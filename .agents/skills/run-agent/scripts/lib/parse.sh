#!/usr/bin/env bash
# lib/parse.sh — Usage display and argument parsing.
# Sourced by run-agent.sh; expects globals from the entrypoint.

# ─── Usage ───────────────────────────────────────────────────────────────────

usage() {
  local exit_code="${1:-1}"
  local timeout_default="${DEFAULT_TIMEOUT_MINUTES:-30}"
  cat <<EOF
Usage: run-agent.sh [OPTIONS]

Options:
  -m, --model MODEL        Model to use (required unless fallback applies)
  -V, --variant VARIANT    Model variant passed to harness (default: high)
                           Presets: low, medium, high, xhigh, max
                           Not all variants apply to all models.
      --timeout M          Kill hung harness runs after M minutes (default: ${timeout_default}). Supports fractional minutes.
      --agent NAME         Agent profile (passed to harness natively where supported)
      --strict-skills      Error on unknown skills (default: warn only)
  -s, --skills LIST        Comma-separated skill names to load
  -p, --prompt TEXT        Prompt text (can also pipe via stdin)
      --session ID         Session ID for grouping related runs
      --label K=V          Run metadata label (repeatable)
  -v, --var KEY=VALUE      Template variable substitution (repeatable)
  -f, --file PATH          Reference file/dir to list in prompt (repeatable)
  -D, --detail LEVEL       Report detail level: brief | standard | detailed (default: standard)
      --continue-run REF   Continue a previous run's harness session
      --fork               Fork the session on continuation (default where supported)
      --in-place           Resume without forking (always for Codex)
      --dry-run            Print composed prompt + CLI command, don't execute
  -C, --cd DIR             Working directory for subprocess
  -h, --help               Show this help
EOF
  exit "$exit_code"
}

require_option_value() {
  local opt="$1"
  local remaining_args="$2"

  if [[ "$remaining_args" -lt 2 ]]; then
    echo "ERROR: $opt requires a value." >&2
    usage
  fi
}

