#!/usr/bin/env bash
# lib/logging.sh — Flat run storage, two-row index (start + finalize), path helpers.
# Sourced by run-agent.sh; expects globals from the entrypoint.

# ─── Path Helpers ─────────────────────────────────────────────────────────────

resolve_repo_path() {
  local path="$1"
  if [[ "$path" == /* ]]; then
    echo "$path"
  else
    echo "$REPO_ROOT/$path"
  fi
}

build_run_id() {
  local ts suffix
  ts="$(date -u +"%Y%m%dT%H%M%SZ")"
  # Keep run IDs compact; agent/model stay in params.json + index metadata.
  suffix="$(printf '%s%04x' "$$" "$RANDOM")"
  echo "${ts}__${suffix}"
}

# ─── Log Setup ────────────────────────────────────────────────────────────────

setup_logging() {
  if [[ -z "${RUN_ID:-}" ]]; then
    RUN_ID="$(build_run_id)"
  fi

  LOG_DIR="$ORCHESTRATE_ROOT/runs/agent-runs/$RUN_ID"

  if [[ "$LOG_DIR" == "/" ]]; then
    echo "ERROR: LOG_DIR resolved to '/' — refusing to write run artifacts at filesystem root." >&2
    exit 2
  fi

  mkdir -p "$LOG_DIR"
  mkdir -p "$ORCHESTRATE_ROOT/index"
}

write_log_params() {
  local cli_cmd="$1"
  local skills_json labels_json now_utc session_id timeout_minutes
  skills_json="$(build_skills_json)"
  labels_json="$(build_labels_json)"
  now_utc="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  session_id="${SESSION_ID:-$RUN_ID}"
  timeout_minutes="${TIMEOUT_MINUTES:-${DEFAULT_TIMEOUT_MINUTES:-30}}"

  cat > "$LOG_DIR/params.json" <<EOF
{
  "run_id": "$(json_escape "$RUN_ID")",
  "session_id": "$(json_escape "$session_id")",
  "model": "$(json_escape "$MODEL")",
  "variant": "$(json_escape "$VARIANT")",
  "timeout_minutes": $timeout_minutes,
  "agent": "$(json_escape "${AGENT_NAME:-}")",
  "tools": "$(json_escape "${AGENT_TOOLS:-}")",
  "sandbox": "$(json_escape "${AGENT_SANDBOX:-}")",
  "skills": $skills_json,
  "labels": $labels_json,
  "cli": "$(json_escape "$cli_cmd")",
  "harness": "$(json_escape "$(route_model "$MODEL")")",
  "invoked_via": "$(json_escape "$0")",
  "script_dir": "$(json_escape "$SCRIPT_DIR")",
  "detail": "$(json_escape "$DETAIL")",
  "cwd": "$(json_escape "$WORK_DIR")",
  "created_at_utc": "$(json_escape "$now_utc")",
  "log_dir": "$(json_escape "$LOG_DIR")"
}
EOF
}

# ─── Index Locking ────────────────────────────────────────────────────────────
# Use flock for atomic appends; fall back to mkdir-based lock if unavailable.

INDEX_FILE=""
_LOCK_FD=""
_LOCK_DIR=""

_resolve_index_file() {
  INDEX_FILE="$ORCHESTRATE_ROOT/index/runs.jsonl"
}

_acquire_lock() {
  local lock_path="$ORCHESTRATE_ROOT/index/runs.lock"

  # Try flock first
  if command -v flock >/dev/null 2>&1; then
    exec {_LOCK_FD}>"$lock_path"
    if flock -w 5 "$_LOCK_FD" 2>/dev/null; then
      return 0
    fi
  fi

  # Fallback: mkdir-based lock with timeout
  _LOCK_DIR="$ORCHESTRATE_ROOT/index/runs.lockdir"
  local attempts=0
  while ! mkdir "$_LOCK_DIR" 2>/dev/null; do
    attempts=$((attempts + 1))
    if [[ $attempts -ge 50 ]]; then
      echo "[run-agent] WARNING: Could not acquire index lock after 5s, appending without lock" >&2
      _LOCK_DIR=""
      return 0
    fi
    sleep 0.1
  done
}

_release_lock() {
  if [[ -n "${_LOCK_FD:-}" ]]; then
    eval "exec ${_LOCK_FD}>&-" 2>/dev/null || true
    _LOCK_FD=""
  fi
  if [[ -n "${_LOCK_DIR:-}" ]]; then
    rmdir "$_LOCK_DIR" 2>/dev/null || true
    _LOCK_DIR=""
  fi
}

# ─── Two-Row Index ────────────────────────────────────────────────────────────

append_start_row() {
  _resolve_index_file
  local labels_json skills_json now_utc session_id
  labels_json="$(build_labels_json)"
  skills_json="$(build_skills_json)"
  now_utc="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  session_id="${SESSION_ID:-$RUN_ID}"

  local agent_field=""
  if [[ -n "${AGENT_NAME:-}" ]]; then
    agent_field="\"agent\":\"$(json_escape "$AGENT_NAME")\","
  fi

  local row
  row=$(cat <<EOF
{"run_id":"$(json_escape "$RUN_ID")","status":"running","created_at_utc":"$(json_escape "$now_utc")","cwd":"$(json_escape "$WORK_DIR")","session_id":"$(json_escape "$session_id")","model":"$(json_escape "$MODEL")","harness":"$(json_escape "$CLI_HARNESS")",${agent_field}"skills":$skills_json,"labels":$labels_json,"log_dir":"$(json_escape "$LOG_DIR")"}
EOF
  )

  _acquire_lock
  echo "$row" >> "$INDEX_FILE"
  _release_lock
}

append_finalize_row() {
  local exit_code="$1"
  local duration_seconds="${2:-0}"
  _resolve_index_file
  local now_utc session_id failure_reason
  now_utc="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  session_id="${SESSION_ID:-$RUN_ID}"

  # Derive failure_reason from exit code
  failure_reason="null"
  if [[ "$exit_code" -ne 0 ]]; then
    case "$exit_code" in
      1)   failure_reason='"agent_error"' ;;
      2)   failure_reason='"infra_error"' ;;
      3)   failure_reason='"timeout"' ;;
      130) failure_reason='"interrupted"' ;;
      143) failure_reason='"interrupted"' ;;
      *)   failure_reason='"unknown"' ;;
    esac
  fi

  local status="completed"
  [[ "$exit_code" -ne 0 ]] && status="failed"

  local output_log="$LOG_DIR/output.jsonl"
  local report_path="$LOG_DIR/report.md"

  # Git metadata (best-effort)
  local git_available="false" in_git_repo="false"
  local head_before="${HEAD_BEFORE:-}" head_after=""
  local commit_count=0 commit_tracking="none" commit_tracking_source="none" commit_tracking_confidence="low"

  if command -v git >/dev/null 2>&1; then
    git_available="true"
    if git -C "$WORK_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
      in_git_repo="true"
      head_after="$(git -C "$WORK_DIR" rev-parse HEAD 2>/dev/null || echo "")"

      # Count commits between start and end HEAD
      if [[ -n "$head_before" ]] && [[ -n "$head_after" ]] && [[ "$head_before" != "$head_after" ]]; then
        commit_count="$(git -C "$WORK_DIR" rev-list --count "$head_before".."$head_after" 2>/dev/null || echo "0")"
        commit_tracking="tracked"
        commit_tracking_source="fallback_git"
        commit_tracking_confidence="medium"
      fi
    fi
  fi

  # Harness session ID (best-effort)
  local harness_session_id=""
  local extractor="$SCRIPT_DIR/extract-harness-session-id.sh"
  if [[ -x "$extractor" ]] && [[ -f "$output_log" ]] && [[ -s "$output_log" ]]; then
    harness_session_id="$("$extractor" "$CLI_HARNESS" "$output_log" 2>/dev/null || echo "")"
  fi

  # Token usage (best-effort, parsed from output)
  local input_tokens="null" output_tokens="null"
  if [[ -f "$output_log" ]] && [[ -s "$output_log" ]]; then
    case "$CLI_HARNESS" in
      claude)
        # Claude result event has usage info
        local usage_line
        usage_line="$(grep '"type":"result"' "$output_log" 2>/dev/null | tail -1 || echo "")"
        if [[ -n "$usage_line" ]]; then
          input_tokens="$(echo "$usage_line" | jq -r '.result.input_tokens // empty' 2>/dev/null || echo "")"
          output_tokens="$(echo "$usage_line" | jq -r '.result.output_tokens // empty' 2>/dev/null || echo "")"
          [[ -z "$input_tokens" ]] && input_tokens="null"
          [[ -z "$output_tokens" ]] && output_tokens="null"
        fi
        ;;
    esac
  fi

  # Continuation/retry metadata (set by caller if applicable)
  local continues_field=""
  if [[ -n "${CONTINUES_RUN_ID:-}" ]]; then
    continues_field="\"continues\":\"$(json_escape "$CONTINUES_RUN_ID")\","
    continues_field+="\"continuation_mode\":\"$(json_escape "${CONTINUATION_MODE:-fork}")\","
    if [[ -n "${CONTINUATION_FALLBACK_REASON:-}" ]]; then
      continues_field+="\"continuation_fallback_reason\":\"$(json_escape "$CONTINUATION_FALLBACK_REASON")\","
    else
      continues_field+="\"continuation_fallback_reason\":null,"
    fi
  fi
  local retries_field=""
  if [[ -n "${RETRIES_RUN_ID:-}" ]]; then
    retries_field="\"retries\":\"$(json_escape "$RETRIES_RUN_ID")\","
  fi

  local row
  row=$(cat <<EOF
{"run_id":"$(json_escape "$RUN_ID")","status":"$status","finished_at_utc":"$(json_escape "$now_utc")","duration_seconds":$duration_seconds,"exit_code":$exit_code,"failure_reason":$failure_reason,"output_log":"$(json_escape "$output_log")","report_path":"$(json_escape "$report_path")",${continues_field}${retries_field}"harness_session_id":"$(json_escape "$harness_session_id")","git_available":$git_available,"in_git_repo":$in_git_repo,"head_before":"$(json_escape "$head_before")","head_after":"$(json_escape "$head_after")","commit_count":$commit_count,"commit_tracking":"$(json_escape "$commit_tracking")","commit_tracking_source":"$(json_escape "$commit_tracking_source")","commit_tracking_confidence":"$(json_escape "$commit_tracking_confidence")","input_tokens":$input_tokens,"output_tokens":$output_tokens}
EOF
  )

  _acquire_lock
  echo "$row" >> "$INDEX_FILE"
  _release_lock
}
