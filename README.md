# codex-clean

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)]()
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

**A safe, confirm-before-clean tool that frees disk space from AI coding agents' cache, logs, and WAL files. Supports OpenAI Codex, Claude Code, and Pi. Never touches your conversations, configs, or projects.**

[English](README.md) | [简体中文](README.zh-CN.md)

`codex-clean` targets only the regenerable, self-produced data inside each agent's home directory — temporary downloads, caches, diagnostic logs and their write-ahead-logs, plus bloat in state databases via `VACUUM`. Conversation history, state data, authentication, configuration, and agent executables are **never** touched.

| Agent | Home | Select with |
|---|---|---|
| **OpenAI Codex** (default) | `~/.codex` (`CODEX_HOME`) | *(default)* |
| **Claude Code** | `~/.claude` (`CLAUDE_HOME`) | `--target claude-code` |
| **Pi** | `~/.pi/agent` (`PI_AGENT_HOME`) | `--target pi` |
| *all of the above* | — | `--target all` |

Each agent's home is resolved at runtime from its environment variable, falling back to the default path — nothing is hardcoded to one machine.

> Also packaged as an [Agent Skill](#install-as-a-skill) (available in [English](SKILL.md) and [简体中文](SKILL.zh-CN.md)) for Codex, Claude Code, and Pi: say *"clean my agent cache"* and it runs scan-confirm-clean for you.

---

## Supported agents

`codex-clean` handles **three agents** today, each with the same scan -> confirm -> clean flow and protected-list safety contract. Adding another is a single entry in the `AGENTS` registry — differences are **data, not branches**.

| Agent | Status | What gets cleaned |
|---|---|---|
| **OpenAI Codex** | Supported | `~/.codex` tmp, plugin cache, logs, WAL, state-DB bloat |
| **Claude Code** | Supported | `~/.claude` cache, debug, shell-snapshots, statsig |
| **Pi** | Supported | `~/.pi/agent` cache, tmp, logs, debug log |
| **opencode** | Planned — v1.5.0 ([#12](https://github.com/Merlin-Arthur05/codex-clean/issues/12)) | XDG data / log / cache + WAL-mode `opencode.db` |

## Not a generic computer cleaner

`codex-clean` does **not** scan your disk, organize files, or clean your whole
machine. Generic cleanup skills (e.g. `qing-li-dian-nao`) target the entire
computer; this tool targets the runtime data of **AI coding agents**, and adds
capabilities generic cleaners don't have:

| Dimension | codex-clean | Generic computer cleanup |
|---|---|---|
| Scope | Only registered agents' own homes (`~/.codex`, `~/.claude`, `~/.pi/agent`) | Whole-machine disk / files |
| Unique capability | SQLite **VACUUM + WAL checkpoint**, oversized log-DB rebuild | Generic file scanning |
| Output language | Bilingual (en/zh), follows client language | Single language |
| Trigger | "Codex / Claude Code / Pi cache, logs, disk usage" | "clean my computer / organize files / disk full" |

## Why

AI coding agents accumulate regenerable data in their home directory that grows without bound. Codex is a good example (CLI/Desktop), under `~/.codex`:

| Item | Role | Growth |
|---|---|---|
| `~/.codex/.tmp` | Temp downloads / extracted plugins | Hundreds of MB |
| `~/.codex/plugins/cache` | Plugin cache (re-downloadable) | Depends on plugins |
| `~/.codex/logs_2.sqlite` | Diagnostic log DB (**not** conversation history) | Reported to reach GBs; WAL adds SSD write amplification |

`logs_2.sqlite` only contains diagnostic logs — deleting or rebuilding it does **not** affect your chat history (that lives in `state_5.sqlite` / `sessions/`), which is why cleaning it is safe. The same principle applies to every agent: only regenerable data is ever in scope.

## What it cleans

Everything below sits inside the selected agent's home. Anything not listed is protected.

| Agent | Deleted (regenerable) | VACUUM + WAL | Rebuild log DB |
|---|---|---|---|
| **Codex** | `.tmp/`, `tmp/`, `plugins/cache/` | 6 known SQLite DBs | yes, if `logs_2.sqlite` > 100 MB |
| **Claude Code** | `cache/`, `debug/`, `shell-snapshots/`, `statsig/` | auto-discovered | not applicable |
| **Pi** | `cache/`, `tmp/`, `logs/`, `pi-debug.log` | auto-discovered | not applicable |

- **VACUUM** runs `PRAGMA wal_checkpoint(TRUNCATE)` + `VACUUM`: data is preserved, only space is reclaimed.
- **Auto-discovered** means the scan globs `*.sqlite` / `*.sqlite3` / `*.db` in the agent's home at scan time, rather than relying on a hardcoded list. If an agent has no databases, the flag reports "not applicable" instead of failing.
- Codex's `logs_2.sqlite` holds **diagnostic logs only** — rebuilding it never touches chat history (that lives in `state_5.sqlite` / `sessions/`).

## What it NEVER touches

Every agent's own protected set, enforced by the registry:

- **Codex** — `bin/`, `runtimes/`, `sessions/`, `config.toml`, `auth.json`, `skills/`, `rules/`, `model-catalogs/`, `backups/`
- **Claude Code** — `projects/` (your conversations), `memory/`, `plugins/`, `skills/`, `settings.json`, `config.json`, `sessions/`, `ide/`, `history.jsonl`
- **Pi** — `sessions/` (conversations), `skills/`, `npm/` (**user-installed packages**), `git/`, `bin/`, `tools/`, `prompts/`, `themes/`, `settings.json`, `trust.json`, `auth.json`, `models.json`, `AGENTS.md`, `SYSTEM.md`
- **All agents** — data *inside* state databases (VACUUM only, never deletion), and your project files & work directories

### Known limitations

Verified constraints of the agents themselves, not gaps in the tool.

- **`--rebuild-logs` (Claude Code, Pi)** — not applicable. Neither has an oversized *diagnostic log database*; their logs are plain files (`debug/` for Claude, `logs/` + `pi-debug.log` for Pi) that are already in the delete whitelist. The flag prints a "does not apply" note instead of failing.
- **`--vacuum` (Claude Code, Pi)** — *not* hardcoded as unsupported. Both declare no fixed DB list and let the scan discover databases (see above). Verified: zero such files under `~/.claude`, so the flag reports "not applicable" and starts working automatically if a future release ships one.
- **Pi's cleanable set is best-effort.** Pi's own source documents only user data under `~/.pi/agent` (`sessions/`, `skills/`, `npm/` = user-installed packages, `extensions/`, plus settings). `cache/` / `tmp/` / `logs/` are offered because they are universally regenerable and are only touched if they actually exist; the protected list guarantees user data never is.

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

# 3. Non-interactive: clean all safe items
python scripts/codex_clean.py --clean --yes

# 4. Recommended full cleanup: also VACUUM the SQLite DBs
python scripts/codex_clean.py --clean --yes --vacuum

# 5. Also rebuild an oversized log DB (>100 MB, backs up first)
python scripts/codex_clean.py --clean --yes --rebuild-logs

# 6. Only clean temp files older than 7 days (keeps recent files)
python scripts/codex_clean.py --scan --age 7

# 7. Pick an agent (Codex is the default)
python scripts/codex_clean.py --scan --target claude-code
python scripts/codex_clean.py --scan --target pi

# 8. Sweep every agent at once
python scripts/codex_clean.py --scan --target all

# 9. Machine-readable output (with a per-item "what would happen" preview)
python scripts/codex_clean.py --scan --json

# 10. Choose output language: en | zh | auto (default)
python scripts/codex_clean.py --scan --lang zh

# 11. Skip or keep specific items (name or agent:name, comma separated)
python scripts/codex_clean.py --scan --target all --exclude "state-db,pi-cache"
python scripts/codex_clean.py --scan --target all --only claude-cache

# 12. Preview a cleanup without changing anything
python scripts/codex_clean.py --clean --dry-run --target codex

# 13. Inspect supported agents and their capabilities
python scripts/codex_clean.py --list-targets

# 14. Automation: exit 3 when reclaimable space reaches 500 MB
python scripts/codex_clean.py --scan --check 500
```

### `--age N` — filter by file age

With `--age N`, **delete** items only touch files whose modification time is
older than N days; newer files are left alone. Useful when you don't want to
wipe an entire cache, and it avoids deleting files an agent may be actively using.

- On scan: `size` shows the **eligible** (reclaimable) bytes, `total_size` shows
  the whole directory.
- On clean: only aged files are removed, plus directories left empty by that.
- Applies to delete items only; VACUUM / rebuild are unaffected (they shrink
  existing databases and involve no file ages).

### `--json` output

**Scan mode** (`--scan --json`) returns an array. Alongside the stable
`name` / `kind` / `size` keys, each item carries a preview of the action:

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
  "ok": true, "dry_run": false, "version": "1.6.0",
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
`LANG`/`LC_ALL` → OS UI language → English. `--json` output keeps the stable
`name`/`kind` keys for machine parsing and localizes only the `desc`/`action` fields.

> **Best practice:** fully quit the target agent before `--clean`, so no process holds an open handle on deleted files — otherwise disk space isn't reclaimed until the process exits.

## Install as a Skill

`codex-clean` ships a single `SKILL.md` that follows the **Agent Skills open standard**, so the same body works in Codex, Claude Code, and Pi. Only the install path and the frontmatter differ:

| Agent | Install path | Invoke with |
|---|---|---|
| **Codex** | `~/.codex/skills/codex-clean/` | *"clean Codex cache"* |
| **Claude Code** | `~/.claude/skills/codex-clean/` | **`/codex-clean`** |
| **Pi** | `~/.pi/agent/skills/codex-clean/` | *"clean my agent cache"* |

```bash
# Codex
mkdir -p ~/.codex/skills/codex-clean
cp SKILL.md ~/.codex/skills/codex-clean/       # or SKILL.zh-CN.md for Chinese
cp -r scripts ~/.codex/skills/codex-clean/

# Claude Code — the directory name becomes the slash command
mkdir -p ~/.claude/skills/codex-clean
cp SKILL.md ~/.claude/skills/codex-clean/      # add `allowed-tools: Bash, Read` to frontmatter
cp -r scripts ~/.claude/skills/codex-clean/

# Pi
mkdir -p ~/.pi/agent/skills/codex-clean
cp SKILL.md ~/.pi/agent/skills/codex-clean/
cp -r scripts ~/.pi/agent/skills/codex-clean/
```

Then just ask — the agent reads the skill, scans, and confirms with you before cleaning.

## Install as a Pi package

The repo is also a Pi package (`package.json` with a `pi` manifest), which gives Pi a native tool + slash command instead of only a skill:

```bash
pi install git:github.com/Merlin-Arthur05/codex-clean
```

This registers:

- **Tools** — `agent_cache_scan`, `agent_cache_clean`, `agent_cache_targets`
- **Command** — `/clean-agents` (scan → confirm → clean)

The extension is a thin wrapper that shells out to the same Python script, so its behaviour is identical across agents. It resolves `python3` / `py -3` / `python` at runtime and never assumes a fixed interpreter path.

## Roadmap / Ideas

- Automatic WAL-growth watchdog suggestion (periodic scan reminder).
- Optional integration as a Windows scheduled task (opt-in only).
- **opencode** ([anomalyco/opencode](https://github.com/anomalyco/opencode)) — its XDG
  data/log/cache directories plus the WAL-mode `opencode.db`. Tracked in [#12](https://github.com/Merlin-Arthur05/codex-clean/issues/12).
- Opt-in age-based cleaning for Claude Code's `projects/` conversation JSONL (explicit flag + per-item confirmation, never on by default).
- Runtime process detection, so a clean warns when the target agent is still running ([#8](https://github.com/Merlin-Arthur05/codex-clean/issues/8)).

All tracked on the [project board](https://github.com/users/Merlin-Arthur05/projects/3).

## Filtering, dry-run & automation

| Flag | What it does |
|---|---|
| `--target all` | sweep every registered agent in one run |
| `--exclude LIST` | skip items by `name` or `agent:name` (comma separated) |
| `--only LIST` | keep only the listed items (inverse of `--exclude`) |
| `--dry-run` | print the plan `--clean` would execute, change nothing |
| `--list-targets` | print supported agents, their homes and capabilities |
| `--check N` | exit **3** when reclaimable space reaches N MB (0 = off) |

Notes:

- Filtering can only **narrow** the whitelist. Protected entries are never part of the
  scanned items, so no pattern can bring one back.
- `--dry-run` reuses the `planned_action` data already present in `--json` scan output,
  so the preview and the real run describe the same actions.
- Exit codes: `0` ok, `2` bad arguments, `3` reclaimable reached the `--check` threshold.

## Tests

```bash
python tests/test_codex_clean.py          # 68 regression checks, standard library only
node   tests/test_pi_extension.mjs        # Pi extension load test (skips if Pi absent)
```

The Python suite points each agent's home env var at throwaway temp directories, so it never
touches real agent data.

## License

[MIT](LICENSE) © Merlin-Arthur05

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) ([简体中文](CONTRIBUTING.zh-CN.md)). PRs welcome — but the safety contract is strict: never add destructive defaults, keep protected items protected, stay stdlib-only.