preparse_work_dir_override() {
  local args=("$@")
  local idx=0
  while [[ $idx -lt ${#args[@]} ]]; do
    case "${args[$idx]}" in
      -C|--cd)
        if [[ $((idx + 1)) -ge ${#args[@]} ]]; then
          echo "ERROR: ${args[$idx]} requires a value." >&2
          usage
        fi
        WORK_DIR="${args[$((idx + 1))]}"
        idx=$((idx + 2))
        ;;
      *)
        idx=$((idx + 1))
        ;;
    esac
  done

  if [[ "$WORK_DIR" != /* ]]; then
    WORK_DIR="$(pwd -P)/$WORK_DIR"
  fi
}

parse_label_kv() {
  local raw="$1"
  local key="${raw%%=*}"
  local val="${raw#*=}"

  if [[ "$raw" != *=* ]]; then
    echo "ERROR: --label requires KEY=VALUE (got: $raw)" >&2
    exit 1
  fi
  if [[ -z "$key" || -z "$val" ]]; then
    echo "ERROR: --label requires non-empty KEY and VALUE (got: $raw)" >&2
    exit 1
  fi
  if [[ ! "$key" =~ ^[A-Za-z0-9._-]+$ ]]; then
    echo "ERROR: Invalid label key '$key'. Allowed: letters, numbers, dot, underscore, dash." >&2
    exit 1
  fi

  LABELS["$key"]="$val"
  HAS_LABELS=true
}

# ─── Argument Parsing ────────────────────────────────────────────────────────

parse_args() {
  preparse_work_dir_override "$@"
  refresh_orchestrate_paths_from_workdir

  while [[ $# -gt 0 ]]; do
    case "$1" in
      -m|--model)
        require_option_value "$1" "$#"
        MODEL="$2"
        MODEL_FROM_CLI=true
        shift 2
        ;;
      -V|--variant)
        require_option_value "$1" "$#"
        VARIANT="$2"
        VARIANT_FROM_CLI=true
        shift 2
        ;;
      --timeout)
        require_option_value "$1" "$#"
        TIMEOUT_MINUTES="$2"
        shift 2
        ;;
      --agent)
        require_option_value "$1" "$#"
        AGENT_NAME="$2"
        shift 2
        ;;
      --strict-skills)
        STRICT_SKILLS=true
        shift
        ;;
      -s|--skills)
        require_option_value "$1" "$#"
        IFS=',' read -ra _skills <<< "$2"
        for s in "${_skills[@]}"; do SKILLS+=("$(echo "$s" | xargs)"); done
        shift 2
        ;;
      -p|--prompt)
        require_option_value "$1" "$#"
        if [[ "$2" == "-" ]]; then
          CLI_PROMPT=""
        else
          CLI_PROMPT="$2"
        fi
        shift 2
        ;;
      --session)
        require_option_value "$1" "$#"
        SESSION_ID="$2"
        shift 2
        ;;
      --label)
        require_option_value "$1" "$#"
        parse_label_kv "$2"
        shift 2
        ;;
      -f|--file)
        require_option_value "$1" "$#"
        REF_FILES+=("$2")
        shift 2
        ;;
      -v|--var)
        require_option_value "$1" "$#"
        key="${2%%=*}"
        val="${2#*=}"
        VARS["$key"]="$val"
        HAS_VARS=true
        shift 2
        ;;
      -D|--detail)
        require_option_value "$1" "$#"
        case "$2" in
          brief|standard|detailed) DETAIL="$2" ;;
          *) echo "[run-agent] WARNING: Invalid detail level '$2', defaulting to 'standard'" >&2; DETAIL="standard" ;;
        esac
        shift 2
        ;;
      --continue-run)
        require_option_value "$1" "$#"
        CONTINUE_RUN_REF="$2"
        shift 2
        ;;
      --fork)
        CONTINUATION_FORK=true
        CONTINUATION_FORK_EXPLICIT=true
        shift
        ;;
      --in-place)
        CONTINUATION_FORK=false
        CONTINUATION_FORK_EXPLICIT=true
        shift
        ;;
      --dry-run) DRY_RUN=true; shift ;;
      -C|--cd)
        # Already handled by preparse; skip here.
        shift 2
        ;;
      -h|--help)    usage 0 ;;
      *)
        echo "ERROR: Unknown argument: $1" >&2
        usage
        ;;
    esac
  done

  # Read prompt from stdin if not provided via -p
  if [[ -z "$CLI_PROMPT" ]] && [[ ! -t 0 ]]; then
    CLI_PROMPT="$(cat)"
  fi

  PROMPT="$CLI_PROMPT"
}

validate_args() {
  if [[ -n "${TIMEOUT_MINUTES:-}" ]]; then
    if ! [[ "$TIMEOUT_MINUTES" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
      echo "ERROR: --timeout must be a non-negative number of minutes (got: $TIMEOUT_MINUTES)" >&2
      exit 1
    fi
  fi

  # Model fallback
  if [[ -z "$MODEL" ]]; then
    echo "[run-agent] WARNING: No model specified; falling back to $FALLBACK_MODEL" >&2
    MODEL="$FALLBACK_MODEL"
  fi

  # Advisory: warn early if the routed CLI isn't installed.
  local routed_cli
  routed_cli="$(route_model "$MODEL" 2>/dev/null || echo "")"
  if [[ -n "$routed_cli" ]] && ! command -v "$routed_cli" >/dev/null 2>&1; then
    echo "[run-agent] WARNING: '$routed_cli' not installed for model '$MODEL'; will fall back to $FALLBACK_MODEL ($FALLBACK_CLI)" >&2
  fi

  # Skill validation (source of truth: orchestrate/skills/<name>/SKILL.md).
  if [[ ${#SKILLS[@]} -gt 0 ]]; then
    local missing_skills=()
    local skill
    for skill in "${SKILLS[@]}"; do
      if [[ ! -f "$SKILLS_DIR/$skill/SKILL.md" ]]; then
        missing_skills+=("$skill")
      fi
    done

    if [[ ${#missing_skills[@]} -gt 0 ]]; then
      local joined
      joined="$(IFS=,; echo "${missing_skills[*]}")"
      if [[ "${STRICT_SKILLS:-false}" == true ]]; then
        echo "ERROR: Unknown skill(s): $joined" >&2
        echo "  Expected files under: $SKILLS_DIR/<skill>/SKILL.md" >&2
        exit 1
      fi
      echo "[run-agent] WARNING: Unknown skill(s): $joined" >&2
      echo "[run-agent] WARNING: Expected files under: $SKILLS_DIR/<skill>/SKILL.md" >&2
    fi
  fi

  if [[ -z "$PROMPT" ]] && [[ ${#SKILLS[@]} -eq 0 ]] && [[ -z "${CONTINUE_RUN_REF:-}" ]]; then
    echo "ERROR: No prompt or skills specified. Use -p, -s, or --continue-run." >&2
    exit 1
  fi

  # Validate template variables are not empty.
  if [[ "$HAS_VARS" == true ]]; then
    local key val
    for key in "${!VARS[@]}"; do
      val="${VARS[$key]}"
      if [[ -z "$val" ]]; then
        echo "ERROR: Template variable '$key' is empty." >&2
        echo "  Hint: If you set the value via a shell variable, make sure it was exported" >&2
        echo "  before the command, or use an inline value:" >&2
        echo "    export MY_VAR=/some/path && ./run-agent.sh -v $key=\"\$MY_VAR\"" >&2
        echo "    ./run-agent.sh -v $key=/some/path" >&2
        exit 1
      fi
    done
  fi
}
