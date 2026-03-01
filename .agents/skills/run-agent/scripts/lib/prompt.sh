#!/usr/bin/env bash
# lib/prompt.sh — Skill loading, template substitution, prompt composition.
# Sourced by run-agent.sh; expects globals from the entrypoint.

# ─── Skill Loading ───────────────────────────────────────────────────────────
# Reads SKILL.md, strips YAML frontmatter, returns body with source path annotation.
# Not used by compose_prompt (skills are listed by name for harness-native loading),
# but kept for other callers (e.g. orchestrate skill policy loader).

load_skill() {
  local name="$1"
  local skill_file="$SKILLS_DIR/$name/SKILL.md"

  if [[ ! -f "$skill_file" ]]; then
    echo "ERROR: Skill not found: $skill_file" >&2
    return 1
  fi

  # Emit source path so the subagent can resolve relative references
  echo "Loaded from: $skill_file"
  echo ""

  # Strip YAML frontmatter (--- ... ---)
  awk '
    BEGIN { in_frontmatter=0; past_frontmatter=0 }
    /^---$/ {
      if (!past_frontmatter) {
        if (in_frontmatter) { past_frontmatter=1; next }
        else { in_frontmatter=1; next }
      }
    }
    past_frontmatter || !in_frontmatter { if (past_frontmatter || NR > 1 || !/^---$/) print }
  ' "$skill_file"
}

append_skill_if_missing() {
  local candidate="$1"
  [[ -z "$candidate" ]] && return 0

  local existing
  for existing in "${SKILLS[@]}"; do
    if [[ "$existing" == "$candidate" ]]; then
      return 0
    fi
  done
  SKILLS+=("$candidate")
}

load_pinned_skills_from_config() {
  local config_file="$ORCHESTRATE_ROOT/config.toml"
  [[ -f "$config_file" ]] || return 0

  local skill
  while IFS= read -r skill; do
    append_skill_if_missing "$skill"
  done < <(
    awk '
      function ltrim(s) { sub(/^[[:space:]]+/, "", s); return s }
      function rtrim(s) { sub(/[[:space:]]+$/, "", s); return s }
      function trim(s)  { return rtrim(ltrim(s)) }
      function strip_comment(s,   i, c, out, in_dq, esc) {
        out = ""
        in_dq = 0
        esc = 0
        for (i = 1; i <= length(s); i++) {
          c = substr(s, i, 1)
          if (esc) {
            out = out c
            esc = 0
            continue
          }
          if (c == "\\" && in_dq) {
            out = out c
            esc = 1
            continue
          }
          if (c == "\"") {
            in_dq = !in_dq
            out = out c
            continue
          }
          if (c == "#" && !in_dq) {
            break
          }
          out = out c
        }
        return out
      }
      function warn(msg) {
        print "[run-agent] WARNING: " msg > "/dev/stderr"
      }
      function emit_token(token,   t, first, last) {
        t = trim(token)
        if (t == "") return 0
        first = substr(t, 1, 1)
        last = substr(t, length(t), 1)
        if ((first == "\"" && last == "\"") || (first == "\047" && last == "\047")) {
          t = substr(t, 2, length(t) - 2)
        }
        if (t == "") return 0
        print t
        return 1
      }
      function parse_array(array_text,   inner, i, c, token, in_quote, quote_char, esc, emitted) {
        array_text = trim(array_text)
        if (substr(array_text, 1, 1) != "[" || substr(array_text, length(array_text), 1) != "]") {
          return -1
        }
        inner = substr(array_text, 2, length(array_text) - 2)
        token = ""
        in_quote = 0
        quote_char = ""
        esc = 0
        emitted = 0

        for (i = 1; i <= length(inner); i++) {
          c = substr(inner, i, 1)
          if (in_quote) {
            token = token c
            if (esc) {
              esc = 0
              continue
            }
            if (c == "\\" && quote_char == "\"") {
              esc = 1
              continue
            }
            if (c == quote_char) {
              in_quote = 0
              quote_char = ""
            }
            continue
          }

          if (c == "\"" || c == "\047") {
            in_quote = 1
            quote_char = c
            token = token c
            continue
          }
          if (c == ",") {
            emitted += emit_token(token)
            token = ""
            continue
          }
          token = token c
        }

        if (in_quote) return -1
        emitted += emit_token(token)
        return emitted
      }
      BEGIN { section = "" }
      {
        line = strip_comment($0)
        line = trim(line)
        if (line == "") next

        if (line ~ /^\[[^]]+\]$/) {
          section = substr(line, 2, length(line) - 2)
          next
        }

        if (section == "skills" && line ~ /^pinned[[:space:]]*=/ && !in_pinned_array) {
          value = line
          sub(/^pinned[[:space:]]*=[[:space:]]*/, "", value)
          value = trim(value)
          saw_pinned = 1
          pinned_start_line = NR

          if (value !~ /^\[/) {
            warn("Invalid [skills].pinned in " FILENAME ":" NR " (expected array)")
            next
          }

          pinned_value = value
          if (index(value, "]") > 0) {
            parsed_count = parse_array(pinned_value)
            if (parsed_count < 0) {
              warn("Invalid [skills].pinned array in " FILENAME ":" pinned_start_line)
            }
            pinned_value = ""
          } else {
            in_pinned_array = 1
          }
          next
        }

        if (in_pinned_array) {
          pinned_value = pinned_value " " line
          if (index(line, "]") > 0) {
            parsed_count = parse_array(pinned_value)
            if (parsed_count < 0) {
              warn("Invalid multiline [skills].pinned array in " FILENAME ":" pinned_start_line)
            }
            pinned_value = ""
            in_pinned_array = 0
          }
        }
      }
      END {
        if (in_pinned_array) {
          warn("Unclosed multiline [skills].pinned array in " FILENAME ":" pinned_start_line)
        } else if (saw_pinned && parsed_count < 0) {
          warn("Failed to parse [skills].pinned in " FILENAME)
        }
      }
    ' "$config_file"
  )
}

