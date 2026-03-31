#!/usr/bin/env bash
set -e

BOLD='\033[1m'
DIM='\033[2m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

REPO="https://github.com/mirautaalexandru/wispy-ai"
INSTALL_DIR="$HOME/.wispy-ai"
BIN_DIR="$INSTALL_DIR/bin"
SRC_DIR="$INSTALL_DIR/src"
ZSHRC="$HOME/.zshrc"

echo ""
echo -e "${BOLD}  wispy-ai — Terminal Autocomplete${NC}"
echo -e "${DIM}  Fast, offline, learns how you type${NC}"
echo ""

if [[ "$OSTYPE" != "darwin"* ]]; then
    echo -e "${RED}Error:${NC} Only macOS is supported at this time."
    exit 1
fi

step() { echo -e "\n${CYAN}=>${NC} ${BOLD}$1${NC}"; }

step "Checking dependencies"

if ! command -v git &>/dev/null; then
    echo -e "${RED}Error:${NC} git is required. Install Xcode Command Line Tools:"
    echo "  xcode-select --install"
    exit 1
fi

if ! command -v cargo &>/dev/null; then
    echo -e "${YELLOW}Rust not found — installing...${NC}"
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --no-modify-path
    source "$HOME/.cargo/env"
fi

echo -e "  ${GREEN}✓${NC} git, rust"

step "Fetching source"

mkdir -p "$BIN_DIR" "$INSTALL_DIR/models"

if [[ -d "$SRC_DIR/.git" ]]; then
    git -C "$SRC_DIR" pull --quiet
    echo -e "  ${GREEN}✓${NC} Updated"
else
    git clone --quiet "$REPO" "$SRC_DIR"
    echo -e "  ${GREEN}✓${NC} Cloned"
fi

step "Building wispy engine"

cd "$SRC_DIR/ai-native/core"
cargo build --release --quiet
cp target/release/ai-native "$BIN_DIR/wispy"
echo -e "  ${GREEN}✓${NC} Binary built → $BIN_DIR/wispy"

step "Installing ZSH plugin"

cp "$SRC_DIR/wispy.zsh" "$INSTALL_DIR/wispy.zsh"

SOURCE_LINE="source $INSTALL_DIR/wispy.zsh"

if grep -q "wispy" "$ZSHRC" 2>/dev/null; then
    sed -i '' "s|source.*wispy\.zsh|$SOURCE_LINE|" "$ZSHRC"
    echo -e "  ${GREEN}✓${NC} Plugin updated in .zshrc"
else
    {
        echo ""
        echo "# wispy-ai — Terminal Autocomplete"
        echo "$SOURCE_LINE"
    } >> "$ZSHRC"
    echo -e "  ${GREEN}✓${NC} Plugin added to .zshrc"
fi

step "Starting AI model"
echo -e "  ${DIM}Downloading Qwen 0.5B + llama.cpp engine (~600 MB, runs in background)${NC}"

"$BIN_DIR/wispy" --daemon &

for i in {1..5}; do
    if nc -z 127.0.0.1 11435 2>/dev/null; then
        echo -e "  ${GREEN}✓${NC} AI model running"
        break
    fi
    sleep 1
done

echo ""
echo -e "${BOLD}${GREEN}  Done!${NC}"
echo ""
echo -e "  Restart your terminal or run:"
echo -e "  ${CYAN}source ~/.zshrc${NC}"
echo ""
echo -e "  ${DIM}wispy start · wispy stop · wispy status${NC}"
echo -e "  ${DIM}Accept suggestions with Tab or Ctrl+N${NC}"
echo ""
