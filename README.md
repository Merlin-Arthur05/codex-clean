# codex-clean

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)]()
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

**A safe, confirm-before-clean tool that frees disk space from AI coding agents' cache, logs, and WAL files — built for OpenAI Codex, with more agents on the roadmap. Never touches your conversations, configs, or projects.**

[English](README.md) | [简体中文](README.zh-CN.md)

`codex-clean` targets only the regenerable, self-produced data inside `~/.codex` that grows over time (temporary plugin downloads, plugin cache, the diagnostic `logs_2.sqlite` database and its write-ahead-log, plus bloat in state databases via `VACUUM`). Conversation history, state data, authentication, configuration, and Codex executables are **never** touched. Codex is the first - and currently the only fully supported - agent; pi and opencode are on the roadmap (see [Supported agents](#supported-agents)).

> Also packaged as a [Codex Agent Skill](#install-as-a-codex-skill) (available in [English](SKILL.md) and [简体中文](SKILL.zh-CN.md)): say *"clean Codex cache"* in Codex and it runs scan-confirm-clean for you.

---

## Supported agents

`codex-clean` is built **primarily for OpenAI Codex**, and is already structured to support more agents. Every agent gets the same scan -> confirm -> clean flow and protected-list safety contract.

| Agent | Status | What gets cleaned |
|---|---|---|
| **OpenAI Codex** | Supported (current) | `~/.codex` cache, logs, WAL, and state-DB bloat |
| **pi** - [@earendil-works/pi-coding-agent](https://www.npmjs.com/package/@earendil-works/pi-coding-agent) | Planned - v1.4.0 ([#10](https://github.com/Merlin-Arthur05/codex-clean/issues/10)) | `~/.pi` data / cache / logs |
| **opencode** - [anomalyco/opencode](https://github.com/anomalyco/opencode) | Planned - v1.4.0 ([#12](https://github.com/Merlin-Arthur05/codex-clean/issues/12)) | XDG data / log / cache + WAL-mode `opencode.db` |
| **Claude Code** | Supported (current) | `~/.claude` cache / logs (JSONL data - no SQLite, so VACUUM does not apply) |

The per-agent registry refactor that makes adding an agent a one-line spec is tracked in [#11](https://github.com/Merlin-Arthur05/codex-clean/issues/11); see [Roadmap](#roadmap--ideas).
## Not a generic computer cleaner

`codex-clean` does **not** scan your disk, organize files, or clean your whole
machine. Generic cleanup skills (e.g. `qing-li-dian-nao`) target the entire
computer; this tool targets the runtime data of **one app — Codex**, and adds
capabilities generic cleaners don't have:

| Dimension | codex-clean | Generic computer cleanup |
|---|---|---|
| Scope | Only Codex's own `~/.codex` | Whole-machine disk / files |
| Unique capability | SQLite **VACUUM + WAL checkpoint**, oversized log-DB rebuild | Generic file scanning |
| Output language | Bilingual (en/zh), follows client language | Single language |
| Trigger | "Codex cache / logs / disk usage" | "clean my computer / organize files / disk full" |

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

## Multi-agent targets

One codebase, one scan -> confirm -> clean flow. Each agent is a single entry in the
`AGENTS` registry inside the script, so differences are **data, not branches**:

| | Codex (default) | Claude Code |
|---|---|---|
| Data directory | `~/.codex` (override `CODEX_HOME`) | `~/.claude` (override `CLAUDE_HOME`) |
| Data format | SQLite (+ WAL/SHM) | JSONL / plain files |
| VACUUM + WAL cleanup | yes | **not applicable** (no SQLite) |
| Oversized log-DB rebuild | yes | **not applicable** |
| How to select | default | `--target claude-code` |

What each agent may touch (strict whitelist, everything else is protected):

- **Codex** — cleans `.tmp/`, `tmp/`, `plugins/cache/`; VACUUMs the six SQLite DBs.
  Protects `sessions/`, `config.toml`, `auth.json`, `skills/`, `rules/`, `backups/`.
- **Claude Code** — cleans `cache/`, `debug/`, `shell-snapshots/`, `statsig/`.
  Protects `projects/` (your conversations), `memory/`, `plugins/`, `skills/`,
  `settings.json`, `config.json`, `sessions/`, `ide/`, `history.jsonl`.

> Because Claude Code stores conversations as JSONL, `--vacuum` and `--rebuild-logs`
> simply do not apply there — the tool tells you so instead of failing.

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

# 6. Only clean temp files older than 7 days (keeps recent files)
python scripts/codex_clean.py --scan --age 7
python scripts/codex_clean.py --clean --yes --age 7

# 7. Machine-readable output (includes a per-item "what would happen" preview)
python scripts/codex_clean.py --scan --json

# 8. JSON cleanup report — estimated vs actually freed
python scripts/codex_clean.py --clean --yes --vacuum --json

# 9. Choose output language: en | zh | auto (default)
python scripts/codex_clean.py --scan --lang zh

# 10. Clean a different agent (Claude Code)
python scripts/codex_clean.py --scan --target claude-code
python scripts/codex_clean.py --clean --yes --target claude-code
```

### `--age N` — filter by file age

With `--age N`, **delete** items only touch files whose modification time is
older than N days; newer files are left alone. Useful when you don't want to
wipe an entire cache, and it avoids deleting files Codex may be actively using.

- On scan: `size` shows the **eligible** (reclaimable) bytes, `total_size` shows
  the whole directory.
- On clean: only aged files are removed, plus directories left empty by that.
- Applies to delete items only; VACUUM / rebuild are unaffected (they shrink
  existing databases and involve no file ages).

### `--json` output

**Scan mode** (`--scan --json`) returns an array. Alongside the stable
`name` / `kind` / `size` keys, each item carries v1.2.0 preview fields:

```jsonc
{
  "name": "tmp", "kind": "delete", "path": "...", "size": "200.0 KB",
  "age_filter_days": 7,
  "eligible_bytes": 204800, "eligible_files": 1, "total_files": 2,
  "total_size": "230.0 KB",
  "planned_action": {
    "type": "delete", "target": "...",
    "reclaimable_bytes": 204800, "reclaimable": "200.0 KB",
    "reversible": false, "confirm_required": true, "age_filter_days": 7
  },
  "safe": true
}
```

**Clean mode** (`--clean --yes --json`) returns a report whose core is the
**estimated vs actual** comparison:

```jsonc
{
  "ok": true, "dry_run": false, "version": "1.3.0",
  "estimated_bytes": 215040, "actual_freed_bytes": 204800, "delta_bytes": -10240,
  "items": [
    { "name": "tmp", "kind": "delete", "status": "ok",
      "estimated_bytes": 204800, "actual_bytes": 204800, "message": "..." }
  ],
  "protected_untouched": ["sessions", "config.toml", "auth.json", "..."]
}
```

> `--clean --json` requires `--yes` (JSON mode cannot prompt interactively).

For VACUUM items, `actual_bytes` is the **measured** shrink (main DB + WAL + SHM
before vs after `VACUUM`), not an estimate — so the delta tells you how far
reality landed from the prediction.

**Output language.** User-facing text (scan list, confirm prompts, results, and
the `--help` screen) is localized. Resolution order: `--lang` argument → `CODEX_CLEAN_LANG` env var →
`LANG`/`LC_ALL` → OS UI language → English. So in a Chinese client just set
`CODEX_CLEAN_LANG=zh` (or call with `--lang zh`); English tools get English by
default. `--json` output uses the localized `desc`/`action` fields with the
stable `name`/`kind` keys for machine parsing.

> **Best practice:** fully quit Codex (CLI, Desktop, IDE extension) before `--clean`, so no process holds an open handle on deleted files — otherwise disk space isn't reclaimed until the process exits.

## Install as a Codex Skill

```bash
mkdir -p ~/.codex/skills/codex-clean
cp SKILL.md ~/.codex/skills/codex-clean/   # or SKILL.zh-CN.md for the Chinese version
cp -r scripts ~/.codex/skills/codex-clean/
```

Then in Codex just say: **"清理 Codex 缓存"** / **"Codex 日志太多"** / **"Codex 占空间"** / **"clean Codex cache"** — it will read the skill, scan, and confirm with you before cleaning.

## Install as a Claude Code skill

Claude Code follows the **Agent Skills open standard** — the same format used here — so the
same `SKILL.md` body works; only the location and frontmatter differ:

```bash
mkdir -p ~/.claude/skills/codex-clean
cp SKILL.md ~/.claude/skills/codex-clean/   # or SKILL.zh-CN.md for Chinese
cp -r scripts ~/.claude/skills/codex-clean/
```

The **directory name becomes the slash command**, so type **`/codex-clean`** (or just ask
*"clean my agent cache"*) in Claude Code. Add `allowed-tools: Bash, Read` to the SKILL.md
frontmatter so it can run the script without an approval prompt.


## Roadmap / Ideas

- Automatic WAL-growth watchdog suggestion (periodic scan reminder).
- Optional integration as a Windows scheduled task (opt-in only).
- `--exclude` to skip specific databases.
- **Multi-agent support** — extend cleanup targets to other AI coding CLIs, applying the
  same scan-confirm-clean + protected-list rules:
  - **pi** ([@earendil-works/pi-coding-agent](https://www.npmjs.com/package/@earendil-works/pi-coding-agent))
    — detect its data/cache/log directories (e.g. `~/.pi`). Tracked in [#10](https://github.com/Merlin-Arthur05/codex-clean/issues/10).
  - **opencode** ([anomalyco/opencode](https://github.com/anomalyco/opencode)) — its XDG
    data/log/cache directories plus the WAL-mode `opencode.db`
    (`~/.local/share/opencode/opencode.db` on Linux). Tracked in [#12](https://github.com/Merlin-Arthur05/codex-clean/issues/12).
  - **Claude Code** - `~/.claude` cache and logs. Conversations are stored as **JSONL, not SQLite**, so VACUUM / log-DB rebuild do not apply; these become per-agent capability flags rather than hardcoded branches. Also ships as a `/codex-clean` slash command ([#14](https://github.com/Merlin-Arthur05/codex-clean/issues/14)). Tracked in [#13](https://github.com/Merlin-Arthur05/codex-clean/issues/13).
  - Refactor cleanup targets into a **per-agent registry** so adding an agent needs only
    one spec entry. Tracked in [#11](https://github.com/Merlin-Arthur05/codex-clean/issues/11).

All tracked on the [project board](https://github.com/users/Merlin-Arthur05/projects/3).

## Tests

```bash
python tests/test_codex_clean.py   # 28 regression checks, standard library only
```

The suite points `CODEX_HOME` / `CLAUDE_HOME` at throwaway temp directories, so it never
touches a real agent home.

## License

[MIT](LICENSE) © Merlin-Arthur05

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) ([简体中文](CONTRIBUTING.zh-CN.md)). PRs welcome — but the safety contract is strict: never add destructive defaults, keep protected items protected, stay stdlib-only.
