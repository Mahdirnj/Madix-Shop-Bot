#!/usr/bin/env bash
# =============================================================================
#  madix.sh — Madix Bot Management CLI
#  Usage: ./madix.sh [command]
#  Commands: status | start | stop | restart | logs | config | update | help
# =============================================================================
set -uo pipefail

# ─── Constants ────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")" )" && pwd)"
SERVICE_NAME="madix-bot"
GITHUB_REPO="https://github.com/Mahdirnj/Madix-Shop-Bot"
GITHUB_BRANCH="Dev"
ENV_FILE="$SCRIPT_DIR/.env"
VENV_PYTHON="$SCRIPT_DIR/venv/bin/python"
REQUIREMENTS_FILE="$SCRIPT_DIR/requirements.txt"
DB_FILE="$SCRIPT_DIR/database.sqlite3"
BACKUP_DIR="$SCRIPT_DIR/backups"

# ─── Colors ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BLUE='\033[0;34m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

# ─── Env Loading ──────────────────────────────────────────────────────────────
# Loaded once at the start of any command that needs it
BOT_TOKEN=""
ADMIN_IDS=""
SUPPORT_HANDLE=""
SHOP_NAME=""

load_env() {
    if [ ! -f "$ENV_FILE" ]; then
        return 0
    fi
    while IFS='=' read -r key value; do
        # Skip comments and blank lines
        [[ "$key" =~ ^[[:space:]]*# ]] && continue
        [[ -z "$key" ]] && continue
        key="${key// /}"
        value="${value%%#*}"       # strip inline comments
        value="${value%"${value##*[![:space:]]}"}" # trim trailing space
        case "$key" in
            BOT_TOKEN)       BOT_TOKEN="$value" ;;
            ADMIN_IDS)       ADMIN_IDS="$value" ;;
            SUPPORT_HANDLE)  SUPPORT_HANDLE="$value" ;;
            SHOP_NAME)       SHOP_NAME="$value" ;;
        esac
    done < "$ENV_FILE"
}

