# Leaf Ownership

| EARS ID | Statement | Phase | Tester Lane | Evidence |
|---------|-----------|-------|-------------|----------|
| WIN-01 | When platform is Windows, the system SHALL skip PTY branch and use subprocess.Popen passthrough | 1 | verifier | |
| WIN-02 | When platform is Windows OR `--port` is specified, the app server SHALL bind to TCP localhost instead of Unix socket | 1 | smoke-tester | |
| WIN-03 | When platform is Windows, the control socket SHALL use TCP with dynamic port allocation and write `control.port` for discovery | 1 | verifier | |
| WIN-04 | When platform is Windows, signal canceller SHALL use TCP connector with port file discovery instead of Unix socket | 1 | verifier | |
