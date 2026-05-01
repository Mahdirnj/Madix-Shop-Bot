"""
database.py — All async database operations using aiosqlite.
"""

import aiosqlite
from datetime import datetime
from typing import Optional

DB_PATH = "database.sqlite3"


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

async def init_db() -> None:
    """Create all tables if they do not already exist and seed default settings."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS Users (
                user_id       INTEGER PRIMARY KEY,
                wallet_balance INTEGER NOT NULL DEFAULT 0,
                joined_at     DATETIME NOT NULL
            );

            CREATE TABLE IF NOT EXISTS Products (
                product_id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name                  TEXT    NOT NULL,
                base_currency_price   REAL    NOT NULL,
                admin_profit          INTEGER NOT NULL DEFAULT 0,
                requires_telegram_id  BOOLEAN NOT NULL DEFAULT 0,
                requires_email        BOOLEAN NOT NULL DEFAULT 0,
                requires_password     BOOLEAN NOT NULL DEFAULT 0,
                requires_count        BOOLEAN NOT NULL DEFAULT 0,
                is_active             BOOLEAN NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS Cards (
                card_id          INTEGER PRIMARY KEY AUTOINCREMENT,
                card_number      TEXT    NOT NULL,
                cardholder_name  TEXT    NOT NULL DEFAULT '',
                is_active        BOOLEAN NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS Discounts (
                code                 TEXT    PRIMARY KEY,
                percentage_discount  INTEGER NOT NULL,
                is_active            BOOLEAN NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS Transactions (
                transaction_id   INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id          INTEGER NOT NULL,
                amount           INTEGER NOT NULL,
                receipt_photo_id TEXT,
                status           TEXT    NOT NULL DEFAULT 'PENDING',
                created_at       DATETIME NOT NULL,
                order_id         INTEGER,
                FOREIGN KEY (user_id) REFERENCES Users(user_id)
            );

            CREATE TABLE IF NOT EXISTS Orders (
                order_id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id           INTEGER NOT NULL,
                product_id        INTEGER NOT NULL,
                final_price_paid  INTEGER NOT NULL,
                payment_method    TEXT    NOT NULL,
                input_telegram_id TEXT,
                input_email       TEXT,
                input_password    TEXT,
                input_count       INTEGER,
                discount_code     TEXT,
                status            TEXT    NOT NULL DEFAULT 'PENDING_PAYMENT',
                created_at        DATETIME NOT NULL,
                FOREIGN KEY (user_id)    REFERENCES Users(user_id),
                FOREIGN KEY (product_id) REFERENCES Products(product_id)
            );

            CREATE TABLE IF NOT EXISTS Settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS Admins (
                user_id    INTEGER PRIMARY KEY,
                name       TEXT    NOT NULL,
                added_at   DATETIME NOT NULL
            );
        """)
        # Seed default settings if they do not exist yet
        await db.execute(
            "INSERT OR IGNORE INTO Settings (key, value) VALUES ('currency_rate', '0')"
        )
        await db.execute(
            "INSERT OR IGNORE INTO Settings (key, value) VALUES ('is_auto_currency', '0')"
        )
        await db.commit()

    # Seed Admins table from ADMIN_IDS env on first run
    import os
    raw_ids = os.getenv("ADMIN_IDS", "")
    env_ids = [int(p.strip()) for p in raw_ids.split(",") if p.strip().isdigit()]
    if env_ids:
        async with aiosqlite.connect(DB_PATH) as db:
            for uid in env_ids:
                await db.execute(
                    "INSERT OR IGNORE INTO Admins (user_id, name, added_at) VALUES (?, ?, ?)",
                    (uid, "ادمین اصلی", datetime.utcnow().isoformat()),
                )
            await db.commit()

    # Migrate existing databases that predate schema additions
    async with aiosqlite.connect(DB_PATH) as db:
        # Cards: add cardholder_name if missing
        try:
            await db.execute("ALTER TABLE Cards ADD COLUMN cardholder_name TEXT NOT NULL DEFAULT ''")
            await db.commit()
        except Exception:
            pass  # Column already exists
        # Discounts: add percentage_discount if missing (old schema had 'amount')
        try:
            await db.execute("ALTER TABLE Discounts ADD COLUMN percentage_discount INTEGER NOT NULL DEFAULT 0")
            await db.commit()
        except Exception:
            pass  # Column already exists
        # Transactions: add order_id if missing
        try:
            await db.execute("ALTER TABLE Transactions ADD COLUMN order_id INTEGER")
            await db.commit()
        except Exception:
            pass  # Column already exists
        # Orders: add discount_code if missing
        try:
            await db.execute("ALTER TABLE Orders ADD COLUMN discount_code TEXT")
            await db.commit()
        except Exception:
            pass  # Column already exists
        # Products: add requires_count if missing
        try:
            await db.execute("ALTER TABLE Products ADD COLUMN requires_count BOOLEAN NOT NULL DEFAULT 0")
            await db.commit()
        except Exception:
            pass  # Column already exists
        # Orders: add input_count if missing
        try:
            await db.execute("ALTER TABLE Orders ADD COLUMN input_count INTEGER")
            await db.commit()
        except Exception:
            pass  # Column already exists
        # Admins table migration for existing databases
        try:
            await db.execute(
                "CREATE TABLE IF NOT EXISTS Admins ("
                "user_id INTEGER PRIMARY KEY, name TEXT NOT NULL, added_at DATETIME NOT NULL)"
            )
            await db.commit()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# User helpers
