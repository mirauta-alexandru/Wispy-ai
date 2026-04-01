#!/usr/bin/env bash
set -e

BOLD='\033[1m'
DIM='\033[2m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

REPO="https://github.com/mirauta-alexandru/Wispy-ai"
INSTALL_DIR="$HOME/.wispy-ai"
BIN_DIR="$INSTALL_DIR/bin"
SRC_DIR="$INSTALL_DIR/src"

echo ""
echo -e "${BOLD}  wispy-ai — Terminal Autocomplete${NC}"
echo -e "${DIM}  Fast, offline, learns how you type${NC}"
echo ""

step() { echo -e "\n${CYAN}=>${NC} ${BOLD}$1${NC}"; }

# ── Detectie OS + arhitectura ────────────────────────────────────────────────

step "Detecting system"

OS=""
ARCH=""

case "$(uname -s)" in
    Darwin)
        OS="macos"
        ARCH=$(uname -m)
        if [[ "$ARCH" != "arm64" ]]; then
            echo -e "${RED}Error:${NC} Only Apple Silicon (arm64) is supported on macOS."
            exit 1
        fi
        ;;
    Linux)
        OS="linux"
        ARCH=$(uname -m)
        case "$ARCH" in
            x86_64)          ARCH="x86_64" ;;
            aarch64|arm64)   ARCH="arm64" ;;
            *)
                echo -e "${RED}Error:${NC} Unsupported architecture: $ARCH"
                exit 1
                ;;
        esac
        ;;
    *)
        echo -e "${RED}Error:${NC} Unsupported OS: $(uname -s)"
        exit 1
        ;;
esac

echo -e "  ${GREEN}✓${NC} OS: $OS  Arch: $ARCH"

# ── Detectie shell ────────────────────────────────────────────────────────────

CURRENT_SHELL=$(basename "$SHELL")
echo -e "  ${GREEN}✓${NC} Shell: $CURRENT_SHELL"

case "$CURRENT_SHELL" in
    zsh|bash|fish) ;;
    *)
        echo -e "  ${YELLOW}Warning:${NC} Shell '$CURRENT_SHELL' not fully supported. Defaulting to bash plugin."
        CURRENT_SHELL="bash"
        ;;
esac

# ── Dependinte ────────────────────────────────────────────────────────────────

step "Checking dependencies"

if ! command -v git &>/dev/null; then
    echo -e "${RED}Error:${NC} git is required."
    [[ "$OS" == "macos" ]] && echo "  xcode-select --install" || echo "  sudo apt install git / sudo yum install git"
    exit 1
fi

if ! command -v unzip &>/dev/null; then
    echo -e "${YELLOW}unzip not found — installing...${NC}"
    if command -v apt-get &>/dev/null; then
        sudo apt-get install -y unzip
    elif command -v yum &>/dev/null; then
        sudo yum install -y unzip
    elif command -v pacman &>/dev/null; then
        sudo pacman -S --noconfirm unzip
    else
        echo -e "${RED}Error:${NC} Please install unzip manually."
        exit 1
    fi
fi

if ! command -v cargo &>/dev/null; then
    echo -e "${YELLOW}Rust not found — installing...${NC}"
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --no-modify-path
    source "$HOME/.cargo/env"
fi

echo -e "  ${GREEN}✓${NC} git, unzip, rust"

# ── Sursa ────────────────────────────────────────────────────────────────────

step "Fetching source"

mkdir -p "$BIN_DIR" "$INSTALL_DIR/models"

if [[ -d "$SRC_DIR/.git" ]]; then
    git -C "$SRC_DIR" remote set-url origin "$REPO" 2>/dev/null
    git -C "$SRC_DIR" pull --quiet
    echo -e "  ${GREEN}✓${NC} Updated"
else
    git clone --quiet "$REPO" "$SRC_DIR"
    echo -e "  ${GREEN}✓${NC} Cloned"
fi

# ── Build ────────────────────────────────────────────────────────────────────

step "Building wispy engine"

cd "$SRC_DIR/ai-native/core"
cargo build --release --quiet
cp target/release/ai-native "$BIN_DIR/wispy"
echo -e "  ${GREEN}✓${NC} Binary built → $BIN_DIR/wispy"

# ── Instalare plugin shell ────────────────────────────────────────────────────

step "Installing $CURRENT_SHELL plugin"

case "$CURRENT_SHELL" in
    zsh)
        cp "$SRC_DIR/wispy.zsh" "$INSTALL_DIR/wispy.zsh"
        SOURCE_LINE="source $INSTALL_DIR/wispy.zsh"
        RC_FILE="$HOME/.zshrc"
        if grep -q "wispy" "$RC_FILE" 2>/dev/null; then
            sed -i.bak "s|source.*wispy\.zsh|$SOURCE_LINE|" "$RC_FILE"
            echo -e "  ${GREEN}✓${NC} Plugin updated in .zshrc"
        else
            { echo ""; echo "# wispy-ai"; echo "$SOURCE_LINE"; } >> "$RC_FILE"
            echo -e "  ${GREEN}✓${NC} Plugin added to .zshrc"
        fi
        ;;
    bash)
        cp "$SRC_DIR/wispy.bash" "$INSTALL_DIR/wispy.bash"
        SOURCE_LINE="source $INSTALL_DIR/wispy.bash"
        RC_FILE="$HOME/.bashrc"
        if grep -q "wispy" "$RC_FILE" 2>/dev/null; then
            sed -i.bak "s|source.*wispy\.bash|$SOURCE_LINE|" "$RC_FILE"
            echo -e "  ${GREEN}✓${NC} Plugin updated in .bashrc"
        else
            { echo ""; echo "# wispy-ai"; echo "$SOURCE_LINE"; } >> "$RC_FILE"
            echo -e "  ${GREEN}✓${NC} Plugin added to .bashrc"
        fi
        ;;
    fish)
        mkdir -p "$HOME/.config/fish/conf.d"
        cp "$SRC_DIR/wispy.fish" "$HOME/.config/fish/conf.d/wispy.fish"
        echo -e "  ${GREEN}✓${NC} Plugin installed in fish/conf.d"
        ;;
esac

# ── Pornire model AI ─────────────────────────────────────────────────────────

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

# ── Done ─────────────────────────────────────────────────────────────────────

echo ""
echo -e "${BOLD}${GREEN}  Done!${NC}"
echo ""

case "$CURRENT_SHELL" in
    zsh)  echo -e "  Reload: ${CYAN}source ~/.zshrc${NC}" ;;
    bash) echo -e "  Reload: ${CYAN}source ~/.bashrc${NC}" ;;
    fish) echo -e "  Reload: ${CYAN}exec fish${NC}" ;;
esac

echo ""
echo -e "  ${DIM}wispy start · wispy stop · wispy status${NC}"
echo -e "  ${DIM}zsh/fish: sugestie apare automat · bash: Ctrl+N${NC}"
echo ""