# ─── Agent Loading ──────────────────────────────────────────────────────────
# Searches discovery dirs in order, returns path to first <name>.md found.

resolve_agent_file() {
  local name="$1"
  local dirs=("$AGENTS_DIR" "$REPO_ROOT/.agents/agents" "$REPO_ROOT/.claude/agents")
  for dir in "${dirs[@]}"; do
    local candidate="$dir/$name.md"
    if [[ -f "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
  done
  echo "ERROR: Agent profile not found: $name" >&2
  echo "  Searched: ${dirs[*]}" >&2
  return 1
}

# Loads agent profile, sets globals from frontmatter (model, variant, skills, sandbox, tools).
# CLI flags always override profile defaults.
load_agent_profile() {
  local agent_file
  agent_file="$(resolve_agent_file "$AGENT_NAME")" || exit 1

  # Extract YAML frontmatter
  local frontmatter
  frontmatter="$(awk '
    BEGIN { in_fm=0; past_fm=0 }
    /^---$/ {
      if (!past_fm) {
        if (in_fm) { past_fm=1; next }
        else { in_fm=1; next }
      }
    }
    in_fm && !past_fm { print }
  ' "$agent_file")"

  # Extract body (frontmatter stripped)
  AGENT_BODY="$(awk '
    BEGIN { in_fm=0; past_fm=0 }
    /^---$/ {
      if (!past_fm) {
        if (in_fm) { past_fm=1; next }
        else { in_fm=1; next }
      }
    }
    past_fm || !in_fm { if (past_fm || NR > 1 || !/^---$/) print }
  ' "$agent_file")"

  # Parse model: (only if not set from CLI)
  if [[ "$MODEL_FROM_CLI" != true ]]; then
    local profile_model
    profile_model="$(echo "$frontmatter" | sed -n 's/^model:[[:space:]]*//p' | xargs)"
    if [[ -n "$profile_model" ]]; then
      MODEL="$profile_model"
    fi
  fi

  # Parse variant: (only if not set from CLI)
  if [[ "$VARIANT_FROM_CLI" != true ]]; then
    local profile_variant
    profile_variant="$(echo "$frontmatter" | sed -n 's/^variant:[[:space:]]*//p' | xargs)"
    if [[ -n "$profile_variant" ]]; then
      VARIANT="$profile_variant"
    fi
  fi

  # Parse skills: merge with CLI --skills
  while IFS= read -r s; do
    append_skill_if_missing "$s"
  done < <(_parse_yaml_list "skills" "$frontmatter")

  # Parse sandbox: (orchestrate extension, used for Codex only)
  local profile_sandbox
  profile_sandbox="$(echo "$frontmatter" | sed -n 's/^sandbox:[[:space:]]*//p' | xargs)"
  if [[ -n "$profile_sandbox" ]]; then
    AGENT_SANDBOX="$profile_sandbox"
  fi

  # Parse tools: stored as comma-separated string
  local tools_csv=""
  while IFS= read -r t; do
    [[ -z "$t" ]] && continue
    [[ -n "$tools_csv" ]] && tools_csv+=","
    tools_csv+="$t"
  done < <(_parse_yaml_list "tools" "$frontmatter")
  if [[ -n "$tools_csv" ]]; then
    AGENT_TOOLS="$tools_csv"
  fi
}

# ─── YAML List Parser ────────────────────────────────────────────────────────
# Parses both inline [a, b] and multiline YAML lists from frontmatter.
# Outputs one item per line, trimmed.

_parse_yaml_list() {
  local key="$1"
  local frontmatter="$2"

  # Try inline format first: key: [a, b, c]
  local inline
  inline="$(echo "$frontmatter" | sed -n "s/^${key}:[[:space:]]*\[//p")"
  if [[ -n "$inline" ]]; then
    inline="${inline%]}"
    IFS=',' read -ra items <<< "$inline"
    for item in "${items[@]}"; do
      item="$(echo "$item" | xargs)"
      [[ -n "$item" ]] && echo "$item"
    done
    return
  fi

  # Try multiline format:
  #   key:
  #     - item1
  #     - item2
  local in_list=false
  while IFS= read -r line; do
    if [[ "$in_list" == true ]]; then
      if [[ "$line" =~ ^[[:space:]]+-[[:space:]]+(.*) ]]; then
        local item="${BASH_REMATCH[1]}"
        item="$(echo "$item" | xargs)"
        [[ -n "$item" ]] && echo "$item"
      elif [[ "$line" =~ ^[[:space:]]*$ ]]; then
        continue
      else
        break  # next key or end of list
      fi
    elif [[ "$line" =~ ^${key}:[[:space:]]*$ ]]; then
      in_list=true
    fi
  done <<< "$frontmatter"
}

# ─── Model Routing ───────────────────────────────────────────────────────────
# Returns the CLI tool family for a given model name.

route_model() {
  local model="$1"
  case "$model" in
    opus*|sonnet*|haiku*|claude-*)
      echo "claude"
      ;;
    gpt-*|o1*|o3*|o4*|codex*)
      echo "codex"
      ;;
    opencode-*|*/*)
      echo "opencode"
      ;;
    *)
      echo "ERROR: Unknown model family: $model" >&2
      echo "  Supported: claude-*, gpt-*/codex*, opencode-*, provider/model" >&2
      return 1
      ;;
  esac
}

# Strip opencode- prefix before passing to the CLI.
# provider/model format (e.g. opencode/kimi-k2.5-free) is passed through unchanged.
strip_model_prefix() {
  echo "${1#opencode-}"
}

# ─── Template Substitution ───────────────────────────────────────────────────

apply_template_vars() {
  local text="$1"
  for key in "${!VARS[@]}"; do
    text="${text//\{\{$key\}\}/${VARS[$key]}}"
  done
  echo "$text"
}

json_escape() {
  local text="$1"
  text="${text//\\/\\\\}"
  text="${text//\"/\\\"}"
  text="${text//$'\n'/\\n}"
  text="${text//$'\r'/\\r}"
  text="${text//$'\t'/\\t}"
  echo "$text"
}

build_skills_json() {
  local json=""
  local skill
  for skill in "${SKILLS[@]}"; do
    [[ -n "$json" ]] && json+=", "
    json+="\"$(json_escape "$skill")\""
  done
  echo "[$json]"
}

build_labels_json() {
  local json=""
  local key

  for key in "${!LABELS[@]}"; do
    [[ -n "$json" ]] && json+=", "
    json+="\"$(json_escape "$key")\":\"$(json_escape "${LABELS[$key]}")\""
  done
  echo "{$json}"
}

# ─── Compose Prompt ──────────────────────────────────────────────────────────

compose_prompt() {
  local composed=""

  # Task prompt first — it's the primary instruction.
  if [[ -n "$PROMPT" ]]; then
    composed+="$PROMPT"$'\n'
  fi

  # Reference files
  if [[ ${#REF_FILES[@]} -gt 0 ]]; then
    composed+=$'\n'"# Reference Files"$'\n\n'
    for ref in "${REF_FILES[@]}"; do
      local resolved_ref="$ref"
      if [[ "$HAS_VARS" == true ]]; then
        resolved_ref="$(apply_template_vars "$ref")"
      fi
      composed+="- $resolved_ref"$'\n'
    done
  fi

  # Inject agent body for Codex (which has no native --agent flag).
  # Claude Code and OpenCode load the agent profile natively via --agent.
  if [[ -n "$AGENT_NAME" ]] && [[ -n "$AGENT_BODY" ]]; then
    local harness
    harness="$(route_model "$MODEL" 2>/dev/null || echo "")"
    if [[ "$harness" == "codex" ]]; then
      composed+=$'\n'"# Agent: $AGENT_NAME"$'\n\n'
      composed+="$AGENT_BODY"$'\n\n'
    fi
  fi

  # List skills by name — harnesses load them natively from their skill directories.
  # Claude Code: .claude/skills/  |  OpenCode: .agents/skills/  |  Codex: .agents/skills/
  if [[ ${#SKILLS[@]} -gt 0 ]]; then
    composed+=$'\n'"# Skills"$'\n\n'
    composed+="Use these skills to complete your task:"$'\n\n'
    for skill in "${SKILLS[@]}"; do
      composed+="- $skill"$'\n'
    done
  fi

  # Apply template variables
  if [[ "$HAS_VARS" == true ]]; then
    composed="$(apply_template_vars "$composed")"
  fi

  echo "$composed"
}

# ─── Report Instruction ─────────────────────────────────────────────────────
# Appended to prompt so the subagent writes a report file the orchestrator can read.

build_output_dir_instruction() {
  local log_dir="$1"
  cat <<EOF

# Output Directory

Write any output files to: \`$log_dir/\`
EOF
}

build_report_instruction() {
  local report_path="$1"
  local level="$2"
  local detail_guide=""

  case "$level" in
    brief)
      detail_guide="Keep the report concise. Focus on: what was done, pass/fail status, any blockers."
      ;;
    standard)
      detail_guide="Include: what was done, key decisions made, files created/modified, verification results, and any issues or blockers."
      ;;
    detailed)
      detail_guide="Be thorough: what was done, reasoning behind decisions, all files touched with descriptions, full verification results, issues found, and recommendations for next steps."
      ;;
  esac

  cat <<EOF

# Report

**IMPORTANT — As your FINAL action**, write a report of your work to: \`$report_path\`

$detail_guide

Use plain markdown. This file is read by the orchestrator to understand what you did without parsing verbose logs.
EOF
}
