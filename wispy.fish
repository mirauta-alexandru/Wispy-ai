# wispy-ai — Terminal Autocomplete Fish Plugin
# https://github.com/mirauta-alexandru/Wispy-ai

if test -x "$HOME/.wispy-ai/bin/wispy"
    set -g _WISPY_BIN "$HOME/.wispy-ai/bin/wispy"
else
    set -g _WISPY_BIN (dirname (status --current-filename))/ai-native/core/target/release/ai-native
end

if not test -x "$_WISPY_BIN"
    echo "wispy: binary not found. Run the installer." >&2
    exit 1
end

set -g _WISPY_SUGGESTION ""
set -g _WISPY_CORRECTION ""

# Porneste daemon la deschiderea shellului
"$_WISPY_BIN" --daemon >/dev/null 2>&1 &

# ── Right prompt: ghost text from memory (instant, no AI) ───────────────────

function fish_right_prompt
    set buf (commandline 2>/dev/null)
    if test (string length "$buf") -lt 2
        return
    end

    set suggestion ("$_WISPY_BIN" --fast "$buf" "$PWD" 2>/dev/null)
    if test -n "$suggestion"
        set_color 244
        printf '%s' $suggestion
        set_color normal
    end
end

# ── Tab / Ctrl+N: accept suggestion (AI fallback if not in memory) ───────────

function _wispy_accept
    set buf (commandline)
    if test -z "$buf"
        commandline -f complete
        return
    end

    # Try memory first — instant
    set suggestion ("$_WISPY_BIN" --fast "$buf" "$PWD" 2>/dev/null)

    # Not in memory — ask the AI
    if test -z "$suggestion"
        set output ("$_WISPY_BIN" "$buf" "$PWD" 2>/dev/null)
        # Typo correction comes back as two lines — take the second one
        if string match -q '*\n*' "$output"
            set suggestion (string split \n "$output")[2]
        else
            set suggestion $output
        end
    end

    if test -n "$suggestion"
        commandline -a "$suggestion"
        commandline -f repaint
    else
        commandline -f complete
    end
end

# ── Invatam din comenzile executate ──────────────────────────────────────────

function _wispy_learn --on-event fish_preexec
    set cmd $argv[1]
    if test (string length "$cmd") -lt 3
        return
    end
    set words (string split ' ' "$cmd")
    if test (count $words) -lt 2
        return
    end
    set input (string join ' ' $words[1..-2])
    set completion " $words[-1]"
    "$_WISPY_BIN" --learn "$input" "$completion" "$PWD" >/dev/null 2>&1 &
end

# ── Curata sugestia cand se executa comanda ───────────────────────────────────

function _wispy_postexec --on-event fish_postexec
    set -g _WISPY_SUGGESTION ""
    set -g _WISPY_CORRECTION ""
end

# ── Key bindings ──────────────────────────────────────────────────────────────

function fish_user_key_bindings
    bind \t _wispy_accept
    bind \cn _wispy_accept
end

# ── Comanda wispy ─────────────────────────────────────────────────────────────

function wispy
    switch $argv[1]
        case start
            "$_WISPY_BIN" --daemon >/dev/null 2>&1 &
            echo "Wispy starting..."
        case stop
            "$_WISPY_BIN" --stop
        case status
            set s ("$_WISPY_BIN" --status)
            if test "$s" = running
                echo "Wispy is running"
            else
                echo "Wispy is stopped  (run: wispy start)"
            end
        case model
            switch $argv[2]
                case list;    "$_WISPY_BIN" --model-list
                case current; echo "Active model: $("$_WISPY_BIN" --model-current)"
                case set
                    if test -z "$argv[3]"
                        echo "Usage: wispy model set <name.gguf>"
                        return 1
                    end
                    "$_WISPY_BIN" --model-set $argv[3]
                case '*'
                    echo "Active model: $("$_WISPY_BIN" --model-current)"
                    echo ""
                    echo "Commands: wispy model list | set <name> | current"
            end
        case memory
            switch $argv[2]
                case clear
                    read --prompt-str "Clear all memory? [y/N] " reply
                    if string match -qi 'y' "$reply"
                        "$_WISPY_BIN" --memory-clear
                    else
                        echo "Cancelled."
                    end
                case forget
                    if test -z "$argv[3]"
                        echo "Usage: wispy memory forget <command>"
                        return 1
                    end
                    "$_WISPY_BIN" --memory-forget $argv[3]
                case '*'
                    "$_WISPY_BIN" --memory-stats
                    echo ""
                    echo "Commands: wispy memory forget <cmd> | clear"
            end
        case import-history
            "$_WISPY_BIN" --import-history
        case update
            echo "Updating wispy-ai..."
            set src "$HOME/.wispy-ai/src"
            set bin "$HOME/.wispy-ai/bin/wispy"
            if not test -d "$src/.git"
                echo "Source not found. Please reinstall."
                return 1
            end
            git -C "$src" remote set-url origin https://github.com/mirauta-alexandru/Wispy-ai.git
            and git -C "$src" pull --quiet
            and cargo build --release --quiet --manifest-path "$src/ai-native/core/Cargo.toml"
            and cp "$src/ai-native/core/target/release/ai-native" "$bin"
            and cp "$src/wispy.fish" "$HOME/.wispy-ai/wispy.fish"
            and echo "Updated! Restart your terminal."
        case '*'
            echo "Usage: wispy [start|stop|status|model|memory|import-history|update]"
    end
end
