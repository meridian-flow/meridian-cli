/**
 * Meridian compaction plugin for OpenCode.
 *
 * On context compaction, re-injects agent profile and skill content that would
 * otherwise be lost. Reads resolved file paths from the Meridian session record
 * (sessions.jsonl) so no search logic or config parsing is needed.
 */

import * as fs from "fs"
import * as path from "path"

interface SessionRecord {
  chatId: string
  harnessSessionId: string
  agentPath: string
  skillPaths: string[]
}

function parseSessionRecords(jsonlPath: string): SessionRecord[] {
  let content: string
  try {
    content = fs.readFileSync(jsonlPath, "utf-8")
  } catch {
    return []
  }

  const records = new Map<string, SessionRecord>()
  const lines = content.split("\n")

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim()
    if (!line) continue

    let row: Record<string, unknown>
    try {
      row = JSON.parse(line)
    } catch {
      // Ignore malformed lines (truncated trailing append).
      continue
    }

    const event = row.event as string
    const chatId = row.chat_id as string
    if (!chatId) continue

    if (event === "start") {
      records.set(chatId, {
        chatId,
        harnessSessionId: (row.harness_session_id as string) || "",
        agentPath: (row.agent_path as string) || "",
        skillPaths: Array.isArray(row.skill_paths)
          ? (row.skill_paths as string[])
          : [],
      })
    } else if (event === "update" && row.harness_session_id) {
      const existing = records.get(chatId)
      if (existing) {
        existing.harnessSessionId = row.harness_session_id as string
      }
    }
  }

  return Array.from(records.values())
}

function readFileContent(filePath: string): string | null {
  try {
    return fs.readFileSync(filePath, "utf-8")
  } catch {
    return null
  }
}

export default {
  name: "meridian",
  subscribe: ["experimental.session.compacting"],

  async onEvent(
    _event: string,
    input: { sessionID: string; directory?: string },
    output: { context: Array<{ title: string; content: string }> },
  ) {
    const spaceId = process.env.MERIDIAN_SPACE_ID
    if (!spaceId) return

    // Derive state root: prefer env var, fall back to cwd-based convention.
    const stateRoot =
      process.env.MERIDIAN_STATE_ROOT ||
      (input.directory
        ? path.join(input.directory, ".meridian")
        : path.join(process.cwd(), ".meridian"))

    const jsonlPath = path.join(
      stateRoot,
      ".spaces",
      spaceId,
      "sessions.jsonl",
    )
    const records = parseSessionRecords(jsonlPath)
    if (records.length === 0) return

    // Find the newest record matching this OpenCode session ID.
    const sessionId = input.sessionID
    let match: SessionRecord | null = null
    for (const record of records) {
      if (record.harnessSessionId === sessionId) {
        match = record // last match = newest (file is append-order)
      }
    }
    if (!match) return

    // Re-inject agent profile body.
    if (match.agentPath) {
      const content = readFileContent(match.agentPath)
      if (content) {
        const name = path.basename(match.agentPath, path.extname(match.agentPath))
        output.context.push({
          title: `Agent: ${name}`,
          content: content.trim(),
        })
      }
    }

    // Re-inject skill contents.
    for (const skillPath of match.skillPaths) {
      const content = readFileContent(skillPath)
      if (!content) continue

      const skillDir = path.basename(path.dirname(skillPath))
      output.context.push({
        title: `Skill: ${skillDir}`,
        content: content.trim(),
      })
    }
  },
}
