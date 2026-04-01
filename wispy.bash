# wispy-ai — Terminal Autocomplete Bash Plugin
# https://github.com/mirauta-alexandru/Wispy-ai

if [[ -x "$HOME/.wispy-ai/bin/wispy" ]]; then
    _WISPY_BIN="$HOME/.wispy-ai/bin/wispy"
else
    _WISPY_BIN="${BASH_SOURCE[0]%/*}/ai-native/core/target/release/ai-native"
fi

if [[ ! -x "$_WISPY_BIN" ]]; then
    echo "wispy: binary not found. Run the installer." >&2
    return 1
fi

# Porneste daemon la deschiderea shellului
"$_WISPY_BIN" --daemon >/dev/null 2>&1 &

# ── Ctrl+N: accept wispy suggestion ─────────────────────────────────────────

_wispy_complete() {
    local buf="${READLINE_LINE}"
    [[ -z "$buf" ]] && return

    local output
    output=$("$_WISPY_BIN" "$buf" "$PWD" 2>/dev/null)
    [[ -z "$output" ]] && return

    local ghost correction
    ghost="${output%%$'\n'*}"
    correction="${output#*$'\n'}"

    if [[ "$output" == *$'\n'* && "$correction" != "$ghost" ]]; then
        # Corectie typo
        READLINE_LINE="$correction"
    else
        READLINE_LINE="${buf}${ghost}"
    fi
    READLINE_POINT=${#READLINE_LINE}

    # Learn the accepted command
    "$_WISPY_BIN" --learn "$buf" "$ghost" "$PWD" >/dev/null 2>&1 &
}

_wispy_tab() {
    local buf="${READLINE_LINE}"

    # Empty line — fall back to file/command completion
    if [[ -z "$buf" ]]; then
        _wispy_fallback
        return
    fi

    local output
    output=$("$_WISPY_BIN" "$buf" "$PWD" 2>/dev/null)

    if [[ -n "$output" ]]; then
        # wispy has a suggestion — apply it
        _wispy_complete
    else
        # no suggestion — fall back to normal bash completion
        _wispy_fallback
    fi
}

_wispy_fallback() {
    # Completare simpla: fisiere si comenzi
    local buf="${READLINE_LINE}"
    local -a completions
    mapfile -t completions < <(compgen -f -- "$buf" 2>/dev/null)
    [[ ${#completions[@]} -eq 0 ]] && mapfile -t completions < <(compgen -c -- "$buf" 2>/dev/null)

    if [[ ${#completions[@]} -eq 1 ]]; then
        READLINE_LINE="${completions[0]}"
        READLINE_POINT=${#READLINE_LINE}
    elif [[ ${#completions[@]} -gt 1 ]]; then
        echo ""
        printf '%s  ' "${completions[@]}"
        echo ""
        echo -n "${PS1@P}${READLINE_LINE}"
    fi
}

bind -x '"\t":  _wispy_tab'
bind -x '"\C-n": _wispy_complete'

# ── Comanda wispy ─────────────────────────────────────────────────────────────

wispy() {
    case "$1" in
        start)
            "$_WISPY_BIN" --daemon >/dev/null 2>&1 &
            echo "Wispy starting..."
            ;;
        stop)
            "$_WISPY_BIN" --stop
            ;;
        status)
            local s
            s=$("$_WISPY_BIN" --status)
            [[ "$s" == "running" ]] && echo "Wispy is running" || echo "Wispy is stopped  (run: wispy start)"
            ;;
        model)
            case "$2" in
                list)    "$_WISPY_BIN" --model-list ;;
                current) echo "Active model: $("$_WISPY_BIN" --model-current)" ;;
                set)
                    [[ -z "$3" ]] && { echo "Usage: wispy model set <name.gguf>"; return 1; }
                    "$_WISPY_BIN" --model-set "$3"
                    ;;
                *)
                    echo "Active model: $("$_WISPY_BIN" --model-current)"
                    echo "Commands: wispy model list | set <name> | current"
                    ;;
            esac
            ;;
        memory)
            case "$2" in
                clear)
                    read -p "Clear all memory? [y/N] " reply
                    [[ "$reply" =~ ^[Yy]$ ]] && "$_WISPY_BIN" --memory-clear || echo "Cancelled."
                    ;;
                forget)
                    [[ -z "$3" ]] && { echo "Usage: wispy memory forget <command>"; return 1; }
                    "$_WISPY_BIN" --memory-forget "$3"
                    ;;
                *)
                    "$_WISPY_BIN" --memory-stats
                    echo ""
                    echo "Commands: wispy memory forget <cmd> | clear"
                    ;;
            esac
            ;;
        import-history)
            "$_WISPY_BIN" --import-history
            ;;
        update)
            echo "Updating wispy-ai..."
            local src="$HOME/.wispy-ai/src"
            local bin="$HOME/.wispy-ai/bin/wispy"
            [[ ! -d "$src/.git" ]] && { echo "Source not found. Please reinstall."; return 1; }
            git -C "$src" remote set-url origin https://github.com/mirauta-alexandru/Wispy-ai.git && \
            git -C "$src" pull --quiet && \
            cargo build --release --quiet --manifest-path "$src/ai-native/core/Cargo.toml" && \
            cp "$src/ai-native/core/target/release/ai-native" "$bin" && \
            cp "$src/wispy.bash" "$HOME/.wispy-ai/wispy.bash" && \
            echo "Updated! Run: source ~/.bashrc"
            ;;
        *)
            echo "Usage: wispy [start|stop|status|model|memory|import-history|update]"
            ;;
    esac
}
