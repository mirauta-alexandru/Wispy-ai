#!/usr/bin/env bash
GRAY=$'\033[38;5;244m'
RESET=$'\033[0m'
BOLD=$'\033[1m'
P="${BOLD}\$${RESET} "

pause() { sleep "${1:-1}"; }

demo() {
    local typed="$1" ghost="$2" full="$3" out="$4"
    echo -n "${P}${typed}"
    pause 1.4
    echo -n "${GRAY}${ghost}${RESET}"
    pause 1.2
    echo -e "\r${P}${full}"
    [[ -n "$out" ]] && echo -e "${GRAY}${out}${RESET}"
    pause 0.9
}

clear
pause 0.4

demo "git s"   "tatus"   "git status"   "On branch main\nnothing to commit, working tree clean"
demo "doc"     "ker ps"  "docker ps"    "CONTAINER ID   IMAGE     STATUS\na1b2c3d4       nginx     Up 3 hours"
demo "gti sta" "tus  →  git status" "git status" "On branch main\nnothing to commit"

pause 1
