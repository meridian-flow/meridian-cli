#!/usr/bin/env bash
# run-agent.sh — Single entry point for running any agent.
# Routes models to the correct CLI tool, composes prompts, logs everything.
#
# Usage:
#   run-agent.sh [OPTIONS]
#   run-agent.sh --model claude-sonnet-4-6 --skills reviewing -p "Review the changes"
#   run-agent.sh --model gpt-5.3-codex -p "Implement feature" --label ticket=PAY-123
#   run-agent.sh --dry-run --model claude-sonnet-4-6 --skills reviewing -p "test"
#
# A run is model + skills + prompt. No "agent" abstraction.

set -euo pipefail

# Resolve through symlinks so SKILLS_DIR is correct even when invoked via a symlink.
_source="${BASH_SOURCE[0]}"
while [[ -L "$_source" ]]; do
  _dir="$(cd "$(dirname "$_source")" && pwd -P)"
  _source="$(readlink "$_source")"
  [[ "$_source" != /* ]] && _source="$_dir/$_source"
done
SCRIPT_DIR="$(cd "$(dirname "$_source")" && pwd -P)"
CURRENT_DIR="$(pwd -P)"
REPO_ROOT="$(git -C "$CURRENT_DIR" rev-parse --show-toplevel 2>/dev/null || echo "$CURRENT_DIR")"
ORCHESTRATE_ROOT=""
SKILLS_DIR=""
AGENTS_DIR=""

refresh_orchestrate_paths() {
  local repo_base="$1"
  ORCHESTRATE_ROOT="$repo_base/.orchestrate"
  # Skills live in the submodule/clone source, not the runtime dir.
  # Derive from SCRIPT_DIR (inside */run-agent/scripts/).
  local source_root
  source_root="$(cd "$SCRIPT_DIR/../../.." && pwd -P)"
  SKILLS_DIR="$source_root/skills"
  AGENTS_DIR="$source_root/agents"
}

refresh_orchestrate_paths_from_workdir() {
  local candidate_repo
  candidate_repo="$(git -C "$WORK_DIR" rev-parse --show-toplevel 2>/dev/null || echo "$WORK_DIR")"
  REPO_ROOT="$candidate_repo"
  refresh_orchestrate_paths "$REPO_ROOT"
}

# ─── Defaults ────────────────────────────────────────────────────────────────

FALLBACK_CLI="codex"
FALLBACK_MODEL="gpt-5.3-codex"
DEFAULT_TIMEOUT_MINUTES=30

MODEL=""
VARIANT="high"
AGENT_NAME=""
AGENT_BODY=""                    # markdown body (frontmatter stripped), used for Codex prompt injection
AGENT_TOOLS=""                   # comma-separated tool allowlist from agent profile
AGENT_SANDBOX=""                 # Codex sandbox: read-only, workspace-write, danger-full-access (or empty)
# Kill hung harness invocations (default: 30 minutes).
TIMEOUT_MINUTES="$DEFAULT_TIMEOUT_MINUTES"
SKILLS=()
PROMPT=""
CLI_PROMPT=""
DRY_RUN=false
DETAIL="standard"
STRICT_SKILLS=false
WORK_DIR="$REPO_ROOT"
SESSION_ID=""               # explicit session grouping (--session)
CONTINUE_RUN_REF=""         # continuation target (--continue-run)
CONTINUATION_FORK=true      # fork by default where supported
CONTINUATION_FORK_EXPLICIT=false
declare -A VARS=()
declare -A LABELS=()
REF_FILES=()
HAS_VARS=false
HAS_LABELS=false
MODEL_FROM_CLI=false
VARIANT_FROM_CLI=false

# Runtime state (populated during execution)
declare -a CLI_CMD_ARGV=()
CLI_HARNESS=""
RUN_ID=""
LOG_DIR=""
EXIT_CODE=0
HEAD_BEFORE=""

# Continuation/retry metadata (set when applicable)
CONTINUES_RUN_ID=""
CONTINUATION_MODE=""
CONTINUATION_FALLBACK_REASON=""
RETRIES_RUN_ID="${RETRIES_RUN_ID:-}"

refresh_orchestrate_paths "$REPO_ROOT"

# ─── Source Modules ──────────────────────────────────────────────────────────

source "$SCRIPT_DIR/lib/parse.sh"
source "$SCRIPT_DIR/lib/prompt.sh"
source "$SCRIPT_DIR/lib/logging.sh"
source "$SCRIPT_DIR/lib/exec.sh"

# ─── Init ────────────────────────────────────────────────────────────────────

init_work_dir() {
  if ! WORK_DIR="$(cd "$WORK_DIR" 2>/dev/null && pwd -P)"; then
    echo "ERROR: Working directory does not exist: $WORK_DIR" >&2
    exit 2
  fi

  REPO_ROOT="$(git -C "$WORK_DIR" rev-parse --show-toplevel 2>/dev/null || echo "$WORK_DIR")"
  refresh_orchestrate_paths "$REPO_ROOT"
}

init_dirs() {
  mkdir -p "$ORCHESTRATE_ROOT"
  mkdir -p "$ORCHESTRATE_ROOT/runs/agent-runs"
  mkdir -p "$ORCHESTRATE_ROOT/index"

  local config_file="$ORCHESTRATE_ROOT/config.toml"
  if [[ ! -f "$config_file" ]]; then
    cat > "$config_file" <<'EOF'
# Orchestrate runtime configuration.
#
# Skills to auto-load on each run-agent invocation.
# [skills]
# pinned = ["orchestrate", "run-agent", "mermaid"]
#
# Additional runtime sections can be added over time.
# [runtime]
# example_option = "value"
EOF
  fi
}

# ─── Main ────────────────────────────────────────────────────────────────────

parse_args "$@"
init_work_dir

# Load agent profile (if --agent specified) before validation so profile
# defaults (model, variant, skills) are available to validate_args.
if [[ -n "$AGENT_NAME" ]]; then
  load_agent_profile
fi
load_pinned_skills_from_config

validate_args
prepare_continuation
init_dirs

COMPOSED_PROMPT="$(compose_prompt)"
build_cli_command

if [[ "$DRY_RUN" == true ]]; then
  do_dry_run
  exit 0
fi

do_execute
