#!/usr/bin/env bash
# =============================================================================
#  Madix Bot — Server Installation Script
#  Usage: bash install.sh
# =============================================================================
set -uo pipefail

# ─── Colors & Formatting ──────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BLUE='\033[0;34m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

# ─── Constants ────────────────────────────────────────────────────────────────
INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="madix-bot"
VENV_DIR="$INSTALL_DIR/venv"
ENV_FILE="$INSTALL_DIR/.env"
REQUIREMENTS_FILE="$INSTALL_DIR/requirements.txt"
MIN_PYTHON_MAJOR=3
MIN_PYTHON_MINOR=10
PYTHON_CMD=""
VENV_PYTHON=""
SYSTEMD_AVAILABLE=false
SKIP_ENV=false
PKG_MANAGER=""
PKG_INSTALL_CMD=()

# ─── Spinner ──────────────────────────────────────────────────────────────────
_spin_pid=""
_spin_msg=""

start_spinner() {
    _spin_msg="$1"
    (
        frames=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')
        i=0
        while true; do
            printf "\r  ${CYAN}${frames[$((i % 10))]}${NC}  %s   " "$_spin_msg"
            i=$((i + 1))
            sleep 0.08
        done
    ) &
    _spin_pid=$!
    disown "$_spin_pid" 2>/dev/null || true
}

stop_spinner() {
    local status="${1:-0}"
    local msg="${2:-$_spin_msg}"
    if [ -n "$_spin_pid" ]; then
        kill "$_spin_pid" 2>/dev/null || true
        wait "$_spin_pid" 2>/dev/null || true
        _spin_pid=""
    fi
    if [ "$status" -eq 0 ]; then
        printf "\r  ${GREEN}✓${NC}  %-55s\n" "$msg"
    else
        printf "\r  ${RED}✗${NC}  %-55s\n" "$msg"
    fi
}

# ─── Print Helpers ────────────────────────────────────────────────────────────
print_banner() {
    clear
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
    echo    "  ║         Professional Telegram Shop Bot Installer        ║"
    echo -e "  ╚══════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

print_section() {
    echo ""
    echo -e "  ${BOLD}${BLUE}▶  $1${NC}"
    echo -e "  ${DIM}  ─────────────────────────────────────────────────────${NC}"
}

print_ok()   { printf "  ${GREEN}✓${NC}  %s\n" "$1"; }
print_info() { printf "  ${CYAN}ℹ${NC}  %s\n" "$1"; }
print_warn() { printf "  ${YELLOW}⚠${NC}  %s\n" "$1"; }
print_err()  { printf "  ${RED}✗${NC}  %s\n" "$1"; }

prompt_input() {
    # prompt_input <var_name> <label> [default] [secret=true]
    local var_name="$1"
    local label="$2"
    local default="${3:-}"
    local secret="${4:-false}"
    local value=""

    while [ -z "$value" ]; do
        if [ -n "$default" ]; then
            printf "  ${BOLD}%-30s${NC} ${DIM}[%s]${NC} → " "$label" "$default"
        else
            printf "  ${BOLD}%-30s${NC} → " "$label"
        fi

        if [ "$secret" = "true" ]; then
            read -rs value
            echo ""
        else
            read -r value
        fi

        if [ -z "$value" ] && [ -n "$default" ]; then
            value="$default"
        fi

        if [ -z "$value" ]; then
            print_err "This field cannot be empty."
        fi
    done

    printf -v "$var_name" '%s' "$value"
}

prompt_optional() {
    # prompt_optional <var_name> <label> [default]
    local var_name="$1"
    local label="$2"
    local default="${3:-}"
    local value=""

    if [ -n "$default" ]; then
        printf "  ${BOLD}%-30s${NC} ${DIM}[%s]${NC} → " "$label" "$default"
    else
        printf "  ${BOLD}%-30s${NC} ${DIM}[leave blank to skip]${NC} → " "$label"
    fi
    read -r value
    if [ -z "$value" ]; then
        value="$default"
    fi
    printf -v "$var_name" '%s' "$value"
}

confirm() {
    local label="$1"
    local default="${2:-y}"
    local hint
    [ "$default" = "y" ] && hint="${BOLD}Y${NC}/n" || hint="y/${BOLD}N${NC}"
    printf "  %s [%b] → " "$label" "$hint"
    local ans
    read -r ans
    ans="${ans:-$default}"
    [[ "${ans,,}" =~ ^(y|yes)$ ]]
}

# ─── Package Manager Detection ───────────────────────────────────────────────
detect_pkg_manager() {
    if command -v apt-get &>/dev/null; then
        PKG_MANAGER="apt"
        PKG_INSTALL_CMD=(sudo apt-get install -y)
    elif command -v dnf &>/dev/null; then
        PKG_MANAGER="dnf"
        PKG_INSTALL_CMD=(sudo dnf install -y)
    elif command -v yum &>/dev/null; then
        PKG_MANAGER="yum"
        PKG_INSTALL_CMD=(sudo yum install -y)
    elif command -v pacman &>/dev/null; then
        PKG_MANAGER="pacman"
        PKG_INSTALL_CMD=(sudo pacman -S --noconfirm)
    else
        PKG_MANAGER="unknown"
        PKG_INSTALL_CMD=()
    fi
}

# Returns the package name(s) for a given component on the detected PKG_MANAGER
# usage: pkg_name_for <what>   (what = pip | venv | python)
pkg_name_for() {
    local what="$1"
    local pyver="3"
    [ -n "$PYTHON_CMD" ] && pyver=$("$PYTHON_CMD" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "3")
    case "$PKG_MANAGER" in
        apt)
            case "$what" in
                pip)    echo "python3-pip" ;;
                venv)   echo "python${pyver}-venv python3-venv" ;;
                python) echo "python3.11" ;;
            esac ;;
        dnf|yum)
            case "$what" in
                pip)    echo "python3-pip" ;;
                venv)   echo "python3-pip" ;;
                python) echo "python3.11" ;;
            esac ;;
        pacman)
            case "$what" in
                pip)    echo "python-pip" ;;
                venv)   echo "python" ;;
                python) echo "python" ;;
            esac ;;
        *) echo "" ;;
    esac
}

