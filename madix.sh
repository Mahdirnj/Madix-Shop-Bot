#!/usr/bin/env bash
# =============================================================================
#  madix.sh — Madix Bot Management CLI
#  Usage: ./madix.sh [command]
#  Commands: status | start | stop | restart | logs | config | update | help
# =============================================================================
set -uo pipefail

# ─── Constants ────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="madix-bot"
ENV_FILE="$SCRIPT_DIR/.env"
VENV_PYTHON="$SCRIPT_DIR/venv/bin/python"
VENV_PIP="$SCRIPT_DIR/venv/bin/pip"
REQUIREMENTS_FILE="$SCRIPT_DIR/requirements.txt"
DB_FILE="$SCRIPT_DIR/database.sqlite3"

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
    if [ -n "$pid" ] && [ -f "/proc/$pid/status" ] 2>/dev/null; then
        grep VmRSS "/proc/$pid/status" 2>/dev/null \
            | awk '{printf "%.1f MB", $2/1024}' || echo "N/A"
    else
        echo "N/A"
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

    local status pid mem uptime restarts db_size py_ver masked_token
    status=$(get_service_status)
    pid=$(get_pid)
    mem=$(get_memory "$pid")
    uptime=$(get_uptime)
    restarts=$(get_restarts)
    db_size=$(get_db_size)
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
    printf "    %-18s %s\n"      "Restart Count"   "$restarts"
    echo ""

    echo -e "  ${BOLD}  ▸ System${NC}"
    printf "    %-18s %s\n"  "Database"   "$db_size"
    printf "    %-18s %s\n"  "Python"     "$py_ver"
    printf "    %-18s %s\n"  "Install Dir" "$SCRIPT_DIR"
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
        echo -e "  ${DIM}Streaming live logs for $SERVICE_NAME — press Ctrl+C to exit.${NC}"
        echo ""
        journalctl -u "$SERVICE_NAME" -f --no-pager
    elif [ -f "$SCRIPT_DIR/bot.log" ]; then
        echo -e "  ${DIM}Streaming log file — press Ctrl+C to exit.${NC}"
        echo ""
        tail -f "$SCRIPT_DIR/bot.log"
    else
        printf "  ${YELLOW}⚠${NC}  No log source found.\n"
    fi
    echo ""
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

        new_value="${new_value// /}"  # basic trim
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

    # Pull code if this is a git repo
    if command -v git &>/dev/null && [ -d "$SCRIPT_DIR/.git" ]; then
        printf "  ${CYAN}→${NC}  Pulling latest code from git...\n"
        if git -C "$SCRIPT_DIR" pull 2>&1 | sed 's/^/    /'; then
            printf "  ${GREEN}✓${NC}  Code updated.\n"
        else
            printf "  ${YELLOW}⚠${NC}  git pull failed — continuing with dependency update.\n"
        fi
        echo ""
    else
        printf "  ${DIM}  (Not a git repository — skipping code pull.)${NC}\n"
    fi

    # Update Python dependencies
    if [ -f "$VENV_PIP" ]; then
        printf "  ${CYAN}→${NC}  Updating Python dependencies...\n"
        if "$VENV_PIP" install -r "$REQUIREMENTS_FILE" --upgrade -q 2>&1 | sed 's/^/    /'; then
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

# ─── cmd: help ───────────────────────────────────────────────────────────────
cmd_help() {
    print_banner
    echo -e "  ${BOLD}Usage:${NC}  ./madix.sh [command]"
    echo ""
    echo -e "  ${BOLD}Commands:${NC}"
    echo ""
    printf "    ${CYAN}%-12s${NC}  %s\n" "status"   "Show detailed status dashboard (runtime, config, logs)"
    printf "    ${CYAN}%-12s${NC}  %s\n" "start"    "Start the bot"
    printf "    ${CYAN}%-12s${NC}  %s\n" "stop"     "Stop the bot"
    printf "    ${CYAN}%-12s${NC}  %s\n" "restart"  "Restart the bot"
    printf "    ${CYAN}%-12s${NC}  %s\n" "logs"     "Stream live logs (Ctrl+C to exit)"
    printf "    ${CYAN}%-12s${NC}  %s\n" "config"   "Interactively edit .env configuration"
    printf "    ${CYAN}%-12s${NC}  %s\n" "update"   "Pull latest code + update dependencies"
    printf "    ${CYAN}%-12s${NC}  %s\n" "help"     "Show this help message"
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

        local status status_color
        status=$(get_service_status)
        case "$status" in
            active)   status_color="$GREEN" ;;
            failed)   status_color="$RED" ;;
            *)        status_color="$YELLOW" ;;
        esac

        echo -e "  ${BOLD}  Shop:${NC}  ${SHOP_NAME:-(not configured)}   ${BOLD}|${NC}  Status: ${status_color}${BOLD}${status^}${NC}"
        echo ""
        divider
        echo ""
        printf "    ${CYAN}1${NC}   📊  Status & Details\n"
        printf "    ${CYAN}2${NC}   ▶   Start Bot\n"
        printf "    ${CYAN}3${NC}   ■   Stop Bot\n"
        printf "    ${CYAN}4${NC}   ↺   Restart Bot\n"
        printf "    ${CYAN}5${NC}   📜  View Live Logs\n"
        printf "    ${CYAN}6${NC}   ⚙   Edit Configuration\n"
        printf "    ${CYAN}7${NC}   ↑   Update (git pull + deps)\n"
        echo ""
        printf "    ${CYAN}0${NC}   ✕   Exit\n"
        echo ""
        divider
        echo ""
        printf "  ${BOLD}Choice:${NC} "
        read -r choice

        case "$choice" in
            1) clear; cmd_status;  pause ;;
            2) clear; cmd_start;   pause ;;
            3) clear; cmd_stop;    pause ;;
            4) clear; cmd_restart; pause ;;
            5) clear; cmd_logs ;;
            6) clear; cmd_config ;;
            7) clear; cmd_update;  pause ;;
            0|q|Q) echo ""; exit 0 ;;
            *) printf "  ${RED}✗${NC}  Invalid option.\n"; sleep 1 ;;
        esac
    done
}

# ─── Entry Point ──────────────────────────────────────────────────────────────
CMD="${1:-}"

case "$CMD" in
    "")        cmd_menu ;;
    status)    cmd_status ;;
    start)     cmd_start ;;
    stop)      cmd_stop ;;
    restart)   cmd_restart ;;
    logs)      cmd_logs ;;
    config)    cmd_config ;;
    update)    cmd_update ;;
    help|-h|--help) cmd_help ;;
    *)
        printf "\n  ${RED}✗${NC}  Unknown command: %s\n" "$CMD"
        printf "  Run ${CYAN}./madix.sh help${NC} for available commands.\n\n"
        exit 1
        ;;
esac