# ─── Helpers ──────────────────────────────────────────────────────────────────
print_banner() {
    echo ""
    echo -e "${CYAN}  ╔══════════════════════════════════════════════════════════╗"
    echo    "  ║                                                          ║"
    echo    "  ║    ███╗   ███╗ █████╗ ██████╗ ██╗██╗  ██╗               ║"
    echo    "  ║    ████╗ ████║██╔══██╗██╔══██╗██║╚██╗██╔╝               ║"
    echo    "  ║    ██╔████╔██║███████║██║  ██║██║ ╚███╔╝                ║"
    echo    "  ║    ██║╚██╔╝██║██╔══██║██║  ██║██║ ██╔██╗                ║"
    echo    "  ║    ██║ ╚═╝ ██║██║  ██║██████╔╝██║██╔╝ ██╗               ║"
    echo    "  ║    ╚═╝     ╚═╝╚═╝  ╚═╝╚═════╝ ╚═╝╚═╝  ╚═╝               ║"
    echo    "  ║                                                          ║"
    echo -e "  ╚══════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

divider() { echo -e "  ${CYAN}  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; }
section()  { echo ""; echo -e "  ${BOLD}  $1${NC}"; divider; }

pause() {
    echo ""
    printf "  ${DIM}Press Enter to continue...${NC} "
    read -r
    clear
}

_sudo() {
    if [ "$EUID" -eq 0 ]; then
        "$@"
    elif command -v sudo &>/dev/null; then
        sudo "$@"
    else
        "$@"
    fi
}

is_systemd() {
    command -v systemctl &>/dev/null && systemctl --version &>/dev/null 2>&1
}

# ─── Status Helpers ───────────────────────────────────────────────────────────
get_service_status() {
    if is_systemd; then
        systemctl is-active "$SERVICE_NAME" 2>/dev/null || echo "inactive"
    else
        if pgrep -f "venv/bin/python.*bot\.py" &>/dev/null; then
            echo "active"
        else
            echo "inactive"
        fi
    fi
}

get_pid() {
    if is_systemd; then
        local pid
        pid=$(systemctl show "$SERVICE_NAME" --property=MainPID --value 2>/dev/null || echo "")
        [ "$pid" = "0" ] && echo "" || echo "$pid"
    else
        pgrep -f "venv/bin/python.*bot\.py" 2>/dev/null | head -1 || echo ""
    fi
}

get_uptime() {
    if is_systemd; then
        local since
        since=$(systemctl show "$SERVICE_NAME" --property=ActiveEnterTimestamp --value 2>/dev/null || echo "")
        if [ -n "$since" ] && [ "$since" != "n/a" ] && [ "$since" != "" ]; then
            local start_epoch now_epoch diff
            start_epoch=$(date -d "$since" +%s 2>/dev/null || echo "")
            if [ -n "$start_epoch" ] && [ "$start_epoch" -gt 0 ] 2>/dev/null; then
                now_epoch=$(date +%s)
                diff=$((now_epoch - start_epoch))
                local days hours mins
                days=$((diff / 86400))
                hours=$(( (diff % 86400) / 3600 ))
                mins=$(( (diff % 3600) / 60 ))
                if   [ "$days"  -gt 0 ]; then echo "${days}d ${hours}h ${mins}m"
                elif [ "$hours" -gt 0 ]; then echo "${hours}h ${mins}m"
                else echo "${mins}m"; fi
                return
            fi
        fi
    fi
    echo "N/A"
}

get_memory() {
    local pid="$1"
    local total_kb used_mb total_mb
    total_kb=$(grep MemTotal /proc/meminfo 2>/dev/null | awk '{print $2}')
    total_mb=$(awk "BEGIN {printf \"%.0f\", ${total_kb:-0}/1024}")
    if [ -n "$pid" ] && [ -f "/proc/$pid/status" ] 2>/dev/null; then
        used_mb=$(grep VmRSS "/proc/$pid/status" 2>/dev/null \
            | awk '{printf "%.1f", $2/1024}')
        echo "${used_mb:-N/A} MB / ${total_mb} MB"
    else
        echo "— / ${total_mb} MB"
    fi
}

get_restarts() {
    if is_systemd; then
        systemctl show "$SERVICE_NAME" --property=NRestarts --value 2>/dev/null || echo "N/A"
    else
        echo "N/A"
    fi
}

get_db_size() {
    [ -f "$DB_FILE" ] && du -sh "$DB_FILE" 2>/dev/null | awk '{print $1}' || echo "N/A"
}

get_db_stats() {
    if [ ! -f "$DB_FILE" ]; then echo "no database yet"; return; fi
    if ! command -v sqlite3 &>/dev/null; then echo "sqlite3 CLI not installed"; return; fi
    local users orders pending
    users=$(sqlite3   "$DB_FILE" "SELECT COUNT(*) FROM Users;"                              2>/dev/null || echo "?")
    orders=$(sqlite3  "$DB_FILE" "SELECT COUNT(*) FROM Orders;"                             2>/dev/null || echo "?")
    pending=$(sqlite3 "$DB_FILE" "SELECT COUNT(*) FROM Transactions WHERE status='PENDING';" 2>/dev/null || echo "?")
    echo "${users} users  |  ${orders} orders  |  ${pending} pending payments"
}

get_cpu() {
    local pid="$1"
    [ -n "$pid" ] && ps -p "$pid" -o %cpu= 2>/dev/null | tr -d ' ' | awk '{printf "%s%%", $1}' || echo "N/A"
}

get_disk() {
    df -h "$SCRIPT_DIR" 2>/dev/null | awk 'NR==2{printf "%s free  (%s used)", $4, $5}' || echo "N/A"
}

get_error_count() {
    local count
    if is_systemd; then
        count=$(journalctl -u "$SERVICE_NAME" --since "24 hours ago" --no-pager 2>/dev/null \
            | grep -ciE "error|exception|traceback" 2>/dev/null || echo "0")
    elif [ -f "$SCRIPT_DIR/bot.log" ]; then
        count=$(grep -ciE "error|exception|traceback" "$SCRIPT_DIR/bot.log" 2>/dev/null || echo "0")
    else
        count="N/A"
    fi
    echo "$count"
}

get_py_version() {
    [ -f "$VENV_PYTHON" ] && "$VENV_PYTHON" --version 2>&1 | awk '{print $2}' || echo "N/A"
}

mask_token() {
    local t="${1:-}"
    if [ ${#t} -gt 12 ]; then
        echo "****...${t: -8}"
    elif [ -n "$t" ]; then
        echo "****"
    else
        echo "(not set)"
    fi
}

# ─── cmd: status ─────────────────────────────────────────────────────────────
cmd_status() {
    load_env

    local status pid mem cpu uptime restarts db_size db_stats disk py_ver masked_token errors
    status=$(get_service_status)
    pid=$(get_pid)
    mem=$(get_memory "$pid")
    cpu=$(get_cpu "$pid")
    uptime=$(get_uptime)
    restarts=$(get_restarts)
    errors=$(get_error_count)
    db_size=$(get_db_size)
    db_stats=$(get_db_stats)
    disk=$(get_disk)
    py_ver=$(get_py_version)
    masked_token=$(mask_token "$BOT_TOKEN")

    local status_label status_color
    case "$status" in
        active)   status_label="● Running";  status_color="$GREEN" ;;
        failed)   status_label="● Failed";   status_color="$RED" ;;
        inactive) status_label="○ Stopped";  status_color="$YELLOW" ;;
        *)        status_label="○ Unknown";  status_color="$YELLOW" ;;
    esac

    echo ""
    divider
    echo -e "  ${BOLD}  MADIX BOT — STATUS DASHBOARD${NC}"
    divider
    echo ""

    echo -e "  ${BOLD}  ▸ Runtime${NC}"
    printf "    %-18s %b%s%b\n"  "Service Status"  "$status_color$BOLD" "$status_label" "$NC"
    printf "    %-18s %s\n"      "Process ID"      "${pid:-None}"
    printf "    %-18s %s\n"      "Uptime"          "$uptime"
    printf "    %-18s %s\n"      "Memory Usage"    "$mem"
    printf "    %-18s %s\n"      "CPU Usage"       "$cpu"
    printf "    %-18s %s\n"      "Restart Count"   "$restarts"
    printf "    %-18s %s\n"      "Errors (24h)"    "$errors"
    echo ""

    echo -e "  ${BOLD}  ▸ System${NC}"
    printf "    %-18s %s\n"  "Database Size"  "$db_size"
    printf "    %-18s %s\n"  "DB Stats"       "$db_stats"
    printf "    %-18s %s\n"  "Disk Space"     "$disk"
    printf "    %-18s %s\n"  "Python"         "$py_ver"
    printf "    %-18s %s\n"  "Install Dir"    "$SCRIPT_DIR"
    echo ""

    echo -e "  ${BOLD}  ▸ Configuration${NC}"
    printf "    %-18s %b%s%b\n"  "Shop Name"  "$BOLD" "${SHOP_NAME:-(not set)}" "$NC"
    printf "    %-18s %s\n"      "Bot Token"  "$masked_token"
    printf "    %-18s %s\n"      "Admin IDs"  "${ADMIN_IDS:-(not set)}"
    printf "    %-18s %s\n"      "Support"    "${SUPPORT_HANDLE:-(not set)}"
    echo ""
    divider
    echo ""

    # Recent logs
    if [ "$status" = "active" ]; then
        echo -e "  ${DIM}  Recent log output:${NC}"
        echo ""
        if is_systemd; then
            journalctl -u "$SERVICE_NAME" -n 8 --no-pager --output=short-iso 2>/dev/null \
                | sed 's/^/    /' || true
        elif [ -f "$SCRIPT_DIR/bot.log" ]; then
            tail -8 "$SCRIPT_DIR/bot.log" | sed 's/^/    /'
        fi
        echo ""
    fi
}

