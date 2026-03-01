#!/usr/bin/env bash
# lib/exec.sh — CLI command building (argv array), execution, structured exit codes.
# Sourced by run-agent.sh; expects globals from the entrypoint.

# ─── Structured Exit Codes ────────────────────────────────────────────────────
# 0 = success, 1 = agent error, 2 = infra error, 3 = timeout, 130 = SIGINT, 143 = SIGTERM

# ─── Build CLI Command (argv array) ──────────────────────────────────────────

# Deterministic heuristic to infer Codex sandbox tier from tools list.
# Codex sandbox controls both filesystem AND network access:
#   read-only         — no writes, no network
#   workspace-write   — writes to workspace, no network by default
#   danger-full-access — unrestricted filesystem + network
infer_sandbox_from_tools() {
  local tools_csv="$1"
  if [[ -z "$tools_csv" ]]; then
    # No tools field = unrestricted
    echo ""
    return
  fi

  local has_web=false has_write=false has_unrestricted_bash=false has_read_only=false

  IFS=',' read -ra tool_list <<< "$tools_csv"
  for t in "${tool_list[@]}"; do
    t="$(echo "$t" | xargs)"
    case "$t" in
      WebSearch|WebFetch)   has_web=true ;;
      Edit|Write)           has_write=true ;;
      Bash)                 has_unrestricted_bash=true ;;
      Bash\(*)             has_write=true ;;  # Bash with restrictions = write-level
      Read|Glob|Grep)       has_read_only=true ;;
    esac
  done

  if [[ "$has_unrestricted_bash" == true ]] || [[ "$has_web" == true ]]; then
    echo "danger-full-access"
  elif [[ "$has_write" == true ]]; then
    echo "workspace-write"
  elif [[ "$has_read_only" == true ]]; then
    echo "read-only"
  else
    echo ""
  fi
}