# ---------------------------------------------------------------------------

async def ensure_user(user_id: int) -> None:
    """Insert the user if they don't already exist."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO Users (user_id, wallet_balance, joined_at) VALUES (?, ?, ?)",
            (user_id, 0, datetime.utcnow().isoformat()),
        )
        await db.commit()


async def get_user(user_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM Users WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def update_wallet(user_id: int, delta: int) -> None:
    """Add delta (positive or negative) to the user's wallet balance."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE Users SET wallet_balance = wallet_balance + ? WHERE user_id = ?",
            (delta, user_id),
        )
        await db.commit()


async def deduct_wallet_if_sufficient(user_id: int, amount: int) -> bool:
    """Atomically deduct amount from wallet only if balance >= amount.

    Returns True if the deduction was applied, False if balance was insufficient.
    This single SQL statement prevents the read-check-write race condition.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE Users SET wallet_balance = wallet_balance - ? "
            "WHERE user_id = ? AND wallet_balance >= ?",
            (amount, user_id, amount),
        )
        await db.commit()
        return cursor.rowcount == 1


# ---------------------------------------------------------------------------
# Product helpers
# ---------------------------------------------------------------------------

async def add_product(
    name: str,
    base_currency_price: float,
    admin_profit: int,
    requires_telegram_id: bool,
    requires_email: bool,
    requires_password: bool,
    requires_count: bool = False,
) -> int:
    """Insert a new product and return its generated product_id."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO Products
                (name, base_currency_price, admin_profit,
                 requires_telegram_id, requires_email, requires_password, requires_count, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (name, base_currency_price, admin_profit,
             int(requires_telegram_id), int(requires_email), int(requires_password), int(requires_count)),
        )
        await db.commit()
        return cursor.lastrowid


