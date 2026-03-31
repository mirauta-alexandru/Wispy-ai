# wispy-ai — Terminal Autocomplete ZSH Plugin
# https://github.com/mirautaalexandru/wispy-ai

# Locate binary: installed path takes priority over local dev build
if [[ -x "$HOME/.wispy-ai/bin/wispy" ]]; then
    _WISPY_BIN="$HOME/.wispy-ai/bin/wispy"
else
    _WISPY_BIN="${0:A:h}/ai-native/core/target/release/ai-native"
fi

if [[ ! -x "$_WISPY_BIN" ]]; then
    echo "wispy: binary not found. Run the installer." >&2
    return 1
fi

_WISPY_SUGGESTION=""
_WISPY_CORRECTION=""
_WISPY_RECENT_CMDS=()

# Start daemon in background on shell load
"$_WISPY_BIN" --daemon >/dev/null 2>&1 &!

# ── Control function ────────────────────────────────────────────────────────

function wispy() {
    case "$1" in
        start)
            "$_WISPY_BIN" --daemon >/dev/null 2>&1 &!
            echo "Wispy starting..."
            ;;
        stop)
            "$_WISPY_BIN" --stop
            ;;
        status)
            local s=$("$_WISPY_BIN" --status)
            if [[ "$s" == "running" ]]; then
                echo "Wispy is running"
            else
                echo "Wispy is stopped  (run: wispy start)"
            fi
            ;;
        *)
            echo "Usage: wispy [start|stop|status]"
            ;;
    esac
}

# ── Track recent commands ───────────────────────────────────────────────────

autoload -Uz add-zsh-hook
function _wispy_track_recent() {
    local last_cmd
    last_cmd=$(fc -ln -1 2>/dev/null | sed 's/^[[:space:]]*//')
    if [[ -n "$last_cmd" && "$last_cmd" != "${_WISPY_RECENT_CMDS[1]}" ]]; then
        _WISPY_RECENT_CMDS=("$last_cmd" "${_WISPY_RECENT_CMDS[@]:0:4}")
    fi
}
add-zsh-hook precmd _wispy_track_recent

# ── ZLE widgets ────────────────────────────────────────────────────────────

function _wispy_self_insert() {
    zle .self-insert
    POSTDISPLAY=""
    _WISPY_SUGGESTION=""
    _WISPY_CORRECTION=""
    region_highlight=()

    if [[ ${#BUFFER} -gt 0 ]]; then
        local recent="${(j:|:)_WISPY_RECENT_CMDS}"
        local output
        output=$("$_WISPY_BIN" "$BUFFER" "$PWD" "$recent" 2>/dev/null)

        if [[ -n "$output" ]]; then
            local ghost="${output%%$'\n'*}"
            local correction="${output#*$'\n'}"
            if [[ "$output" == *$'\n'* && "$correction" != "$ghost" ]]; then
                _WISPY_SUGGESTION="$ghost"
                _WISPY_CORRECTION="$correction"
                POSTDISPLAY=" → $_WISPY_CORRECTION"
            else
                _WISPY_SUGGESTION="$output"
                _WISPY_CORRECTION=""
                POSTDISPLAY="$_WISPY_SUGGESTION"
            fi
            region_highlight=("P0 9999 fg=244")
        fi
    fi
}

function _wispy_backward_delete_char() {
    zle .backward-delete-char
    POSTDISPLAY=""
    _WISPY_SUGGESTION=""
    _WISPY_CORRECTION=""
    region_highlight=()
}

function _wispy_accept() {
    if [[ -n "$POSTDISPLAY" && -n "$_WISPY_SUGGESTION" ]]; then
        local input="$BUFFER"
        local completion="$_WISPY_SUGGESTION"

        if [[ -n "$_WISPY_CORRECTION" ]]; then
            BUFFER="$_WISPY_CORRECTION"
        else
            BUFFER="$BUFFER$_WISPY_SUGGESTION"
        fi

        POSTDISPLAY=""
        _WISPY_SUGGESTION=""
        _WISPY_CORRECTION=""
        region_highlight=()
        CURSOR=$#BUFFER
        zle -R

        # Learn only from correct commands, not typo corrections
        if [[ -z "$_WISPY_CORRECTION" ]]; then
            "$_WISPY_BIN" --learn "$input" "$completion" "$PWD" >/dev/null 2>&1 &!
        fi
    else
        zle expand-or-complete
    fi
}

zle -N self-insert           _wispy_self_insert
zle -N backward-delete-char  _wispy_backward_delete_char
zle -N _wispy_accept

# Tab or Ctrl+N to accept
bindkey '^I' _wispy_accept
bindkey '^N' _wispy_accept
