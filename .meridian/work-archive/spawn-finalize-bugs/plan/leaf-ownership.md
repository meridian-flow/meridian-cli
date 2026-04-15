# Leaf Ownership

| EARS ID | Description | Phase | Status | Evidence |
|---------|-------------|-------|--------|----------|
| B-01 | Idle → finalized never fires | Phase 1 | verified | streaming_runner.py:246-247 — turn/completed → succeeded/0 |
| B-02 | Cancel origin mis-tagged | Phase 1 | verified | spawn_manager.py:343-349 — cancel_sent → cancelled/143 |
| B-03 | SIGKILL classified as succeeded | Phase 1 | verified | streaming_runner.py:249-254 — error/connectionClosed → failed/1 |
| B-04 | /inject 400 vs 422 | Phase 2 | verified | server.py:181-183 — scoped to "mutually exclusive" only |
| B-05 | Report create deletion | Phase 3 | verified | report_cmd.py, manifest.py, report.py, prompt.py, docs — create removed |