# ─── cmd: start ──────────────────────────────────────────────────────────────
cmd_start() {
    echo ""
    if is_systemd; then
        printf "  ${CYAN}→${NC}  Starting %s...\n" "$SERVICE_NAME"
        _sudo systemctl start "$SERVICE_NAME"
        sleep 2
        if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
            printf "  ${GREEN}✓${NC}  Bot is running.\n"
        else
            printf "  ${RED}✗${NC}  Failed to start. Run: ${CYAN}./madix.sh logs${NC}\n"
        fi
    else
        if [ ! -f "$VENV_PYTHON" ]; then
            printf "  ${RED}✗${NC}  venv not found. Run ./install.sh first.\n"
            exit 1
        fi
        nohup "$VENV_PYTHON" "$SCRIPT_DIR/bot.py" >> "$SCRIPT_DIR/bot.log" 2>&1 &
        printf "  ${GREEN}✓${NC}  Bot started (PID: %s). Logs: %s/bot.log\n" "$!" "$SCRIPT_DIR"
    fi
    echo ""
}

# ─── cmd: stop ───────────────────────────────────────────────────────────────
cmd_stop() {
    echo ""
    if is_systemd; then
        printf "  ${CYAN}→${NC}  Stopping %s...\n" "$SERVICE_NAME"
        _sudo systemctl stop "$SERVICE_NAME"
        printf "  ${GREEN}✓${NC}  Bot stopped.\n"
    else
        local pid
        pid=$(pgrep -f "venv/bin/python.*bot\.py" 2>/dev/null | head -1 || echo "")
        if [ -n "$pid" ]; then
            kill "$pid" 2>/dev/null
            printf "  ${GREEN}✓${NC}  Bot stopped (PID: %s).\n" "$pid"
        else
            printf "  ${YELLOW}⚠${NC}  Bot is not running.\n"
        fi
    fi
    echo ""
}

# ─── cmd: restart ────────────────────────────────────────────────────────────
cmd_restart() {
    echo ""
    if is_systemd; then
        printf "  ${CYAN}→${NC}  Restarting %s...\n" "$SERVICE_NAME"
        _sudo systemctl restart "$SERVICE_NAME"
        sleep 2
        if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
            printf "  ${GREEN}✓${NC}  Bot restarted and running.\n"
        else
            printf "  ${RED}✗${NC}  Restart failed. Run: ${CYAN}./madix.sh logs${NC}\n"
        fi
    else
        cmd_stop
        cmd_start
    fi
    echo ""
}