async def get_all_products(active_only: bool = False) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM Products"
        if active_only:
            query += " WHERE is_active = 1"
        query += " ORDER BY product_id"
        async with db.execute(query) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_product(product_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM Products WHERE product_id = ?", (product_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def toggle_product_status(product_id: int) -> bool:
    """Flip is_active for the product; returns the NEW status."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT is_active FROM Products WHERE product_id = ?", (product_id,)
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            raise ValueError(f"No product with id={product_id}")
        new_status = 0 if row["is_active"] else 1
        await db.execute(
            "UPDATE Products SET is_active = ? WHERE product_id = ?",
            (new_status, product_id),
        )
        await db.commit()
        return bool(new_status)


async def delete_product(product_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM Products WHERE product_id = ?", (product_id,))
        await db.commit()


async def update_product(
    product_id: int,
    name: Optional[str] = None,
    base_currency_price: Optional[float] = None,
    admin_profit: Optional[int] = None,
    requires_telegram_id: Optional[bool] = None,
    requires_email: Optional[bool] = None,
    requires_password: Optional[bool] = None,
    requires_count: Optional[bool] = None,
) -> None:
    """Partial update — only fields that are not None are updated."""
    fields, values = [], []
    if name is not None:
        fields.append("name = ?")
        values.append(name)
    if base_currency_price is not None:
        fields.append("base_currency_price = ?")
        values.append(base_currency_price)
    if admin_profit is not None:
        fields.append("admin_profit = ?")
        values.append(admin_profit)
    if requires_telegram_id is not None:
        fields.append("requires_telegram_id = ?")
        values.append(int(requires_telegram_id))
    if requires_email is not None:
        fields.append("requires_email = ?")
        values.append(int(requires_email))
    if requires_password is not None:
        fields.append("requires_password = ?")
        values.append(int(requires_password))
    if requires_count is not None:
        fields.append("requires_count = ?")
        values.append(int(requires_count))
    if not fields:
        return
    values.append(product_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE Products SET {', '.join(fields)} WHERE product_id = ?",
            values,
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Card helpers
# ---------------------------------------------------------------------------

async def add_card(card_number: str, cardholder_name: str = "") -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO Cards (card_number, cardholder_name, is_active) VALUES (?, ?, 1)",
            (card_number, cardholder_name),
        )
        await db.commit()
        return cursor.lastrowid


async def get_all_cards(active_only: bool = False) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM Cards"
        if active_only:
            query += " WHERE is_active = 1"
        query += " ORDER BY card_id"
        async with db.execute(query) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def toggle_card_status(card_id: int) -> bool:
    """Flip is_active for the card; returns the NEW status."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT is_active FROM Cards WHERE card_id = ?", (card_id,)
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            raise ValueError(f"No card with id={card_id}")
        new_status = 0 if row["is_active"] else 1
        await db.execute(
            "UPDATE Cards SET is_active = ? WHERE card_id = ?", (new_status, card_id)
        )
        await db.commit()
        return bool(new_status)


async def delete_card(card_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM Cards WHERE card_id = ?", (card_id,))
        await db.commit()


# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------

async def get_setting(key: str) -> Optional[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT value FROM Settings WHERE key = ?", (key,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


async def set_setting(key: str, value: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO Settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        await db.commit()


async def get_currency_rate() -> float:
    value = await get_setting("currency_rate")
    try:
        return float(value) if value is not None else 0.0
    except ValueError:
        return 0.0


# ---------------------------------------------------------------------------
# Admin management helpers
# ---------------------------------------------------------------------------

async def get_all_admins() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM Admins ORDER BY added_at") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def add_admin(user_id: int, name: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO Admins (user_id, name, added_at) VALUES (?, ?, ?)",
            (user_id, name, datetime.utcnow().isoformat()),
        )
        await db.commit()


async def remove_admin(user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM Admins WHERE user_id = ?", (user_id,))
        await db.commit()


async def get_admin_name(user_id: int) -> Optional[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT name FROM Admins WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


# ---------------------------------------------------------------------------
# Discount helpers
# ---------------------------------------------------------------------------

async def add_discount(code: str, percentage_discount: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO Discounts (code, percentage_discount, is_active) VALUES (?, ?, 1)",
            (code, percentage_discount),
        )
        await db.commit()


async def get_discount(code: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM Discounts WHERE code = ? AND is_active = 1", (code,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def check_discount_used(user_id: int, code: str) -> bool:
    """Return True if this user already used this discount code on a non-rejected order."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT 1 FROM Orders
            WHERE user_id = ? AND discount_code = ? AND status != 'REJECTED'
            LIMIT 1
            """,
            (user_id, code),
        ) as cursor:
            row = await cursor.fetchone()
            return row is not None


async def get_all_discounts() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM Discounts ORDER BY code") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def delete_discount(code: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM Discounts WHERE code = ?", (code,))
        await db.commit()


# ---------------------------------------------------------------------------
# Transaction helpers
# ---------------------------------------------------------------------------

async def create_transaction(
    user_id: int, amount: int, receipt_photo_id: Optional[str] = None,
    order_id: Optional[int] = None,
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO Transactions (user_id, amount, receipt_photo_id, status, created_at, order_id)
            VALUES (?, ?, ?, 'PENDING', ?, ?)
            """,
            (user_id, amount, receipt_photo_id, datetime.utcnow().isoformat(), order_id),
        )
        await db.commit()
        return cursor.lastrowid


async def get_transaction(transaction_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM Transactions WHERE transaction_id = ?", (transaction_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def update_transaction_status(transaction_id: int, status: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE Transactions SET status = ? WHERE transaction_id = ?",
            (status, transaction_id),
        )
        await db.commit()


async def update_transaction_status_by_order(order_id: int, status: str) -> None:
    """Update the status of the transaction linked to a given order (card receipt)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE Transactions SET status = ? WHERE order_id = ?",
            (status, order_id),
        )
        await db.commit()


async def get_pending_transactions() -> list[dict]:
    """Returns all PENDING transactions with product name for card-order receipts."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT t.*, p.name AS product_name, o.input_count AS input_count
            FROM Transactions t
            LEFT JOIN Orders o ON t.order_id = o.order_id
            LEFT JOIN Products p ON o.product_id = p.product_id
            WHERE t.status = 'PENDING'
            ORDER BY t.created_at
            """
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Order helpers
# ---------------------------------------------------------------------------

async def create_order(
    user_id: int,
    product_id: int,
    final_price_paid: int,
    payment_method: str,
    input_telegram_id: Optional[str] = None,
    input_email: Optional[str] = None,
    input_password: Optional[str] = None,
    input_count: Optional[int] = None,
    discount_code: Optional[str] = None,
    status: str = "PENDING_PAYMENT",
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO Orders
                (user_id, product_id, final_price_paid, payment_method,
                 input_telegram_id, input_email, input_password, input_count, discount_code, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id, product_id, final_price_paid, payment_method,
                input_telegram_id, input_email, input_password, input_count,
                discount_code, status, datetime.utcnow().isoformat(),
            ),
        )
        await db.commit()
        return cursor.lastrowid


async def get_order(order_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM Orders WHERE order_id = ?", (order_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def update_order_status(order_id: int, status: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE Orders SET status = ? WHERE order_id = ?", (status, order_id)
        )
        await db.commit()


async def get_orders_by_status(status: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT o.*, p.name AS product_name
            FROM Orders o
            JOIN Products p ON o.product_id = p.product_id
            WHERE o.status = ?
            ORDER BY o.created_at
            """,
            (status,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_user_orders(user_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT o.*, p.name AS product_name
            FROM Orders o
            JOIN Products p ON o.product_id = p.product_id
            WHERE o.user_id = ?
            ORDER BY o.created_at DESC
            """,
            (user_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_all_users() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM Users") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_statistics() -> dict:
    """Return aggregate stats for the admin Statistics panel."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM Users") as cur:
            total_users = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT COALESCE(SUM(final_price_paid), 0) FROM Orders WHERE status IN ('PROCESSING', 'COMPLETED')"
        ) as cur:
            total_sales = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM Orders WHERE status = 'PENDING_PAYMENT'"
        ) as cur:
            pending_orders = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM Transactions WHERE status = 'PENDING'"
        ) as cur:
            pending_transactions = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM Orders WHERE status = 'PROCESSING'"
        ) as cur:
            processing_orders = (await cur.fetchone())[0]
    return {
        "total_users": total_users,
        "total_sales": total_sales,
        "pending_orders": pending_orders,
        "pending_transactions": pending_transactions,
        "processing_orders": processing_orders,
    }
