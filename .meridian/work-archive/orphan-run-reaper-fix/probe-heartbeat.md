# Heartbeat Probe

## Empirical gap distribution

*Timing source:* `output.jsonl` itself is not line-timestamped. For Claude/Codex I used the underlying harness session logs referenced by the spawn artifacts; for OpenCode I used the embedded `time.created`/`time.updated` fields in the event payloads.

| harness | sample size | p50 inter-line gap | p95 inter-line gap | max inter-line gap | spawn IDs checked |
|---|---:|---:|---:|---:|---|
| claude | 12 | 0.304s | 23.059s | 153.922s | `p1677,p1679,p1702,p1703,p1705,p1711,p1716,p1717,p1719,p1720,p1734,p1736` |
| codex | 12 | 0.008s | 7.639s | 86.799s | `p1726,p1727,p1728,p1729,p1730,p1731,p1732,p1733,p1735,p1737,p1738,p1739` |
| opencode | 10 | 0.006s | 0.092s | 1.201s | `p750,p1338,p1499,p1502,p1507,p1510,p1513,p1539,p1543,p1545` |

## Harness-specific silence scenarios

- Claude: healthy long silence is real. In `p1736`, the largest gap was 153.922s while a background `meridian spawn wait p1737 p1738 p1739` command was still running; the next event was a task-completion notification. The adapter itself blocks on `stdout.readline()` and only emits when Claude writes a line, so long model-thinking gaps, tool round-trips, and approval waits are all silent by construction.
- Codex: healthy long silence is also real. In `p1727`, the worst gap was 86.799s between two successive response items in the session log. The websocket reader in `codex_ws.py` waits on inbound messages with no keepalive or periodic emit, so long tool execution, model thinking, and approval waits can go quiet for >60s.
- OpenCode: no >60s gap showed up in this sample, but the SSE loop in `opencode_http.py` only yields when chunks arrive and does not synthesize a heartbeat. A healthy server can therefore sit silent indefinitely while thinking or waiting on work; the sample is too small to prove a safe upper bound.

## Recommendation

**Runner heartbeat needed.** Do not rely on `output.jsonl` / `stderr.log` mtimes for `running`. Add a runner-owned periodic heartbeat touch on a 30s tick so the reaper can distinguish live-but-silent runs from dead ones. Keep the 120s window for `finalizing`, where the post-exit work is bounded.

### Evidence pointers

- Stream capture flushes every line immediately and flushes stderr chunks immediately: [`src/meridian/lib/launch/stream_capture.py`](</home/jimyao/gitrepos/meridian-cli/src/meridian/lib/launch/stream_capture.py:74>)
- Claude blocks on `stdout.readline()` with no timer: [`src/meridian/lib/harness/connections/claude_ws.py`](</home/jimyao/gitrepos/meridian-cli/src/meridian/lib/harness/connections/claude_ws.py:197>)
- Codex blocks on websocket receive with no keepalive: [`src/meridian/lib/harness/connections/codex_ws.py`](</home/jimyao/gitrepos/meridian-cli/src/meridian/lib/harness/connections/codex_ws.py:466>)
- OpenCode blocks on SSE chunk arrival and only retries after drops: [`src/meridian/lib/harness/connections/opencode_http.py`](</home/jimyao/gitrepos/meridian-cli/src/meridian/lib/harness/connections/opencode_http.py:247>)