# ─── cmd: logs ───────────────────────────────────────────────────────────────
cmd_logs() {
    echo ""
    if is_systemd; then
        echo -e "  ${DIM}Showing last 50 log lines — press Ctrl+C to stop live stream, or wait.${NC}"
        echo ""
        # Show last 50 lines then follow; trap Ctrl+C so we return to menu cleanly
        journalctl -u "$SERVICE_NAME" -n 50 --no-pager
        echo ""
        echo -e "  ${DIM}─────────────────────────────────────────────────────${NC}"
        echo -e "  ${CYAN}f${NC}  Follow live  │  Any other key → back to menu"
        echo -e "  ${DIM}─────────────────────────────────────────────────────${NC}"
        printf "  Choice → "
        local key
        read -r -n1 key
        echo ""
        if [[ "${key,,}" == "f" ]]; then
            echo -e "  ${DIM}Streaming live logs — press Ctrl+C to stop.${NC}"
            echo ""
            journalctl -u "$SERVICE_NAME" -f --no-pager || true
            echo ""
        fi
    elif [ -f "$SCRIPT_DIR/bot.log" ]; then
        tail -n 50 "$SCRIPT_DIR/bot.log"
        echo ""
        echo -e "  ${DIM}─────────────────────────────────────────────────────${NC}"
        echo -e "  ${CYAN}f${NC}  Follow live  │  Any other key → back to menu"
        echo -e "  ${DIM}─────────────────────────────────────────────────────${NC}"
        printf "  Choice → "
        local key
        read -r -n1 key
        echo ""
        if [[ "${key,,}" == "f" ]]; then
            tail -f "$SCRIPT_DIR/bot.log" || true
            echo ""
        fi
    else
        printf "  ${YELLOW}⚠${NC}  No log source found.\n"
        echo ""
        printf "  Press any key to continue..."
        read -r -n1
        echo ""
    fi
}

# ─── cmd: config ─────────────────────────────────────────────────────────────
cmd_config() {
    if [ ! -f "$ENV_FILE" ]; then
        printf "  ${RED}✗${NC}  .env file not found. Run ./install.sh first.\n"
        exit 1
    fi

    while true; do
        load_env
        local masked
        masked=$(mask_token "$BOT_TOKEN")

        echo ""
        divider
        echo -e "  ${BOLD}  Configuration Editor${NC}"
        divider
        echo ""
        printf "  ${BOLD}  %-4s %-22s %s${NC}\n" "" "Field" "Current Value"
        echo ""
        printf "    ${CYAN}1${NC}   %-22s ${DIM}%s${NC}\n" "Bot Token"      "$masked"
        printf "    ${CYAN}2${NC}   %-22s ${DIM}%s${NC}\n" "Admin IDs"      "${ADMIN_IDS:-(not set)}"
        printf "    ${CYAN}3${NC}   %-22s ${DIM}%s${NC}\n" "Support Handle" "${SUPPORT_HANDLE:-(not set)}"
        printf "    ${CYAN}4${NC}   %-22s ${DIM}%s${NC}\n" "Shop Name"      "${SHOP_NAME:-(not set)}"
        echo ""
        printf "    ${CYAN}0${NC}   Back\n"
        echo ""
        divider
        echo ""
        printf "  ${BOLD}Select field to edit:${NC} "
        read -r choice

        local key new_value=""
        case "$choice" in
            1)
                key="BOT_TOKEN"
                printf "  ${BOLD}New Bot Token${NC} ${DIM}(input hidden)${NC} → "
                read -rs new_value
                echo ""
                ;;
            2)
                key="ADMIN_IDS"
                printf "  ${BOLD}New Admin IDs${NC} ${DIM}(comma-separated, e.g. 123,456)${NC} → "
                read -r new_value
                ;;
            3)
                key="SUPPORT_HANDLE"
                printf "  ${BOLD}New Support Handle${NC} → "
                read -r new_value
                ;;
            4)
                key="SHOP_NAME"
                printf "  ${BOLD}New Shop Name${NC} → "
                read -r new_value
                ;;
            0|"")
                echo ""
                return 0
                ;;
            *)
                printf "  ${RED}✗${NC}  Invalid option.\n"
                sleep 1
                clear
                continue
                ;;
        esac

        if [ -z "$new_value" ]; then
            printf "  ${YELLOW}⚠${NC}  No change made (empty input).\n"
            sleep 1
            clear
            continue
        fi

        # Escape for sed: handle / & \ characters in the new value
        local safe_value
        safe_value=$(printf '%s' "$new_value" | sed 's/[&/\]/\\&/g')

        if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
            sed -i "s|^${key}=.*|${key}=${safe_value}|" "$ENV_FILE"
        else
            echo "${key}=${new_value}" >> "$ENV_FILE"
        fi

        printf "  ${GREEN}✓${NC}  %s updated successfully.\n" "$key"
        echo ""
        printf "  Restart the bot to apply changes? [Y/n] → "
        local restart_ans
        read -r restart_ans
        restart_ans="${restart_ans:-y}"
        if [[ "${restart_ans,,}" =~ ^(y|yes)$ ]]; then
            cmd_restart
        fi
        clear
    done
}

