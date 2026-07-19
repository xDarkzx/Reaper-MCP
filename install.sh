#!/bin/bash
set -euo pipefail

# Ensure PATH covers Homebrew on both Intel and Apple Silicon Macs so brew/python3
# are findable even when this is launched from Finder (which strips PATH).
if [[ "${OSTYPE:-}" == "darwin"* ]]; then
    # Process Intel first, Apple Silicon second: each iteration prepends, so
    # the last one processed ends up first. That makes /opt/homebrew win by
    # default when neither is already on PATH (e.g. launched from Finder,
    # which strips PATH) — the correct default on Apple Silicon — while the
    # "already on PATH" check below means a user's own correctly-ordered
    # shell PATH is never touched either way.
    for hb in /usr/local /opt/homebrew; do
        if [ -x "$hb/bin/brew" ] && [[ ":$PATH:" != *":$hb/bin:"* ]]; then
            export PATH="$hb/bin:$hb/sbin:$PATH"
        fi
    done
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
echo "[1/5] Checking Python..."
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
        if [[ "${OSTYPE:-}" == "darwin"* ]]; then
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
echo "[2/5] Installing reaper-mcp..."

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

# Verify the 'reaper-mcp' command on PATH actually points at the Python we
# just installed with — not a stale install from a different Python (e.g.
# an old Intel-Homebrew reaper-mcp shadowing a fresh Apple-Silicon one, or
# any other case of two Pythons on the same machine). Claude Desktop will
# run whatever 'reaper-mcp' resolves to, which may not be what this script
# just set up.
RESOLVED_CMD="$(command -v reaper-mcp 2>/dev/null || true)"
if [ -z "$RESOLVED_CMD" ]; then
    echo ""
    echo "  NOTE: 'reaper-mcp' isn't on PATH yet in this shell session."
    echo "  Open a new terminal (or source your shell rc file) before asking"
    echo "  Claude to use it — Claude Desktop launches commands using your"
    echo "  normal shell PATH, so if it doesn't resolve here, it won't there."
elif [ -f "$RESOLVED_CMD" ] && head -1 "$RESOLVED_CMD" 2>/dev/null | grep -q '^#!'; then
    SHEBANG_PY="$(head -1 "$RESOLVED_CMD" | sed 's/^#!//' | awk '{print $1}')"
    ACTUAL_PY="$($PYTHON -c 'import sys; print(sys.executable)')"
    if [ -n "$SHEBANG_PY" ] && [ "$SHEBANG_PY" != "$ACTUAL_PY" ]; then
        echo ""
        echo "  WARNING: 'reaper-mcp' on your PATH is bound to a DIFFERENT"
        echo "  Python than the one just used to install it:"
        echo "    On PATH now: $SHEBANG_PY"
        echo "    Just used:   $ACTUAL_PY"
        echo "  This usually means an older reaper-mcp install (a different"
        echo "  Homebrew Python, a previous global pip install, etc.) is"
        echo "  shadowing the one just installed. Run 'echo \$PATH' and check"
        echo "  which directory containing 'reaper-mcp' comes first, or run"
        echo "  'which -a reaper-mcp' to see every copy on PATH."
        echo ""
    fi
fi

# ── Set up REAPER auto-start ──────────────────────────────
# REAPER auto-runs any script literally named __startup.lua found in its
# Scripts resource folder, on every launch, with no Action-list registration
# needed. This removes the "load the Lua script every time REAPER opens"
# manual step for anyone who runs this installer.
echo ""
echo "[3/5] Setting up REAPER auto-start..."

if [[ "${OSTYPE:-}" == "darwin"* ]]; then
    REAPER_RESOURCE_DIR="$HOME/Library/Application Support/REAPER"
else
    REAPER_RESOURCE_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/REAPER"
fi
REAPER_SCRIPTS_DIR="$REAPER_RESOURCE_DIR/Scripts"
STARTUP_SCRIPT="$REAPER_SCRIPTS_DIR/__startup.lua"
LOAD_LINE="dofile([[$SCRIPT_DIR/reaper_scripts/reaper_mcp_server.lua]])"

if [ ! -d "$REAPER_SCRIPTS_DIR" ]; then
    echo "  REAPER hasn't been run yet (no Scripts folder found) — skipping."
    echo "  Run REAPER once, then re-run this installer to enable auto-start,"
    echo "  or load the script manually (see the final instructions below)."
elif [ -f "$STARTUP_SCRIPT" ] && grep -qF "reaper_mcp_server.lua" "$STARTUP_SCRIPT" 2>/dev/null; then
    echo "  Auto-start already configured — skipping."
elif [ -f "$STARTUP_SCRIPT" ]; then
    # A startup script already exists for something else — append rather
    # than overwrite it, so we don't clobber the user's own setup.
    cp "$STARTUP_SCRIPT" "$STARTUP_SCRIPT.bak"
    {
        echo ""
        echo "-- Added by the ReaperMCP installer"
        echo "reaper.defer(function() reaper.defer(function() $LOAD_LINE end) end)"
    } >> "$STARTUP_SCRIPT"
    echo "  Found an existing __startup.lua — backed it up to __startup.lua.bak"
    echo "  and appended ReaperMCP's auto-start to the end of it."
else
    cat > "$STARTUP_SCRIPT" << EOF
-- Auto-start ReaperMCP server on REAPER launch.
-- Double-defer ensures REAPER is fully initialized first.
reaper.defer(function()
  reaper.defer(function()
    $LOAD_LINE
  end)
end)
EOF
    echo "  Created: $STARTUP_SCRIPT"
    echo "  ReaperMCP will now load automatically every time REAPER starts."
fi

# ── Configure Claude Desktop ──────────────────────────────
echo ""
echo "[4/5] Configuring Claude Desktop..."

read -rp "  Configure Claude Desktop for ReaperMCP? (y/n): " CONFIGURE_CLAUDE
if [[ ! "$CONFIGURE_CLAUDE" =~ ^[Yy]$ ]]; then
    echo "  Skipped. See docs/INSTALLATION.md for manual setup."
else
    if [[ "${OSTYPE:-}" == "darwin"* ]]; then
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
echo "[5/5] Done!"
echo ""
echo " ============================================"
echo "  SETUP COMPLETE!"
echo " ============================================"
echo ""
if [ -f "$STARTUP_SCRIPT" ] && grep -qF "reaper_mcp_server.lua" "$STARTUP_SCRIPT" 2>/dev/null; then
    echo " Next steps:"
    echo ""
    echo "  1. Open REAPER (or restart it if it's already open) — ReaperMCP"
    echo "     loads automatically now, nothing to click."
    echo "  2. Restart Claude Desktop (if it's open)"
    echo "  3. Ask Claude: \"Get info about the current REAPER project\""
    echo ""
else
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
fi
echo " Docs: https://github.com/xDarkzx/Reaper-MCP"
echo " ============================================"
echo ""
