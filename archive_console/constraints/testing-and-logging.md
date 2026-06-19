# Testing and logging (Archive Console)

- **Tests:** Prefer small unit tests for pure helpers (path merge, archive resolution, log line patterns); use subprocess mocks for drivers when the behavior is policy, not the child process.
- **Logs:** Never log secrets (`cookies.txt` contents, tokens in URLs). For spawn failures, log a short argv summary (basenames) and stderr tail; operator-facing lines stay in run logs without dumping full archive databases.
