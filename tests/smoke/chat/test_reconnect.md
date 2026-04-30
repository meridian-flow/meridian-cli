# Chat backend reconnect smoke test

1. Create a chat and connect WebSocket client A.
2. Produce several events through prompts or a scripted harness.
3. Disconnect client A, record its last received `seq`, reconnect with `?last_seq=<seq>`.
4. Verify no gap: replay begins at `last_seq + 1`, then live events continue.
5. Connect a slow client and force buffer overflow in a test harness; verify close reason asks the client to reconnect with `last_seq`.
