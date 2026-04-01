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

Then reload your shell:

```bash
source ~/.zshrc
```

> **Requirements:** macOS Apple Silicon · zsh · ~600 MB disk space

---

## How it works

1. **You type** — a gray suggestion appears after your cursor
2. **Press `Tab`** to accept, or keep typing to ignore
3. **It learns** — every accepted command is saved and returned instantly next time
4. **It corrects** — typos like `gti sta` are recognized and show `→ git status`

The AI model ([Qwen2.5-Coder-0.5B](https://huggingface.co/Qwen/Qwen2.5-Coder-0.5B-Instruct-GGUF)) runs locally via [llama.cpp](https://github.com/ggerganov/llama.cpp). First run downloads ~600 MB. After that, everything is offline.

---

## Usage

Just type — suggestions appear automatically in gray.

| Key | Action |
|-----|--------|
| `Tab` | Accept suggestion |
| `Ctrl+N` | Accept suggestion |
| Any other key | Dismiss and keep typing |

### Commands

```bash
wispy start    # Start the AI model
wispy stop     # Stop the AI model
wispy status   # Check if running
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

## Uninstall

```bash
sed -i '' '/wispy/d' ~/.zshrc
rm -rf ~/.wispy-ai
```

---

## Technical details

| Component | Details |
|-----------|---------|
| AI model | Qwen2.5-Coder-0.5B-Instruct (Q4_K_M, ~300 MB) |
| Engine | llama.cpp (llama-server, local HTTP API on port 11435) |
| Memory | JSON file at `~/.wispy-ai/memory.json` |
| Language | Rust (wispy binary) + Zsh (plugin) |
| Platform | macOS Apple Silicon |
| Network | None after initial download |

---

## License

MIT
