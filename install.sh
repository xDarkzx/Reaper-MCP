#!/bin/bash
set -euo pipefail

# Ensure PATH covers Homebrew on both Intel and Apple Silicon Macs so brew/python3
# are findable even when this is launched from Finder (which strips PATH).
if [[ "${OSTYPE:-}" == "darwin"* ]]; then
    if [ -x /opt/homebrew/bin/brew ]; then
        export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:$PATH"
    fi
    if [ -x /usr/local/bin/brew ]; then
        export PATH="/usr/local/bin:/usr/local/sbin:$PATH"
    fi
fi

echo ""
echo " ============================================"
echo "  ReaperMCP - One-Click Installer"
echo "  AI-powered music production in REAPER"
echo " ============================================"
echo ""
echo "  Platform: $(uname -s) $(uname -m)"
echo ""

# ── Check Python ──────────────────────────────────────────
echo "[1/4] Checking Python..."
if command -v python3 &> /dev/null; then
    PYTHON=python3
elif command -v python &> /dev/null; then
    PYTHON=python
else
    echo ""
    echo " Python is not installed."
    echo ""
    read -rp " Would you like to install Python now? (y/n): " INSTALL_PY
    if [[ "$INSTALL_PY" =~ ^[Yy]$ ]]; then
        if [[ "$OSTYPE" == "darwin"* ]]; then
            if command -v brew &> /dev/null; then
                echo " Installing Python via Homebrew..."
                brew install python3
            else
                echo " Homebrew not found. Install it first:"
                echo "   /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
                echo " Then run this installer again."
                exit 1
            fi
        else
            if command -v apt &> /dev/null; then
                echo " Installing Python via apt..."
                sudo apt update && sudo apt install -y python3 python3-pip
            elif command -v dnf &> /dev/null; then
                echo " Installing Python via dnf..."
                sudo dnf install -y python3 python3-pip
            elif command -v pacman &> /dev/null; then
                echo " Installing Python via pacman..."
                sudo pacman -S --noconfirm python python-pip
            else
                echo " Could not detect your package manager."
                echo " Install Python 3.10+ manually: https://www.python.org/downloads/"
                exit 1
            fi
        fi
        # Re-detect after install
        if command -v python3 &> /dev/null; then
            PYTHON=python3
        elif command -v python &> /dev/null; then
            PYTHON=python
        else
            echo ""
            echo " ERROR: Python install succeeded but python3 not found in PATH."
            echo " Close and reopen your terminal, then run this installer again."
            exit 1
        fi
    else
        echo ""
        echo " ReaperMCP requires Python 3.10+ to run."
        echo " Install it and come back!"
        echo ""
        echo "   macOS:  brew install python3"
        echo "   Ubuntu: sudo apt install python3 python3-pip"
        echo "   Or:     https://www.python.org/downloads/"
        echo ""
        exit 1
    fi
fi

PYVER=$($PYTHON --version 2>&1)
echo "  Found $PYVER"

# Verify Python >= 3.10
PY_MAJOR=$($PYTHON -c "import sys; print(sys.version_info.major)")
PY_MINOR=$($PYTHON -c "import sys; print(sys.version_info.minor)")
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    echo ""
    echo " ERROR: Python 3.10+ is required, but you have $PYVER"
    echo " Please upgrade Python: https://www.python.org/downloads/"
    echo ""
    exit 1
fi

# Warn if running inside a virtual environment
if [ -n "${VIRTUAL_ENV:-}" ]; then
    echo ""
    echo " WARNING: You are inside a virtual environment."
    echo " reaper-mcp should be installed globally so Claude Desktop can find it."
    echo " Deactivate your venv first: deactivate"
    echo ""
    exit 1
fi

# ── Install reaper-mcp ────────────────────────────────────
echo ""
echo "[2/4] Installing reaper-mcp..."

# Check if pip is available
if ! $PYTHON -m pip --version &> /dev/null; then
    echo "  pip not found, installing pip..."
    if ! $PYTHON -m ensurepip --upgrade &> /dev/null; then
        echo ""
        echo " ERROR: pip is not installed and ensurepip failed."
        echo " Try: $PYTHON -m ensurepip --upgrade"
        echo " Or reinstall Python with pip enabled."
        echo ""
        exit 1
    fi
fi

