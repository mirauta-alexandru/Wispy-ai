# wispy-ai
<img width="3361" height="1191" alt="Wispy-ai" src="https://github.com/user-attachments/assets/73101dc4-175b-46da-9d54-c1b992be282e" />

> Fast, offline AI-powered autocomplete for your terminal — that learns how you type.

![demo](https://vhs.charm.sh/vhs-1exf3bQFikFWpmVSJKcuKd.gif)

No cloud. No API key. Runs entirely on your machine.

---

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/mirauta-alexandru/Wispy-ai/main/install.sh | bash
```

The installer automatically detects your OS, architecture and shell.

> **Requirements:** macOS Apple Silicon or Linux (x86_64 / arm64) · zsh, bash or fish · ~600 MB disk space

---

## How it works

1. **You type** — a suggestion appears as you type
2. **Press `Tab`** to accept, or keep typing to ignore
3. **It learns** — every accepted command is saved and returned instantly next time
4. **It corrects** — typos like `gti sta` are recognized and show `→ git status`

The AI model ([Qwen2.5-Coder-0.5B](https://huggingface.co/Qwen/Qwen2.5-Coder-0.5B-Instruct-GGUF)) runs locally via [llama.cpp](https://github.com/ggml-org/llama.cpp). First run downloads ~600 MB. After that, everything is offline.

---

## Shell support

| Shell | Experience |
|-------|------------|
| **zsh** | Inline ghost text after cursor, updates on every keystroke |
| **fish** | Ghost text in right prompt, updates on every keystroke |
| **bash** | `Tab` triggers suggestion, `Ctrl+N` as alternative |

---

## Usage

| Key | zsh / fish | bash |
|-----|-----------|------|
| `Tab` | Accept suggestion | Suggest or complete |
| `Ctrl+N` | Accept suggestion | Accept suggestion |

### Commands

```bash
wispy start    # Start the AI model
wispy stop     # Stop the AI model
wispy status   # Check if running
wispy update   # Update to latest version
```

### Model management

```bash
wispy model list              # List available GGUF models
wispy model set <name.gguf>   # Switch active model
wispy model current           # Show active model
```

### Memory

```bash
wispy memory                      # Show stats and top commands
wispy memory forget <command>     # Remove a specific command
wispy memory clear                # Clear all memory
wispy import-history              # Import commands from ~/.zsh_history
```

---

## Memory system

wispy-ai gets smarter the more you use it:

- **Instant recall** — commands accepted 3+ times are returned immediately, no AI needed
- **Context-aware** — knows your current directory; different projects get different suggestions
- **Typo-safe** — typos are never saved to memory, only correct commands are learned
- **Prefix expansion** — type `gi` and get `t status` if that's your pattern

Memory is stored at `~/.wispy-ai/memory.json`.

---

## How memory and AI work together

```
You type: "git s"
          │
          ├─ Exact match in memory (count ≥ 3)?  → instant reply, no AI
          ├─ Starts with a known prefix?          → expand from memory
          ├─ Looks like a typo?                   → fuzzy correct + show "→ git status"
          └─ None of the above?                   → ask local AI with your patterns as hints
```

---

## Using a fine-tuned model

After training your own model and converting it to GGUF:

```bash
# Place the GGUF file in the models directory
cp your-model.gguf ~/.wispy-ai/models/

# Switch to it
wispy model set your-model.gguf

# Restart wispy
wispy stop && wispy start
```

---

## Uninstall

**zsh / bash:**
```bash
sed -i '' '/wispy/d' ~/.zshrc   # or ~/.bashrc
rm -rf ~/.wispy-ai
```

**fish:**
```bash
rm ~/.config/fish/conf.d/wispy.fish
rm -rf ~/.wispy-ai
```

---

## Technical details

| Component | Details |
|-----------|---------|
| AI model | Qwen2.5-Coder-0.5B-Instruct (Q4_K_M, ~300 MB) |
| Engine | llama.cpp (llama-server, local HTTP API on port 11435) |
| Memory | JSON file at `~/.wispy-ai/memory.json` |
| Language | Rust (wispy binary) + zsh / bash / fish plugins |
| Platform | macOS Apple Silicon · Linux x86_64 · Linux arm64 |
| Network | None after initial download |

---

## License

MIT
