# codex-clean

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)]()
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

**A safe, confirm-before-clean tool that frees disk space from Codex's own cache, logs, and WAL files — never touching your conversations, configs, or projects.**

`codex-clean` targets only the regenerable, self-produced data inside `~/.codex` that grows over time (temporary plugin downloads, plugin cache, the diagnostic `logs_2.sqlite` database and its write-ahead-log, plus bloat in state databases via `VACUUM`). Conversation history, state data, authentication, configuration, and Codex executables are **never** touched.

> Also packaged as a [Codex Agent Skill](#install-as-a-codex-skill): say *"clean Codex cache"* in Codex and it runs scan-confirm-clean for you.

---

## Why

Codex (CLI/Desktop) keeps several things under `~/.codex` that grow without bound:

| Item | Role | Growth |
|---|---|---|
| `~/.codex/.tmp` | Temp downloads / extracted plugins | Hundreds of MB |
| `~/.codex/plugins/cache` | Plugin cache (re-downloadable) | Depends on plugins |
| `~/.codex/logs_2.sqlite` | Diagnostic log DB (**not** conversation history) | Reported to reach GBs; WAL adds SSD write amplification |

`logs_2.sqlite` only contains diagnostic logs — deleting or rebuilding it does **not** affect your chat history (that lives in `state_5.sqlite` / `sessions/`), which is why cleaning it is safe.

## What it cleans (strict whitelist)

**A. Delete (regenerable — Codex recreates on demand)**

| Item | Path |
|---|---|
| `tmp` | `~/.codex/.tmp` |
| `tmp2` | `~/.codex/tmp` |
| `plugin-cache` | `~/.codex/plugins/cache` |

**B. VACUUM + WAL cleanup (data preserved, space reclaimed)** — runs `PRAGMA wal_checkpoint(TRUNCATE)` + `VACUUM` on:

`logs_2.sqlite` · `state_5.sqlite` · `thread_history_1.sqlite` · `queue_1.sqlite` · `goals_1.sqlite` · `memories_1.sqlite`

**C. Rebuild oversized log DB (optional)** — if `logs_2.sqlite` exceeds 100 MB, back it up and let Codex recreate an empty one.

## What it NEVER touches

- Codex executables & runtimes: `bin/`, `runtimes/`
- Conversation history: `sessions/`
- Data inside state/memory/goals DBs (only VACUUM, never deletion)
- Config: `config.toml`, `auth.json`, `model-catalogs/`, `backups/`
- Your project files & work directories

## Install

```bash
git clone https://github.com/Merlin-Arthur05/codex-clean.git
cd codex-clean
python scripts/codex_clean.py --scan
```

Pure standard-library Python 3.8+. No dependencies.

## Usage

```bash
# 1. Read-only scan (safe default) — shows what can be reclaimed
python scripts/codex_clean.py --scan

# 2. Interactive: confirm each item before cleaning
python scripts/codex_clean.py --clean

# 3. Non-interactive: clean all safe "delete + WAL" items
python scripts/codex_clean.py --clean --yes

# 4. Recommended full cleanup: also VACUUM the SQLite DBs
python scripts/codex_clean.py --clean --yes --vacuum

# 5. Also rebuild an oversized log DB (>100 MB, backs up first)
python scripts/codex_clean.py --clean --yes --rebuild-logs

# 6. Machine-readable output
python scripts/codex_clean.py --scan --json
```

> **Best practice:** fully quit Codex (CLI, Desktop, IDE extension) before `--clean`, so no process holds an open handle on deleted files — otherwise disk space isn't reclaimed until the process exits.

## Install as a Codex Skill

```bash
mkdir -p ~/.codex/skills/codex-clean
cp SKILL.md ~/.codex/skills/codex-clean/
cp -r scripts ~/.codex/skills/codex-clean/
```

Then in Codex just say: **"清理 Codex 缓存"** / **"Codex 日志太多"** / **"Codex 占空间"** / **"clean Codex cache"** — it will read the skill, scan, and confirm with you before cleaning.

## Roadmap / Ideas

- Automatic WAL-growth watchdog suggestion (periodic scan reminder).
- `--age N` filtering for stale temp files.
- Optional integration as a Windows scheduled task (opt-in only).

## License

[MIT](LICENSE) © Merlin-Arthur05

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). PRs welcome — but the safety contract is strict: never add destructive defaults, keep protected items protected, stay stdlib-only.