# Install from local directory (not on PyPI yet).
# Many modern Pythons (Homebrew on macOS, Debian/Ubuntu, Fedora) ship with
# PEP 668 "externally-managed" protection that blocks global pip installs.
# Try a normal install first; if it fails with that error, retry with --user.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

install_log=$(mktemp)
if $PYTHON -m pip install -e "$SCRIPT_DIR" 2>"$install_log"; then
    rm -f "$install_log"
    echo "  reaper-mcp installed successfully!"
elif grep -qE "externally-managed|error: could not install" "$install_log"; then
    echo "  System pip is externally managed — retrying with --user..."
    if ! $PYTHON -m pip install --user -e "$SCRIPT_DIR"; then
        cat "$install_log"
        rm -f "$install_log"
        echo ""
        echo " ERROR: pip install --user also failed."
        echo " Try: pipx install -e $SCRIPT_DIR"
        echo ""
        exit 1
    fi
    rm -f "$install_log"
    echo "  reaper-mcp installed to user site-packages."
    # Make sure ~/.local/bin is on PATH so Claude Desktop finds reaper-mcp
    USER_BIN="$($PYTHON -m site --user-base)/bin"
    if [ -d "$USER_BIN" ] && [[ ":$PATH:" != *":$USER_BIN:"* ]]; then
        echo ""
        echo "  NOTE: $USER_BIN is not on your PATH."
        echo "  Add this line to your ~/.bashrc or ~/.zshrc:"
        echo "    export PATH=\"$USER_BIN:\$PATH\""
        echo ""
    fi
else
    cat "$install_log"
    rm -f "$install_log"
    echo ""
    echo " ERROR: pip install failed. See error above."
    echo " If you see 'externally-managed', install pipx and retry with:"
    echo "   pipx install -e $SCRIPT_DIR"
    echo ""
    exit 1
fi

# ── Configure Claude Desktop ──────────────────────────────
echo ""
echo "[3/4] Configuring Claude Desktop..."

read -rp "  Configure Claude Desktop for ReaperMCP? (y/n): " CONFIGURE_CLAUDE
if [[ ! "$CONFIGURE_CLAUDE" =~ ^[Yy]$ ]]; then
    echo "  Skipped. See docs/INSTALLATION.md for manual setup."
else
    if [[ "$OSTYPE" == "darwin"* ]]; then
        CONFIG_DIR="$HOME/Library/Application Support/Claude"
    else
        CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/Claude"
    fi
    CONFIG_FILE="$CONFIG_DIR/claude_desktop_config.json"

    mkdir -p "$CONFIG_DIR"

    if [ -f "$CONFIG_FILE" ]; then
        if grep -q '"reaper"' "$CONFIG_FILE" 2>/dev/null; then
            echo "  Claude Desktop config already has reaper entry - skipping."
        else
            # Back up existing config
            cp "$CONFIG_FILE" "$CONFIG_FILE.bak"
            echo "  Backed up existing config to: $CONFIG_FILE.bak"
            echo ""
            echo "  Found existing Claude Desktop config at:"
            echo "  $CONFIG_FILE"
            echo ""
            echo "  Add this inside your \"mcpServers\" block:"
            echo ""
            echo '    "reaper": {'
            echo '      "command": "reaper-mcp"'
            echo '    }'
            echo ""
        fi
    else
        cat > "$CONFIG_FILE" << 'EOF'
{
  "mcpServers": {
    "reaper": {
      "command": "reaper-mcp"
    }
  }
}
EOF
        chmod 600 "$CONFIG_FILE"
        echo "  Created Claude Desktop config at:"
        echo "  $CONFIG_FILE"
    fi
fi

# ── Done ──────────────────────────────────────────────────
echo ""
echo "[4/4] Done!"
echo ""
echo " ============================================"
echo "  SETUP COMPLETE!"
echo " ============================================"
echo ""
echo " Next steps:"
echo ""
echo "  1. Open REAPER"
echo "  2. Load the Lua script:"
echo "     Actions > Show action list > Load ReaScript..."
echo "     Select: reaper_scripts/reaper_mcp_server.lua"
echo "     Click \"Run\""
echo "  3. Restart Claude Desktop (if it's open)"
echo "  4. Ask Claude: \"Get info about the current REAPER project\""
echo ""
echo " The Lua script must be running in REAPER for MCP to work."
echo " You only need to load it once - REAPER remembers it."
echo ""
echo " Docs: https://github.com/xDarkzx/Reaper-MCP"
echo " ============================================"
echo ""
