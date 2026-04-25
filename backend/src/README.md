# Src

Thin orchestration layer for the local Xiaohongshu + AI backend.

- `main.py`: CLI entrypoint
- `jobs.py`: one-shot command flows
- `scheduler.py`: Beijing-time scheduled runner

## Commands

```bash
python backend/src/main.py login --config data/config/watchlist.json
python backend/src/main.py migrate-json-to-sqlite
python backend/src/main.py run-once --config data/config/watchlist.json
python backend/src/main.py run-once-x --config data/config/x_watchlist.json
python backend/src/main.py run-scheduler --config data/config/watchlist.json
```

## Xiaohongshu Login

`login` now uses a project-scoped persistent Chrome user data directory at
`data/runtime/state/xhs_chrome_user_data/`.

- After upgrading, run `login` once again to establish a fresh session.
- `run-once` and `run-scheduler` no longer depend on `xhs_storage_state.json`.