# ─── cmd: update ─────────────────────────────────────────────────────────────
cmd_update() {
    echo ""

    # Auto-backup before updating
    printf "  ${CYAN}→${NC}  Creating pre-update backup...\n"
    local _backup_dest
    _backup_dest=$(_do_backup "pre-update" 2>/dev/null)
    if [ $? -eq 0 ] && [ -n "$_backup_dest" ]; then
        printf "  ${GREEN}✓${NC}  Backup saved to: ${DIM}%s${NC}\n" "$_backup_dest"
    else
        printf "  ${YELLOW}⚠${NC}  Nothing to backup yet (no .env or database found).\n"
    fi
    echo ""

    # Pull code from GitHub
    if command -v git &>/dev/null; then
        if [ -d "$SCRIPT_DIR/.git" ]; then
            # Detect the current tracking branch
            local cur_branch
            cur_branch=$(git -C "$SCRIPT_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "$GITHUB_BRANCH")
            printf "  ${CYAN}→${NC}  Pulling latest code from GitHub (branch: %s)...\n" "$cur_branch"
            # Stash any local changes so pull never fails
            git -C "$SCRIPT_DIR" stash --include-untracked -q 2>/dev/null || true
            if git -C "$SCRIPT_DIR" pull origin "$cur_branch" 2>&1 | sed 's/^/    /'; then
                printf "  ${GREEN}✓${NC}  Code updated to latest %s.\n" "$cur_branch"
            else
                printf "  ${YELLOW}⚠${NC}  git pull failed — your code was not changed.\n"
            fi
        else
            printf "  ${YELLOW}⚠${NC}  This directory is not a git repository.\n"
            printf "  ${CYAN}→${NC}  Connect it to GitHub now so future updates work? [Y/n] → "
            local init_ans
            read -r init_ans
            init_ans="${init_ans:-y}"
            if [[ "${init_ans,,}" =~ ^(y|yes)$ ]]; then
                printf "  ${CYAN}→${NC}  Initializing git and fetching %s branch...\n" "$GITHUB_BRANCH"
                git -C "$SCRIPT_DIR" init -q
                git -C "$SCRIPT_DIR" remote add origin "$GITHUB_REPO" 2>/dev/null \
                    || git -C "$SCRIPT_DIR" remote set-url origin "$GITHUB_REPO"
                if git -C "$SCRIPT_DIR" fetch origin "$GITHUB_BRANCH" 2>&1 | sed 's/^/    /'; then
                    git -C "$SCRIPT_DIR" checkout -B "$GITHUB_BRANCH" "FETCH_HEAD" 2>&1 | sed 's/^/    /'
                    printf "  ${GREEN}✓${NC}  Connected to GitHub and code updated.\n"
                    printf "  ${DIM}  (.env and database are untracked — they were not touched)${NC}\n"
                else
                    printf "  ${RED}✗${NC}  Could not fetch from GitHub. Check network connection.\n"
                fi
            else
                printf "  ${DIM}  Skipping code update.${NC}\n"
            fi
        fi
    else
        printf "  ${YELLOW}⚠${NC}  git is not installed — skipping code pull.\n"
        printf "  ${DIM}  Install it with: sudo apt-get install -y git${NC}\n"
    fi
    echo ""

    # Update Python dependencies
    if [ -f "$VENV_PYTHON" ]; then
        printf "  ${CYAN}→${NC}  Updating Python dependencies...\n"
        if "$VENV_PYTHON" -m pip install -r "$REQUIREMENTS_FILE" --upgrade -q 2>&1 | sed 's/^/    /'; then
            printf "  ${GREEN}✓${NC}  Dependencies up to date.\n"
        else
            printf "  ${RED}✗${NC}  Dependency update failed.\n"
        fi
    else
        printf "  ${RED}✗${NC}  venv not found. Run ./install.sh first.\n"
    fi

    echo ""
    printf "  Restart bot to apply updates? [Y/n] → "
    local ans
    read -r ans
    ans="${ans:-y}"
    if [[ "${ans,,}" =~ ^(y|yes)$ ]]; then
        cmd_restart
    fi
    echo ""
}

# ─── cmd: backup ─────────────────────────────────────────────────────────────
_do_backup() {
    local label="${1:-manual}"
    local ts
    ts=$(date '+%Y%m%d_%H%M%S')
    local dest="$BACKUP_DIR/${ts}_${label}"
    mkdir -p "$dest"

    local ok=0
    [ -f "$ENV_FILE" ]  && cp "$ENV_FILE"  "$dest/.env"             && ok=$((ok+1))
    [ -f "$DB_FILE"  ]  && cp "$DB_FILE"   "$dest/database.sqlite3" && ok=$((ok+1))

    if [ "$ok" -eq 0 ]; then
        rmdir "$dest" 2>/dev/null
        return 1
    fi
    echo "$dest"
    return 0
}

cmd_backup() {
    echo ""
    section "Backup"
    echo ""

    local dest
    dest=$(_do_backup "manual")
    local exit_code=$?

    if [ "$exit_code" -eq 0 ]; then
        printf "  ${GREEN}✓${NC}  Backup saved to:\n"
        printf "      ${DIM}%s${NC}\n" "$dest"
        echo ""

        # List existing backups
        if [ -d "$BACKUP_DIR" ]; then
            local count
            count=$(find "$BACKUP_DIR" -maxdepth 1 -mindepth 1 -type d | wc -l)
            printf "  ${DIM}Total backups stored: %s  (in %s)${NC}\n" "$count" "$BACKUP_DIR"
        fi
    else
        printf "  ${RED}✗${NC}  Nothing to backup (.env and database not found).\n"
    fi
    echo ""
}

# ─── cmd: uninstall ──────────────────────────────────────────────────────────
cmd_uninstall() {
    echo ""
    section "Uninstall"
    echo ""
    printf "  ${RED}${BOLD}WARNING:${NC}  This will remove the bot service and optionally delete all data.\n"
    echo ""
    printf "  Type ${BOLD}yes${NC} to confirm uninstall → "
    local confirm_ans
    read -r confirm_ans
    if [[ "${confirm_ans,,}" != "yes" ]]; then
        printf "  ${YELLOW}⚠${NC}  Uninstall cancelled.\n\n"
        return 0
    fi

    # 1. Stop & disable the systemd service
    if is_systemd; then
        local svc_file="/etc/systemd/system/$SERVICE_NAME.service"
        printf "  ${CYAN}→${NC}  Stopping service...\n"
        _sudo systemctl stop "$SERVICE_NAME" 2>/dev/null || true
        printf "  ${CYAN}→${NC}  Disabling service...\n"
        _sudo systemctl disable "$SERVICE_NAME" 2>/dev/null || true
        if [ -f "$svc_file" ]; then
            printf "  ${CYAN}→${NC}  Removing service file...\n"
            _sudo rm -f "$svc_file"
            _sudo systemctl daemon-reload
        fi
        printf "  ${GREEN}✓${NC}  systemd service removed.\n"
    else
        # Kill background process if running without systemd
        local pid
        pid=$(pgrep -f "venv/bin/python.*bot\.py" 2>/dev/null | head -1 || echo "")
        [ -n "$pid" ] && kill "$pid" 2>/dev/null && printf "  ${GREEN}✓${NC}  Bot process stopped.\n"
    fi
    echo ""

    # 2. Ask whether to delete data
    printf "  Delete database and backups? ${RED}(irreversible)${NC} [y/N] → "
    local del_data
    read -r del_data
    if [[ "${del_data,,}" =~ ^(y|yes)$ ]]; then
        [ -f "$DB_FILE"    ] && rm -f "$DB_FILE"    && printf "  ${GREEN}✓${NC}  Database deleted.\n"
        [ -d "$BACKUP_DIR" ] && rm -rf "$BACKUP_DIR" && printf "  ${GREEN}✓${NC}  Backups deleted.\n"
    else
        printf "  ${DIM}  Data kept — files remain in: %s${NC}\n" "$SCRIPT_DIR"
    fi
    echo ""

    # 3. Remove venv
    printf "  Delete Python virtual environment? [y/N] → "
    local del_venv
    read -r del_venv
    if [[ "${del_venv,,}" =~ ^(y|yes)$ ]]; then
        [ -d "$SCRIPT_DIR/venv" ] && rm -rf "$SCRIPT_DIR/venv" && printf "  ${GREEN}✓${NC}  venv deleted.\n"
    fi
    echo ""

    # 4. Remove global command symlink
    local _global="/usr/local/bin/madix"
    if [ -L "$_global" ]; then
        _sudo rm -f "$_global" && printf "  ${GREEN}✓${NC}  Global 'madix' command removed.\n"
    fi
    echo ""

    printf "  ${GREEN}✓${NC}  Madix Bot has been uninstalled.\n"
    printf "  ${DIM}  Project files remain at: %s${NC}\n" "$SCRIPT_DIR"
    echo ""
    exit 0
}

# ─── cmd: health ─────────────────────────────────────────────────────────────
cmd_health() {
    load_env
    echo ""
    section "Health Check"
    echo ""

    local all_ok=true

    # 1. Network — can we reach Telegram API?
    printf "  ${CYAN}→${NC}  Checking network connectivity to Telegram API...\n"
    if curl -sf --max-time 8 "https://api.telegram.org" -o /dev/null 2>/dev/null; then
        printf "  ${GREEN}✓${NC}  api.telegram.org is reachable.\n"
    else
        printf "  ${RED}✗${NC}  Cannot reach api.telegram.org — check firewall or internet connection.\n"
        all_ok=false
    fi
    echo ""

    # 2. Bot token — validate via getMe
    printf "  ${CYAN}→${NC}  Validating bot token...\n"
    if [ -z "$BOT_TOKEN" ]; then
        printf "  ${RED}✗${NC}  BOT_TOKEN is not set in .env\n"
        all_ok=false
    else
        local api_resp
        api_resp=$(curl -sf --max-time 8 "https://api.telegram.org/bot${BOT_TOKEN}/getMe" 2>/dev/null || echo "")
        if echo "$api_resp" | grep -q '"ok":true'; then
            local bot_name
            bot_name=$(echo "$api_resp" | grep -o '"username":"[^"]*"' | cut -d'"' -f4)
            printf "  ${GREEN}✓${NC}  Token valid — bot username: @%s\n" "$bot_name"
        else
            printf "  ${RED}✗${NC}  Token is invalid or revoked. Check BOT_TOKEN in .env\n"
            all_ok=false
        fi
    fi
    echo ""

    # 3. Database file — exists and is readable SQLite
    printf "  ${CYAN}→${NC}  Checking database integrity...\n"
    if [ ! -f "$DB_FILE" ]; then
        printf "  ${YELLOW}⚠${NC}  Database file not found (will be created on first run).\n"
    else
        # SQLite header magic bytes check
        local magic
        magic=$(head -c 16 "$DB_FILE" 2>/dev/null | tr -d '\0' || echo "")
        if [[ "$magic" == "SQLite format 3"* ]]; then
            local db_size
            db_size=$(du -sh "$DB_FILE" 2>/dev/null | awk '{print $1}')
            printf "  ${GREEN}✓${NC}  Database is valid SQLite (%s).\n" "$db_size"
        else
            printf "  ${RED}✗${NC}  Database file exists but is corrupt or not a valid SQLite file.\n"
            all_ok=false
        fi
    fi
    echo ""

    # 4. venv + Python
    printf "  ${CYAN}→${NC}  Checking Python environment...\n"
    if [ -f "$VENV_PYTHON" ] && "$VENV_PYTHON" -m pip --version &>/dev/null 2>&1; then
        printf "  ${GREEN}✓${NC}  venv OK — %s\n" "$("$VENV_PYTHON" --version 2>&1)"
    else
        printf "  ${RED}✗${NC}  venv is missing or broken. Run ./install.sh to repair.\n"
        all_ok=false
    fi
    echo ""

    # 5. Disk space — warn if < 500MB free
    printf "  ${CYAN}→${NC}  Checking disk space...\n"
    local free_kb
    free_kb=$(df -k "$SCRIPT_DIR" 2>/dev/null | awk 'NR==2{print $4}' || echo "0")
    local free_mb=$(( free_kb / 1024 ))
    if [ "$free_mb" -lt 500 ]; then
        printf "  ${YELLOW}⚠${NC}  Low disk space: %sMB free. Consider cleaning up logs or backups.\n" "$free_mb"
        all_ok=false
    else
        printf "  ${GREEN}✓${NC}  Disk space OK: %sMB free.\n" "$free_mb"
    fi
    echo ""

    # Summary
    divider
    if [ "$all_ok" = true ]; then
        printf "  ${GREEN}${BOLD}✓  All checks passed — bot is healthy.${NC}\n"
    else
        printf "  ${YELLOW}${BOLD}⚠  One or more checks failed — review the issues above.${NC}\n"
    fi
    echo ""
}

# ─── cmd: help ───────────────────────────────────────────────────────────────
cmd_install_global() {
    local target="/usr/local/bin/madix"
    local self="$SCRIPT_DIR/madix.sh"
    echo ""
    echo -e "  ${BOLD}Installing global 'madix' command...${NC}"
    echo ""
    if _sudo ln -sf "$self" "$target" 2>/dev/null && _sudo chmod +x "$target" 2>/dev/null; then
        echo -e "  ${GREEN}✔${NC}  Symlink created: ${CYAN}$target${NC} → ${DIM}$self${NC}"
        echo -e "  ${GREEN}✔${NC}  You can now run ${CYAN}madix${NC} from anywhere in the terminal."
    else
        echo -e "  ${RED}✗${NC}  Failed to create symlink (try running with sudo)."
        echo -e "  ${DIM}  Hint: sudo ln -sf \"$self\" $target${NC}"
    fi
    echo ""
}

cmd_help() {
    print_banner
    echo -e "  ${BOLD}Usage:${NC}  ./madix.sh [command]"
    echo ""
    echo -e "  ${BOLD}Commands:${NC}"
    echo ""
    printf "    ${CYAN}%-12s${NC}  %s\n" "status"    "Show detailed status dashboard (runtime, config, logs)"
    printf "    ${CYAN}%-12s${NC}  %s\n" "start"     "Start the bot"
    printf "    ${CYAN}%-12s${NC}  %s\n" "stop"      "Stop the bot"
    printf "    ${CYAN}%-12s${NC}  %s\n" "restart"   "Restart the bot"
    printf "    ${CYAN}%-12s${NC}  %s\n" "logs"      "View recent logs (with live-follow option)"
    printf "    ${CYAN}%-12s${NC}  %s\n" "health"    "Run health checks (network, token, DB, disk)"
    printf "    ${CYAN}%-12s${NC}  %s\n" "backup"    "Backup .env + database to backups/"
    printf "    ${CYAN}%-12s${NC}  %s\n" "config"    "Interactively edit .env configuration"
    printf "    ${CYAN}%-12s${NC}  %s\n" "update"    "Pull latest code from GitHub + update deps"
    printf "    ${CYAN}%-12s${NC}  %s\n" "uninstall" "Remove service, optionally delete data"
    printf "    ${CYAN}%-12s${NC}  %s\n" "install-global" "Install 'madix' command system-wide"
    printf "    ${CYAN}%-12s${NC}  %s\n" "help"      "Show this help message"
    echo ""
    echo -e "  ${DIM}Run without arguments for the interactive menu.${NC}"
    echo ""
}

# ─── Interactive Menu ─────────────────────────────────────────────────────────
cmd_menu() {
    while true; do
        clear
        print_banner
        load_env

        local status status_color pid _cpu _mem _db
        status=$(get_service_status)
        pid=$(get_pid)
        case "$status" in
            active)   status_color="$GREEN" ;;
            failed)   status_color="$RED" ;;
            *)        status_color="$YELLOW" ;;
        esac

        # Live stats — gathered fresh on every menu render
        if [ "$status" = "active" ] && [ -n "$pid" ]; then
            _cpu=$(get_cpu "$pid")
            _mem=$(get_memory "$pid")
        else
            _cpu="—"
            _mem="—"
        fi
        _db=$(get_db_stats)

        echo -e "  ${BOLD}  Shop:${NC}  ${SHOP_NAME:-(not configured)}   ${BOLD}|${NC}  Status: ${status_color}${BOLD}${status^}${NC}"
        echo -e "  ${DIM}  CPU: ${_cpu}   RAM: ${_mem}   DB: ${_db}${NC}"
        echo ""
        divider
        echo ""
        printf "    ${CYAN}1${NC}   📊  Status & Details\n"
        printf "    ${CYAN}2${NC}   ▶   Start Bot\n"
        printf "    ${CYAN}3${NC}   ■   Stop Bot\n"
        printf "    ${CYAN}4${NC}   ↺   Restart Bot\n"
        printf "    ${CYAN}5${NC}   📜  View Logs\n"
        printf "    ${CYAN}6${NC}   🩺  Health Check\n"
        printf "    ${CYAN}7${NC}   💾  Backup\n"
        printf "    ${CYAN}8${NC}   ⚙   Edit Configuration\n"
        printf "    ${CYAN}9${NC}   ↑   Update (GitHub + deps)\n"
        printf "    ${CYAN}u${NC}   🗑   Uninstall\n"
        printf "    ${CYAN}g${NC}   🌐  Install 'madix' command globally\n"
        echo ""
        printf "    ${CYAN}0${NC}   ✕   Exit\n"
        echo ""
        divider
        echo ""
        printf "  ${BOLD}Choice:${NC} "
        # read with 3-second timeout — if no input, loop reruns and stats refresh
        if ! read -r -t 3 choice; then
            continue
        fi

        case "$choice" in
            1) clear; cmd_status;    pause ;;
            2) clear; cmd_start;     pause ;;
            3) clear; cmd_stop;      pause ;;
            4) clear; cmd_restart;   pause ;;
            5) clear; cmd_logs ;;
            6) clear; cmd_health;    pause ;;
            7) clear; cmd_backup;    pause ;;
            8) clear; cmd_config ;;
            9) clear; cmd_update;    pause ;;
            u|U) clear; cmd_uninstall ;;
            g|G) clear; cmd_install_global; pause ;;
            0|q|Q) echo ""; exit 0 ;;
            *) printf "  ${RED}✗${NC}  Invalid option.\n"; sleep 1 ;;
        esac
    done
}

# ─── Entry Point ──────────────────────────────────────────────────────────────
CMD="${1:-}"

case "$CMD" in
    "")           cmd_menu ;;
    status)       cmd_status ;;
    start)        cmd_start ;;
    stop)         cmd_stop ;;
    restart)      cmd_restart ;;
    logs)         cmd_logs ;;
    health)       cmd_health ;;
    backup)       cmd_backup ;;
    config)       cmd_config ;;
    update)       cmd_update ;;
    uninstall)       cmd_uninstall ;;
    install-global)  cmd_install_global ;;
    help|-h|--help)  cmd_help ;;
    *)
        printf "\n  ${RED}✗${NC}  Unknown command: %s\n" "$CMD"
        printf "  Run ${CYAN}./madix.sh help${NC} for available commands.\n\n"
        exit 1
        ;;
esac