# Prompts user to auto-install missing packages; exits if they decline or if
# no package manager is available.
ask_and_install() {
    local desc="$1"
    local pkgs="$2"

    echo ""
    print_warn "${desc} is required but not installed."

    if [ ${#PKG_INSTALL_CMD[@]} -eq 0 ]; then
        echo -e "  ${DIM}No supported package manager (apt/dnf/yum/pacman) was found.${NC}"
        echo -e "  ${DIM}Please install ${desc} manually and re-run this script.${NC}"
        echo ""
        exit 1
    fi

    echo -e "  ${DIM}Command: ${PKG_INSTALL_CMD[*]} $pkgs${NC}"
    echo ""
    if confirm "Install missing packages automatically?" "y"; then
        echo ""
        echo -e "  ${CYAN}──────────────────────────────────────────────────────${NC}"
        # Run visibly — sudo may need a password; do NOT redirect output
        if [ "$PKG_MANAGER" = "apt" ]; then
            sudo apt-get update -qq
        fi
        # Read package names into an array (split on spaces, not IFS)
        local -a pkgs_arr
        IFS=' ' read -ra pkgs_arr <<< "$pkgs"
        "${PKG_INSTALL_CMD[@]}" "${pkgs_arr[@]}"
        local exit_code=$?
        echo -e "  ${CYAN}──────────────────────────────────────────────────────${NC}"
        echo ""
        if [ "$exit_code" -eq 0 ]; then
            print_ok "Installed: $pkgs"
            return 0
        else
            print_err "Automatic installation failed (exit code: $exit_code)"
            echo -e "  ${DIM}Try manually: $PKG_INSTALL_CMD $pkgs${NC}"
            echo ""
            exit 1
        fi
    else
        echo ""
        print_err "Installation cancelled — ${desc} is required to continue."
        exit 1
    fi
}

# Python detection helper (extracted so it can be called after auto-install)
_detect_python() {
    PYTHON_CMD=""
    for cmd in python3.13 python3.12 python3.11 python3.10 python3; do
        if command -v "$cmd" &>/dev/null; then
            local ver major minor
            ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
            major=$(echo "$ver" | cut -d. -f1)
            minor=$(echo "$ver" | cut -d. -f2)
            if [ "$major" -ge "$MIN_PYTHON_MAJOR" ] && [ "$minor" -ge "$MIN_PYTHON_MINOR" ]; then
                PYTHON_CMD="$cmd"
                return 0
            fi
        fi
    done
    return 1
}

# ─── Step 1: System Requirements ─────────────────────────────────────────────
check_requirements() {
    print_section "System Requirements"
    detect_pkg_manager

    # ── Python 3.10+ ──────────────────────────────────────────────────────────
    if ! _detect_python; then
        ask_and_install "Python $MIN_PYTHON_MAJOR.$MIN_PYTHON_MINOR+" "$(pkg_name_for python)"
        if ! _detect_python; then
            print_err "Python $MIN_PYTHON_MAJOR.$MIN_PYTHON_MINOR+ still not found after installation."
            echo -e "  ${DIM}Please install it manually and re-run this script.${NC}"
            exit 1
        fi
    fi
    print_ok "Python: $("$PYTHON_CMD" --version 2>&1)"

    # ── pip ───────────────────────────────────────────────────────────────────
    if ! "$PYTHON_CMD" -m pip --version &>/dev/null 2>&1; then
        ask_and_install "pip" "$(pkg_name_for pip)"
        if ! "$PYTHON_CMD" -m pip --version &>/dev/null 2>&1; then
            print_err "pip still not available after installation."
            echo -e "  ${DIM}Try: ${PKG_INSTALL_CMD[*]} $(pkg_name_for pip)${NC}"
            exit 1
        fi
    fi
    print_ok "pip: $("$PYTHON_CMD" -m pip --version 2>&1 | awk '{print $1, $2}')"

    # ── venv module ───────────────────────────────────────────────────────────
    if ! "$PYTHON_CMD" -m venv --help &>/dev/null 2>&1; then
        ask_and_install "python3-venv" "$(pkg_name_for venv)"
        if ! "$PYTHON_CMD" -m venv --help &>/dev/null 2>&1; then
            print_err "venv module still not available after installation."
            echo -e "  ${DIM}Try: ${PKG_INSTALL_CMD[*]} $(pkg_name_for venv)${NC}"
            exit 1
        fi
    fi
    print_ok "venv module available"

    # ── systemd ───────────────────────────────────────────────────────────────
    if command -v systemctl &>/dev/null && systemctl --version &>/dev/null 2>&1; then
        SYSTEMD_AVAILABLE=true
        print_ok "systemd is available"
    else
        print_warn "systemd not found — service auto-start will be skipped"
    fi

    # ── root warning ──────────────────────────────────────────────────────────
    if [ "$EUID" -eq 0 ]; then
        print_warn "Running as root. For production, consider a dedicated non-root user."
    fi
}

# ─── Step 2: Detect Existing Installation ────────────────────────────────────
check_existing() {
    if [ -f "$ENV_FILE" ]; then
        echo ""
        print_warn "Existing configuration found at: $ENV_FILE"
        if confirm "Overwrite existing configuration?" "n"; then
            SKIP_ENV=false
        else
            SKIP_ENV=true
            print_info "Keeping existing .env — configuration step will be skipped."
        fi
    fi
}

# ─── Step 3: Virtual Environment ─────────────────────────────────────────────
setup_venv() {
    print_section "Virtual Environment"

    # Helper: try to create the venv; if it fails due to missing ensurepip/venv
    # package, offer to install the version-specific package and retry once.
    _create_venv() {
        rm -rf "$VENV_DIR"
        local venv_err
        venv_err=$("$PYTHON_CMD" -m venv "$VENV_DIR" 2>&1)
        local exit_code=$?
        if [ "$exit_code" -ne 0 ]; then
            # Detect the "ensurepip is not available" error from Debian/Ubuntu
            if echo "$venv_err" | grep -qi "ensurepip"; then
                # Derive the exact versioned package name, e.g. python3.12-venv
                local pyver
                pyver=$("$PYTHON_CMD" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "3")
                local venv_pkg="python${pyver}-venv"
                ask_and_install "$venv_pkg" "$venv_pkg"
                # Retry once after install
                rm -rf "$VENV_DIR"
                if ! "$PYTHON_CMD" -m venv "$VENV_DIR"; then
                    print_err "Failed to create virtual environment even after installing $venv_pkg"
                    exit 1
                fi
            else
                echo "$venv_err" >&2
                print_err "Failed to create virtual environment"
                exit 1
            fi
        fi
    }

    # Check if an existing venv is fully functional (python + pip both work).
    # Any failure (stale, cross-OS, broken) → delete and recreate cleanly.
    _venv_is_healthy() {
        [ -f "$VENV_DIR/bin/python" ] &&
        "$VENV_DIR/bin/python" --version &>/dev/null 2>&1 &&
        "$VENV_DIR/bin/python" -m pip --version &>/dev/null 2>&1
    }

    if [ -d "$VENV_DIR" ]; then
        if _venv_is_healthy; then
            print_info "Existing venv found — reusing."
        else
            print_warn "Existing venv is broken or stale — recreating."
            _create_venv
            print_ok "Virtual environment created"
        fi
    else
        print_info "Creating virtual environment..."
        _create_venv
        print_ok "Virtual environment created"
    fi

    VENV_PYTHON="$VENV_DIR/bin/python"

    # Final sanity check
    if ! "$VENV_PYTHON" -m pip --version &>/dev/null 2>&1; then
        print_err "pip is still not available inside the venv after recreation."
        print_info "Try manually: $PYTHON_CMD -m venv --clear \"$VENV_DIR\""
        exit 1
    fi

    print_ok "venv ready: $("$VENV_PYTHON" --version 2>&1)"
}

# ─── Step 4: Install Dependencies ────────────────────────────────────────────
install_deps() {
    print_section "Installing Dependencies"

    if [ ! -f "$REQUIREMENTS_FILE" ]; then
        print_err "requirements.txt not found at $REQUIREMENTS_FILE"
        exit 1
    fi

    print_info "Installing Python packages (this may take a minute)..."
    echo ""
    echo -e "  ${CYAN}──────────────────────────────────────────────────────${NC}"
    # Always use 'python -m pip' — reliable regardless of whether pip binary exists
    "$VENV_PYTHON" -m pip install -r "$REQUIREMENTS_FILE" --upgrade
    local exit_code=$?
    echo -e "  ${CYAN}──────────────────────────────────────────────────────${NC}"
    echo ""
    if [ "$exit_code" -eq 0 ]; then
        print_ok "All dependencies installed successfully"
    else
        print_err "Dependency installation failed (exit code: $exit_code)"
        print_info "Try manually: \"$VENV_PYTHON\" -m pip install -r \"$REQUIREMENTS_FILE\""
        exit 1
    fi
}

# ─── Step 5: Configure .env ──────────────────────────────────────────────────
configure_env() {
    print_section "Bot Configuration"

    if [ "$SKIP_ENV" = true ]; then
        print_info "Skipping — using existing configuration."
        return 0
    fi

    echo ""
    echo -e "  ${DIM}All fields are required unless marked optional.${NC}"
    echo -e "  ${DIM}The Bot Token will be hidden as you type (security).${NC}"
    echo ""

    local token admin_ids support_handle shop_name

    prompt_input  token          "Telegram Bot Token"              ""          "true"
    prompt_input  admin_ids      "Admin Telegram User ID(s)"       ""          "false"
    prompt_optional support_handle "Support Handle (optional)"     "@support"
    prompt_input  shop_name      "Your Shop Name"                  "My Shop"   "false"

    # Write .env with comments
    cat > "$ENV_FILE" << EOF
# ─── Madix Bot — Configuration ────────────────────────────────────────────────
# Generated on $(date '+%Y-%m-%d %H:%M:%S')
# IMPORTANT: Keep this file private. Never commit it to version control.

# Your bot token from @BotFather
BOT_TOKEN=$token

# Comma-separated Telegram user IDs that have admin access
# Example: 123456789,987654321
ADMIN_IDS=$admin_ids

# Telegram handle for customer support (shown in the support menu)
SUPPORT_HANDLE=$support_handle

# Your shop's display name shown to users in greeting messages
SHOP_NAME=$shop_name
EOF

    chmod 600 "$ENV_FILE"
    echo ""
    print_ok ".env created and locked (chmod 600 — owner read-only)"
    print_ok "Shop name: $shop_name"
}

# ─── Step 6: systemd Service ─────────────────────────────────────────────────
setup_service() {
    print_section "System Service Setup"

    if [ "$SYSTEMD_AVAILABLE" != true ]; then
        print_warn "Skipping — systemd is not available."
        print_info "Start manually: cd $INSTALL_DIR && $VENV_PYTHON bot.py"
        return 0
    fi

    echo ""
    if ! confirm "Install as a systemd service? (recommended — auto-starts on reboot)"; then
        print_info "Skipping service installation."
        print_info "Start manually: cd $INSTALL_DIR && $VENV_PYTHON bot.py"
        return 0
    fi

    local current_user
    current_user=$(whoami)
    local service_file="/etc/systemd/system/$SERVICE_NAME.service"
    local sudo_prefix=""

    if [ "$EUID" -ne 0 ]; then
        if ! command -v sudo &>/dev/null; then
            print_err "sudo is required to install the systemd service."
            print_info "Re-run this script as root, or install sudo."
            return 1
        fi
        sudo_prefix="sudo"
    fi

    start_spinner "Writing service file to $service_file..."
    $sudo_prefix tee "$service_file" > /dev/null << EOF
[Unit]
Description=Madix Telegram Shop Bot
Documentation=file://$INSTALL_DIR/README.md
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$current_user
WorkingDirectory=$INSTALL_DIR
ExecStart=$VENV_PYTHON $INSTALL_DIR/bot.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=madix-bot
EnvironmentFile=$ENV_FILE

[Install]
WantedBy=multi-user.target
EOF
    stop_spinner $? "Service file written"

    start_spinner "Reloading systemd daemon..."
    $sudo_prefix systemctl daemon-reload >/dev/null 2>&1
    stop_spinner $? "systemd daemon reloaded"

    start_spinner "Enabling $SERVICE_NAME for auto-start on boot..."
    $sudo_prefix systemctl enable "$SERVICE_NAME" >/dev/null 2>&1
    stop_spinner $? "Service enabled"

    echo ""
    if confirm "Start the bot now?"; then
        start_spinner "Starting $SERVICE_NAME..."
        $sudo_prefix systemctl start "$SERVICE_NAME" >/dev/null 2>&1
        sleep 2
        if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
            stop_spinner 0 "Bot is running!"
        else
            stop_spinner 1 "Bot failed to start"
            print_info "Check logs: ./madix.sh logs"
        fi
    fi
}

# ─── Step 7: Finalize ─────────────────────────────────────────────────────────
finalize() {
    # Make management script executable
    if [ -f "$INSTALL_DIR/madix.sh" ]; then
        chmod +x "$INSTALL_DIR/madix.sh"
    fi

    # Install global 'madix' command
    local _target="/usr/local/bin/madix"
    if [ -f "$INSTALL_DIR/madix.sh" ]; then
        local _ln_ok=false
        if [ "$EUID" -eq 0 ]; then
            ln -sf "$INSTALL_DIR/madix.sh" "$_target" && chmod +x "$_target" && _ln_ok=true
        elif command -v sudo &>/dev/null; then
            sudo ln -sf "$INSTALL_DIR/madix.sh" "$_target" && sudo chmod +x "$_target" && _ln_ok=true
        else
            ln -sf "$INSTALL_DIR/madix.sh" "$_target" && chmod +x "$_target" && _ln_ok=true
        fi
        if [ "$_ln_ok" = true ]; then
            # Flush bash's command path cache so the new command is found immediately
            hash -r 2>/dev/null || true
            print_success "Global command installed: type ${CYAN}madix${NC} anywhere to manage your bot."
        else
            print_warning "Could not install global command. Run manually: sudo ln -sf \"$INSTALL_DIR/madix.sh\" $_target"
        fi
    fi

    echo ""
    echo ""
    echo -e "${GREEN}  ╔══════════════════════════════════════════════════════════╗"
    echo    "  ║                                                          ║"
    echo    "  ║               🎉  Installation Complete!                ║"
    echo    "  ║                                                          ║"
    echo -e "  ╚══════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  ${BOLD}Manage your bot with:${NC}"
    echo ""
    echo -e "    ${CYAN}madix${NC}                → Interactive management menu (global)"
    echo -e "    ${CYAN}madix status${NC}         → Detailed status dashboard"
    echo -e "    ${CYAN}madix start${NC}          → Start the bot"
    echo -e "    ${CYAN}madix stop${NC}           → Stop the bot"
    echo -e "    ${CYAN}madix restart${NC}        → Restart the bot"
    echo -e "    ${CYAN}madix logs${NC}           → Stream live logs"
    echo -e "    ${CYAN}madix config${NC}         → Edit configuration"
    echo -e "    ${CYAN}madix update${NC}         → Pull updates & restart"
    echo ""
    echo -e "  ${DIM}Install directory: $INSTALL_DIR${NC}"
    echo ""
}

# ─── Main ─────────────────────────────────────────────────────────────────────
main() {
    print_banner

    echo -e "  ${DIM}Install directory: $INSTALL_DIR${NC}"
    echo ""

    check_requirements
    check_existing
    setup_venv
    install_deps
    configure_env
    setup_service
    finalize
}

main "$@"