build_continuation_fallback_prompt() {
  local original_run_id="$1"
  local original_model="$2"
  local original_log_dir="$3"
  local follow_up_prompt="$4"
  local original_input_file="$original_log_dir/input.md"
  local original_report_file="$original_log_dir/report.md"

  if [[ ! -f "$original_input_file" ]]; then
    echo "ERROR: Cannot build continuation fallback prompt: missing $original_input_file" >&2
    return 1
  fi
  if [[ ! -f "$original_report_file" ]]; then
    echo "ERROR: Cannot build continuation fallback prompt: missing $original_report_file" >&2
    return 1
  fi

  local original_input original_report
  original_input="$(cat "$original_input_file")"
  original_report="$(cat "$original_report_file")"

  cat <<EOF
# Continuation Context

Native harness continuation was unavailable. Continue from this prior run context.

- Original run ID: $original_run_id
- Original model: $original_model

## Original Prompt

\`\`\`markdown
$original_input
\`\`\`

## Original Report

\`\`\`markdown
$original_report
\`\`\`

## Follow-Up Request

$follow_up_prompt
EOF
}

resolve_continuation_run_ref() {
  local ref="$1"
  local derived="$2"

  case "$ref" in
    @latest)
      echo "$derived" | jq -r '.[0].run_id // empty'
      ;;
    @last-failed)
      echo "$derived" | jq -r '[.[] | select(.effective_status == "failed")] | .[0].run_id // empty'
      ;;
    @last-completed)
      echo "$derived" | jq -r '[.[] | select(.effective_status == "completed")] | .[0].run_id // empty'
      ;;
    *)
      local exact
      exact="$(echo "$derived" | jq -r --arg ref "$ref" '[.[] | select(.run_id == $ref)] | .[0].run_id // empty')"
      if [[ -n "$exact" ]]; then
        echo "$exact"
        return 0
      fi

      if [[ ${#ref} -lt 8 ]]; then
        echo "ERROR: Continuation run reference prefix must be at least 8 characters (got ${#ref})." >&2
        return 1
      fi

      local matches count
      matches="$(echo "$derived" | jq -r --arg prefix "$ref" '[.[] | select(.run_id | startswith($prefix))] | map(.run_id)')"
      count="$(echo "$matches" | jq 'length')"

      if [[ "$count" -eq 0 ]]; then
        echo "ERROR: No run matching continuation ref '$ref'." >&2
        return 1
      fi
      if [[ "$count" -gt 1 ]]; then
        echo "ERROR: Ambiguous continuation ref '$ref'. Use a longer prefix." >&2
        return 1
      fi

      echo "$matches" | jq -r '.[0]'
      ;;
  esac
}

prepare_continuation() {
  [[ -z "${CONTINUE_RUN_REF:-}" ]] && return 0

  local index_file="$ORCHESTRATE_ROOT/index/runs.jsonl"
  if [[ ! -f "$index_file" ]]; then
    echo "ERROR: Cannot continue run '$CONTINUE_RUN_REF': index file not found at $index_file" >&2
    return 1
  fi
  if ! command -v jq >/dev/null 2>&1; then
    echo "ERROR: jq is required for --continue-run." >&2
    return 2
  fi

  local derived
  derived="$(
    jq -s '
      group_by(.run_id)
      | map(
          . as $rows
          | ($rows | map(select(.status == "running")) | first) as $start
          | ($rows | map(select(.status == "completed" or .status == "failed")) | first) as $fin
          | ($start // $rows[0])
          + (if $fin then $fin else {} end)
          + { effective_status: (if $fin then $fin.status else "running" end) }
        )
      | sort_by(.created_at_utc // "") | reverse
    ' "$index_file" 2>/dev/null
  )"

  local continue_run_id
  continue_run_id="$(resolve_continuation_run_ref "$CONTINUE_RUN_REF" "$derived")" || return 1
  if [[ -z "$continue_run_id" ]]; then
    echo "ERROR: Could not resolve continuation ref '$CONTINUE_RUN_REF'." >&2
    return 1
  fi

  local run_row
  run_row="$(echo "$derived" | jq --arg id "$continue_run_id" '.[] | select(.run_id == $id)')"
  if [[ -z "$run_row" ]]; then
    echo "ERROR: Could not find continuation run '$continue_run_id' in index." >&2
    return 1
  fi

  local effective_status source_harness source_model harness_session_id source_log_dir
  effective_status="$(echo "$run_row" | jq -r '.effective_status // "running"')"
  if [[ "$effective_status" == "running" ]]; then
    echo "ERROR: Cannot continue run '$continue_run_id': run has no finalize row (crashed or still in progress)." >&2
    return 1
  fi
  source_harness="$(echo "$run_row" | jq -r '.harness // empty')"
  source_model="$(echo "$run_row" | jq -r '.model // empty')"
  harness_session_id="$(echo "$run_row" | jq -r '.harness_session_id // empty')"
  source_log_dir="$(echo "$run_row" | jq -r '.log_dir // empty')"

  if [[ -z "$source_harness" || -z "$source_model" || -z "$source_log_dir" ]]; then
    echo "ERROR: Cannot continue run '$continue_run_id': missing required run metadata." >&2
    return 1
  fi

  # Continuations default to original model unless user explicitly overrides.
  if [[ "${MODEL_FROM_CLI:-false}" != true ]]; then
    MODEL="$source_model"
  fi

  local target_harness
  target_harness="$(route_model "$MODEL" 2>/dev/null || echo "")"
  if [[ -z "$target_harness" ]]; then
    echo "ERROR: Cannot continue run '$continue_run_id': model '$MODEL' does not map to a supported harness." >&2
    return 1
  fi
  if [[ "$target_harness" != "$source_harness" ]]; then
    echo "ERROR: Cannot continue run '$continue_run_id': model '$MODEL' maps to '$target_harness', expected '$source_harness'." >&2
    return 1
  fi

  CONTINUES_RUN_ID="$continue_run_id"
  CONTINUATION_FALLBACK_REASON=""

  if [[ -z "$harness_session_id" ]]; then
    CONTINUATION_MODE="fallback-prompt"
    CONTINUATION_FALLBACK_REASON="missing_session_id"
    PROMPT="$(build_continuation_fallback_prompt "$continue_run_id" "$source_model" "$source_log_dir" "$PROMPT")" || return 1
    return 0
  fi

  CONTINUE_HARNESS_SESSION_ID="$harness_session_id"

  case "$source_harness" in
    codex)
      if [[ "${CONTINUATION_FORK_EXPLICIT:-false}" == true && "${CONTINUATION_FORK:-true}" == true ]]; then
        echo "ERROR: Codex continuation does not support forking. Use --in-place or omit --fork." >&2
        return 1
      fi
      CONTINUATION_MODE="in-place"
      ;;
    claude|opencode)
      if [[ "${CONTINUATION_FORK:-true}" == true ]]; then
        CONTINUATION_MODE="fork"
      else
        CONTINUATION_MODE="in-place"
      fi
      ;;
    *)
      CONTINUATION_MODE="fallback-prompt"
      CONTINUATION_FALLBACK_REASON="unsupported_harness"
      PROMPT="$(build_continuation_fallback_prompt "$continue_run_id" "$source_model" "$source_log_dir" "$PROMPT")" || return 1
      ;;
  esac
}

build_cli_command() {
  local tool
  local normalized_tools
  local native_continuation=false
  CLI_PROMPT_MODE="stdin"

  tool="$(route_model "$MODEL" 2>/dev/null || echo "")"

  if [[ -z "$tool" ]]; then
    if [[ -n "${CONTINUE_RUN_REF:-}" ]]; then
      echo "ERROR: Unknown model family '$MODEL' for continuation run." >&2
      return 2
    fi
    echo "[run-agent] WARNING: Unknown model family '$MODEL'; falling back to $FALLBACK_MODEL ($FALLBACK_CLI)" >&2
    tool="$FALLBACK_CLI"
    MODEL="$FALLBACK_MODEL"
  elif ! command -v "$tool" >/dev/null 2>&1; then
    if [[ -n "${CONTINUE_RUN_REF:-}" ]]; then
      echo "ERROR: '$tool' CLI not found for continuation model '$MODEL'." >&2
      return 2
    fi
    echo "[run-agent] WARNING: '$tool' CLI not found for model '$MODEL'; falling back to $FALLBACK_MODEL ($FALLBACK_CLI)" >&2
    tool="$FALLBACK_CLI"
    MODEL="$FALLBACK_MODEL"
  fi

  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "ERROR: '$tool' CLI not found. Install it or try a different model with -m." >&2
    return 2
  fi

  CLI_CMD_ARGV=()
  CLI_HARNESS="$tool"
  if [[ -n "${CONTINUE_RUN_REF:-}" ]] \
    && [[ -n "${CONTINUE_HARNESS_SESSION_ID:-}" ]] \
    && [[ "${CONTINUATION_MODE:-}" != "fallback-prompt" ]]; then
    native_continuation=true
  fi

  case "$tool" in
    claude)
      local -a agent_flags=()
      if [[ -n "$AGENT_NAME" ]]; then
        # Claude Code reads .claude/agents/<name>.md and enforces tools/permissions natively
        agent_flags+=(--agent "$AGENT_NAME")
      else
        agent_flags+=(--dangerously-skip-permissions)
      fi
      CLI_CMD_ARGV=(env CLAUDECODE= claude -p - --model "$MODEL" --effort "$VARIANT" --verbose --output-format stream-json "${agent_flags[@]}")
      if [[ "$native_continuation" == true ]]; then
        CLI_CMD_ARGV+=(--resume "$CONTINUE_HARNESS_SESSION_ID")
        if [[ "${CONTINUATION_MODE:-}" == "fork" ]]; then
          CLI_CMD_ARGV+=(--fork-session)
        fi
      fi
      ;;
    codex)
      # Codex has no --agent flag. Determine sandbox from agent profile.
      # Priority: explicit sandbox: field > inferred from tools: field > unrestricted
      local effective_sandbox="${AGENT_SANDBOX:-}"
      if [[ -z "$effective_sandbox" ]] && [[ -n "$AGENT_TOOLS" ]]; then
        effective_sandbox="$(infer_sandbox_from_tools "$AGENT_TOOLS")"
      fi
      local -a perm_flags=()
      case "${effective_sandbox:-}" in
        read-only)           perm_flags+=(--sandbox read-only) ;;
        workspace-write)     perm_flags+=(--sandbox workspace-write) ;;
        danger-full-access)  perm_flags+=(--sandbox danger-full-access) ;;
        *)                   perm_flags+=(--dangerously-bypass-approvals-and-sandbox) ;;
      esac
      if [[ "$native_continuation" == true ]]; then
        CLI_CMD_ARGV=(codex exec resume "$CONTINUE_HARNESS_SESSION_ID" -m "$MODEL" -c "model_reasoning_effort=$VARIANT" "${perm_flags[@]}" --json -)
      else
        CLI_CMD_ARGV=(codex exec -m "$MODEL" -c "model_reasoning_effort=$VARIANT" "${perm_flags[@]}" --json -)
      fi
      ;;
    opencode)
      local effective_model
      effective_model="$(strip_model_prefix "$MODEL")"
      local -a agent_flags=()
      if [[ -n "$AGENT_NAME" ]]; then
        # OpenCode reads .agents/agents/<name>.md and enforces permissions natively
        agent_flags+=(--agent "$AGENT_NAME")
      fi
      CLI_CMD_ARGV=(opencode run --model "$effective_model" --format json --print-logs --variant "$VARIANT" "${agent_flags[@]}")
      CLI_PROMPT_MODE="arg"
      if [[ "$native_continuation" == true ]]; then
        CLI_CMD_ARGV+=(--session "$CONTINUE_HARNESS_SESSION_ID")
        if [[ "${CONTINUATION_MODE:-}" == "fork" ]]; then
          CLI_CMD_ARGV+=(--fork)
        fi
      fi
      ;;
    *)
      echo "ERROR: Unsupported CLI harness: $tool" >&2
      return 2
      ;;
  esac
}

format_cli_cmd() {
  local out=""
  for arg in "${CLI_CMD_ARGV[@]}"; do
    if [[ "$arg" == *" "* || "$arg" == *"="* ]]; then
      out+="\"$arg\" "
    else
      out+="$arg "
    fi
  done
  echo "${out% }"
}

# ─── Files-Touched Extraction ────────────────────────────────────────────────

write_files_touched_from_log() {
  local output_log="$1"
  local log_dir="$2"
  local extractor="$SCRIPT_DIR/extract-files-touched.sh"

  if [[ -x "$extractor" ]]; then
    # Produce NUL-delimited canonical format
    if ! "$extractor" "$output_log" "$log_dir/files-touched.nul" --nul 2>/dev/null; then
      # Fallback: try without --nul for backward compat during transition
      "$extractor" "$output_log" "$log_dir/files-touched.txt" 2>/dev/null || true
      return
    fi
    # Derive newline-delimited from NUL-delimited
    if [[ -f "$log_dir/files-touched.nul" ]]; then
      tr '\0' '\n' < "$log_dir/files-touched.nul" > "$log_dir/files-touched.txt"
    fi
  else
    : > "$log_dir/files-touched.txt"
    : > "$log_dir/files-touched.nul"
  fi
}

# ─── Dry Run ─────────────────────────────────────────────────────────────────

do_dry_run() {
  local cli_display
  cli_display="$(format_cli_cmd)"

  echo "═══ DRY RUN ═══"
  echo ""
  if [[ -n "${AGENT_NAME:-}" ]]; then echo "── Agent: $AGENT_NAME"; fi
  echo "── Model: $MODEL ($(route_model "$MODEL" 2>/dev/null || echo "fallback"))"
  echo "── Variant: $VARIANT"
  echo "── Report: $DETAIL"
  if [[ ${#SKILLS[@]} -gt 0 ]]; then echo "── Skills: ${SKILLS[*]}"; else echo "── Skills: none"; fi
  if [[ -n "${AGENT_TOOLS:-}" ]]; then echo "── Tools: $AGENT_TOOLS"; else echo "── Tools: unrestricted"; fi
  if [[ -n "${AGENT_SANDBOX:-}" ]]; then echo "── Sandbox: $AGENT_SANDBOX"; else echo "── Sandbox: none (unrestricted)"; fi
  if [[ -n "${SESSION_ID:-}" ]]; then echo "── Session: $SESSION_ID"; fi
  if [[ "$HAS_LABELS" == true ]]; then
    local k
    echo "── Labels:"
    for k in "${!LABELS[@]}"; do
      echo "   - $k=${LABELS[$k]}"
    done
  else
    echo "── Labels: none"
  fi
  if [[ ${#REF_FILES[@]} -gt 0 ]]; then echo "── Ref files: ${REF_FILES[*]}"; else echo "── Ref files: none"; fi
  echo "── Working dir: $WORK_DIR"
  echo ""
  echo "── CLI Command (argv):"
  echo "  $cli_display"
  echo ""
  echo "── Composed Prompt:"
  echo "────────────────────────────────────────"
  echo "$COMPOSED_PROMPT"
  echo ""
  echo "[report instruction would be appended with LOG_DIR path at $DETAIL detail]"
  echo "────────────────────────────────────────"
}

# ─── Signal Handling ──────────────────────────────────────────────────────────

_run_interrupted=false
_run_start_epoch=0

_handle_signal() {
  local sig_code="$1"
  _run_interrupted=true

  # Write finalize row for observability before exiting
  if [[ -n "${RUN_ID:-}" ]] && [[ -n "${LOG_DIR:-}" ]]; then
    local duration=0
    if [[ "$_run_start_epoch" -gt 0 ]]; then
      local now_epoch
      now_epoch="$(date +%s)"
      duration=$((now_epoch - _run_start_epoch))
    fi
    append_finalize_row "$sig_code" "$duration" 2>/dev/null || true
  fi

  exit "$sig_code"
}

# ─── Execute ─────────────────────────────────────────────────────────────────

write_failfast_report() {
  local exit_code="$1"
  local title="$2"
  local details="${3:-}"

  # Avoid clobbering a non-empty report from an upstream harness (rare but possible).
  if [[ -f "$LOG_DIR/report.md" ]] && [[ -s "$LOG_DIR/report.md" ]]; then
    return 0
  fi

  {
    echo "# Run Report (auto-generated)"
    echo ""
    echo "**Status**: failed (exit $exit_code)"
    echo ""
    echo "**Failure**: $title"
    if [[ -n "$details" ]]; then
      echo ""
      echo "$details"
    fi
  } > "$LOG_DIR/report.md"
}

extract_opencode_error_message() {
  local output_log="$1"
  if ! command -v jq >/dev/null 2>&1; then
    return 1
  fi
  # Best-effort: find the last error event and extract a message-like field.
  jq -r '
    select(.type == "error")
    | (.error.data.message // .error.message // .error.data // .error // .message // empty)
  ' "$output_log" 2>/dev/null | tail -1
}

detect_opencode_error_event() {
  local output_log="$1"
  grep -q '"type":"error"' "$output_log" 2>/dev/null
}

do_execute() {
  local cli_display output_log run_index_base_cmd show_cmd report_cmd files_cmd logs_cmd
  cli_display="$(format_cli_cmd)"

  # Set up logging and write start index row for crash visibility
  setup_logging
  export ORCHESTRATE_RUN_ID="$RUN_ID"
  output_log="$LOG_DIR/output.jsonl"
  write_log_params "$cli_display"
  run_index_base_cmd="$SCRIPT_DIR/run-index.sh --repo \"$REPO_ROOT\""
  show_cmd="$run_index_base_cmd show \"$RUN_ID\""
  report_cmd="$run_index_base_cmd report \"$RUN_ID\""
  files_cmd="$run_index_base_cmd files \"$RUN_ID\""
  logs_cmd="$run_index_base_cmd logs \"$RUN_ID\""

  # Capture git HEAD before execution (best-effort)
  HEAD_BEFORE=""
  if command -v git >/dev/null 2>&1; then
    HEAD_BEFORE="$(git -C "$WORK_DIR" rev-parse HEAD 2>/dev/null || echo "")"
  fi

  # Write start row immediately (crash visibility)
  append_start_row

  # Install signal traps
  trap '_handle_signal 130' INT
  trap '_handle_signal 143' TERM

  # Record start time for duration tracking
  _run_start_epoch="$(date +%s)"

  # Save composed prompt before run-time instructions are appended.
  # This is used by retry to avoid duplicating generated sections.
  echo "$COMPOSED_PROMPT" > "$LOG_DIR/prompt.raw.md"

  # Append output directory and report instruction now that LOG_DIR is known.
  COMPOSED_PROMPT+="$(build_output_dir_instruction "$LOG_DIR")"
  COMPOSED_PROMPT+="$(build_report_instruction "$LOG_DIR/report.md" "$DETAIL")"

  # Save composed prompt
  echo "$COMPOSED_PROMPT" > "$LOG_DIR/input.md"

  echo "[run-agent] Run: $RUN_ID | Model: $MODEL | Variant: $VARIANT" >&2
  echo "[run-agent] run-index commands:" >&2
  echo "[run-agent]   show: $show_cmd" >&2
  echo "[run-agent]   report: $report_cmd" >&2
  echo "[run-agent]   files: $files_cmd" >&2
  echo "[run-agent]   logs: $logs_cmd" >&2

  # Execute via argv array — no eval needed.
  cd "$WORK_DIR"
  local timeout_used=false
  local -a runner=()
  if command -v timeout >/dev/null 2>&1 && awk -v m="${TIMEOUT_MINUTES:-0}" 'BEGIN{exit !(m>0)}'; then
    local timeout_seconds
    timeout_seconds="$(awk -v m="${TIMEOUT_MINUTES:-0}" 'BEGIN{printf "%.3f", m*60}')"
    # Use a grace period so the harness can flush logs before SIGKILL.
    runner=(timeout --signal=TERM --kill-after=10s "${timeout_seconds}s")
    timeout_used=true
  fi
  local harness_exit=0
  set +e
  if [[ "${CLI_PROMPT_MODE:-stdin}" == "arg" ]]; then
    "${runner[@]}" "${CLI_CMD_ARGV[@]}" "$COMPOSED_PROMPT" \
      > "$output_log" \
      2> >(tee "$LOG_DIR/stderr.log" >&2)
  else
    "${runner[@]}" "${CLI_CMD_ARGV[@]}" <<< "$COMPOSED_PROMPT" \
      > "$output_log" \
      2> >(tee "$LOG_DIR/stderr.log" >&2)
  fi
  harness_exit=$?
  set -e

  # Map harness exit to structured exit code
  local exit_code="$harness_exit"
  if [[ "$timeout_used" == true ]] && { [[ "$harness_exit" -eq 124 ]] || [[ "$harness_exit" -eq 137 ]]; }; then
    exit_code=3
    write_failfast_report "$exit_code" "Timed out" "Harness exceeded ${TIMEOUT_MINUTES} minutes."
  fi

  # Exit codes 0, 1, 2, 3 pass through as-is (already structured).
  # 130/143 are handled by signal traps above.
  # Other non-zero codes map to 1 (agent error).
  if [[ "$exit_code" -gt 3 ]] && [[ "$exit_code" -ne 130 ]] && [[ "$exit_code" -ne 143 ]]; then
    exit_code=1
  fi

  # Fail-fast: don't silently succeed when a harness produces no usable output.
  if [[ "$exit_code" -eq 0 ]]; then
    case "$CLI_HARNESS" in
      claude)
        if [[ ! -f "$output_log" ]] || [[ ! -s "$output_log" ]]; then
          exit_code=2
          write_failfast_report "$exit_code" "No harness output captured" "Claude returned success but produced no stream-json events."
        fi
        ;;
      opencode)
        if [[ ! -f "$output_log" ]] || [[ ! -s "$output_log" ]]; then
          exit_code=2
          write_failfast_report "$exit_code" "No harness output captured" "OpenCode returned success but produced no JSON events."
        elif detect_opencode_error_event "$output_log"; then
          local msg=""
          msg="$(extract_opencode_error_message "$output_log" 2>/dev/null || echo "")"
          exit_code=1
          if [[ -n "$msg" ]]; then
            write_failfast_report "$exit_code" "OpenCode error event" "$msg"
          else
            write_failfast_report "$exit_code" "OpenCode error event" "See output log for details: $output_log"
          fi
        fi
        ;;
    esac
  fi

  # Derive files touched
  write_files_touched_from_log "$output_log" "$LOG_DIR"

  # Report fallback: if no report.md, try to extract last assistant message
  if [[ ! -f "$LOG_DIR/report.md" ]] || [[ ! -s "$LOG_DIR/report.md" ]]; then
    local fallback_extractor="$SCRIPT_DIR/extract-report-fallback.sh"
    if [[ -x "$fallback_extractor" ]]; then
      "$fallback_extractor" "$CLI_HARNESS" "$output_log" "$LOG_DIR/stderr.log" "$exit_code" \
        > "$LOG_DIR/report.md" 2>/dev/null || true
    fi
  fi

  # Compute duration
  local end_epoch duration_seconds
  end_epoch="$(date +%s)"
  duration_seconds=$((_run_start_epoch > 0 ? end_epoch - _run_start_epoch : 0))

  # Write finalize row
  EXIT_CODE="$exit_code"
  append_finalize_row "$exit_code" "$duration_seconds"

  # Print report to stdout for the orchestrator
  if [[ -f "$LOG_DIR/report.md" ]] && [[ -s "$LOG_DIR/report.md" ]]; then
    cat "$LOG_DIR/report.md"
  else
    echo "---" >&2
    echo "[run-agent] WARNING: Agent did not produce a report at $LOG_DIR/report.md" >&2
    echo "[run-agent] Exit code: $exit_code" >&2
    echo "[run-agent] Output log: $output_log" >&2
    if [[ -f "$output_log" ]] && [[ -s "$output_log" ]]; then
      echo "[run-agent] Last 40 lines of output:" >&2
      tail -n 40 "$output_log" >&2
    else
      echo "[run-agent] Output log is empty — the CLI may have failed to start." >&2
    fi
    echo "---" >&2
  fi

  echo "[run-agent] Done (exit=$exit_code, duration=${duration_seconds}s). Run: $RUN_ID" >&2
  echo "[run-agent] Report: $report_cmd" >&2
  exit "$exit_code"
}
