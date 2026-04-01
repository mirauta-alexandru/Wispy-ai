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

# ── Ctrl+N: accepta sugestia wispy ───────────────────────────────────────────
# Tab ramane pentru completarea normala bash

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

    # Invata comanda acceptata
    "$_WISPY_BIN" --learn "$buf" "$ghost" "$PWD" >/dev/null 2>&1 &
}

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
                current) echo "Model activ: $("$_WISPY_BIN" --model-current)" ;;
                set)
                    [[ -z "$3" ]] && { echo "Folosire: wispy model set <nume.gguf>"; return 1; }
                    "$_WISPY_BIN" --model-set "$3"
                    ;;
                *)
                    echo "Model activ: $("$_WISPY_BIN" --model-current)"
                    echo "Comenzi: wispy model list | set <nume> | current"
                    ;;
            esac
            ;;
        memory)
            case "$2" in
                clear)
                    read -p "Stergi toata memoria? [y/N] " reply
                    [[ "$reply" =~ ^[Yy]$ ]] && "$_WISPY_BIN" --memory-clear || echo "Anulat."
                    ;;
                forget)
                    [[ -z "$3" ]] && { echo "Folosire: wispy memory forget <comanda>"; return 1; }
                    "$_WISPY_BIN" --memory-forget "$3"
                    ;;
                *)
                    "$_WISPY_BIN" --memory-stats
                    echo ""
                    echo "Comenzi: wispy memory forget <cmd> | clear"
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
