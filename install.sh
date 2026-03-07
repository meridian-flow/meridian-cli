#!/usr/bin/env bash
# meridian-channel installer
# Installs uv (if needed) and meridian-channel as a uv tool.
# Usage: curl -LsSf https://raw.githubusercontent.com/haowjy/meridian-channel/main/install.sh | sh

set -euo pipefail

info()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn()  { printf '\033[1;33mwarning:\033[0m %s\n' "$*"; }
error() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; }

# --- Detect OS ---
OS="$(uname -s)"
case "$OS" in
  Linux|Darwin) ;;
  *)
    error "Unsupported OS: $OS (only macOS and Linux are supported)"
    exit 1
    ;;
esac

info "Detected OS: $OS"

# --- Install uv if missing ---
if command -v uv >/dev/null 2>&1; then
  info "uv is already installed: $(uv --version)"
else
  info "Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh

  # Source uv env so it's available in this session
  if [ -f "$HOME/.local/bin/env" ]; then
    # shellcheck disable=SC1091
    . "$HOME/.local/bin/env"
  elif [ -f "$HOME/.cargo/env" ]; then
    # shellcheck disable=SC1091
    . "$HOME/.cargo/env"
  fi

  if ! command -v uv >/dev/null 2>&1; then
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
  fi

  if command -v uv >/dev/null 2>&1; then
    info "uv installed: $(uv --version)"
  else
    error "uv installation succeeded but 'uv' is not on PATH."
    error "Add ~/.local/bin or ~/.cargo/bin to your PATH and re-run."
    exit 1
  fi
fi

# --- Install meridian-channel ---
info "Installing meridian-channel..."
uv tool install meridian-channel

# --- Verify ---
if command -v meridian >/dev/null 2>&1; then
  info "meridian $(meridian --version) installed successfully!"
else
  # uv tool bin may not be on PATH yet
  UV_TOOL_BIN="$(uv tool dir 2>/dev/null)/bin" || UV_TOOL_BIN="$HOME/.local/bin"
  if [ -x "$UV_TOOL_BIN/meridian" ]; then
    info "meridian installed to $UV_TOOL_BIN/meridian"
    warn "Add $UV_TOOL_BIN to your PATH to use 'meridian' directly."
  else
    error "Installation finished but 'meridian' binary not found."
    exit 1
  fi
fi

echo ""
info "Next steps:"
echo "  1. Install at least one harness CLI:"
echo "     - Claude CLI:  https://docs.anthropic.com/en/docs/claude-code"
echo "     - Codex CLI:   https://github.com/openai/codex"
echo "     - OpenCode:    https://opencode.ai"
echo "  2. Run:  meridian config init"
echo "  3. Run:  meridian doctor"
