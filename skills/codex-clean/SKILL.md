---
name: codex-clean
allowed-tools: Bash, Read
description: "Runtime cache/log cleaner for AI coding agents — targets ONLY regenerable data produced by the agents themselves (~/.codex, ~/.claude, ~/.pi/agent). Completely different from generic PC cleaners (qing-li-dian-nao): it never scans your disk, organizes files, or touches project directories. Use when: an AI coding agent's disk usage ballooned, its logs/temp files piled up, logs_2.sqlite and its WAL are huge, or it is driving heavy SSD writes. Triggers: 清理Codex缓存, Codex日志太多, Codex占空间, codex cache clean, codex log clean, codex SSD占用, clean up codex, 清理Claude缓存, 清理Pi缓存. Unique capabilities: (1) SQLite VACUUM + WAL checkpoint(TRUNCATE) on Codex databases — a Codex-specific remedy for log-DB/WAL bloat that generic cleaners lack; (2) logs_2.sqlite (diagnostics only, not conversations) can be backed up and rebuilt when over 100MB; (3) bilingual en/zh output that follows the client language (--lang / CODEX_CLEAN_LANG); (4) pure stdlib, zero dependencies; (5) --age N removes only temp files older than N days, preserving recent files so in-use caches are not deleted; (6) --json emits a per-item planned_action preview plus an estimated-vs-actual freed-bytes report; (7) one --target flag selects codex, claude-code, pi, or all. Safety boundary: deletes only rebuildable caches, VACUUMs databases without deleting rows, and never touches conversation history (sessions/), state/memory/goals DB contents, auth.json/config.toml/settings.json, bin/runtimes executables, installed packages, or user projects. Defaults to a read-only scan and confirms each item before cleaning."
---

# Agent Cache & Log Cleaner

[English](SKILL.md) | [简体中文](SKILL.zh-CN.md)

Frees disk space by removing or shrinking the regenerable caches, logs, and WAL
files that AI coding agents create for themselves:

| Agent | Home | Select with |
|---|---|---|
| **Codex** (default) | `~/.codex` (`CODEX_HOME`) | default, or `--target codex` |
| **Claude Code** | `~/.claude` (`CLAUDE_HOME`) | `--target claude-code` |
| **Pi** | `~/.pi/agent` (`PI_AGENT_HOME`) | `--target pi` |
| all of the above | — | `--target all` |

Codex is the primary target and has the deepest support (SQLite VACUUM, log-DB
rebuild). Every agent gets the same scan -> confirm -> clean flow and the same
protected-list safety contract.

## How this differs from generic PC cleaners

| Dimension | codex-clean | Generic cleaner (qing-li-dian-nao, etc.) |
|---|---|---|
| Target | **Only the agents' own** runtime data under their home directories | Whole machine: C: drive, downloads/desktop/docs, large & duplicate files |
| Never touches | Your files, project dirs, installed agent packages | Agent session/log DB internals are usually not even in scope |
| Unique capability | **SQLite VACUUM + WAL checkpoint(TRUNCATE)** for `logs_2.sqlite`/WAL bloat; oversized log-DB rebuild | Generic disk scanning, Docker/WSL/browser caches |
| Output | Bilingual (en/zh), follows client language (`--lang` / `CODEX_CLEAN_LANG`) | Usually single-language |
| When to trigger | Only when the user explicitly mentions an agent's cache/logs/disk usage — **do not** fire on "clean my PC / free C: drive / organize files" | When the user says "clean my computer / organize files / find large files" |

> In one line: **codex-clean is self-cleaning for coding agents, not a PC butler.**
> If the user wants their computer or disk cleaned, hand off to a generic
> cleaner instead of using this skill.

## Core contract

- **Only the named agents.** Never cleans the user's personal files or other tools.
- **Scan first, clean second.** The default scan lists every candidate with its
  size; nothing runs until each item is confirmed.
- **Never deleted / never touched** (protected list):
  - Agent executables & runtimes: `%LOCALAPPDATA%\OpenAI\Codex\bin`, `runtimes`
  - Conversation history: `~/.codex/sessions`, `~/.claude/projects`,
    `~/.pi/agent/sessions`
  - State / memory / goals: `state_5.sqlite`, `thread_history_1.sqlite`,
    `memories_1.sqlite`, `goals_1.sqlite`, `queue_1.sqlite`
    (these are **VACUUM/WAL-only — their rows are never deleted**)
  - Config & credentials: `config.toml`, `auth.json`, `settings.json`,
    `trust.json`, `models.json`, `model-catalogs`, `backups`
  - Installed content: `skills/`, `plugins/`, `extensions/`,
    `~/.pi/agent/npm` (**user-installed packages**), `~/.pi/agent/git`
  - Any of the user's project working directories

## Cleanable items

**A. Plain deletes (regenerable — the agent recreates them on demand)**

| Item | Path | Notes |
|---|---|---|
| `tmp` | `~/.codex/.tmp` | Plugin/marketplace download & extraction cache |
| `tmp2` | `~/.codex/tmp` | Codex temp directory |
| `plugin-cache` | `~/.codex/plugins/cache` | Plugin cache, re-downloadable |
| `claude-cache` | `~/.claude/cache` | Claude Code regenerable cache |
| `claude-debug` | `~/.claude/debug` | Claude Code debug logs |
| `claude-shell-snapshots` | `~/.claude/shell-snapshots` | Shell snapshots |
| `claude-statsig` | `~/.claude/statsig` | Telemetry cache |
| `pi-tmp` | `~/.pi/agent/tmp` | Pi temp dir (includes `tmp/extensions/<hash>` package checkouts) |
| `pi-debug-log` | `~/.pi/agent/pi-debug.log` | Pi debug log |
| `pi-cache`, `pi-logs` | `~/.pi/agent/{cache,logs}` | Best-effort: only if they exist |

**B. Database VACUUM + WAL cleanup (data kept, space reclaimed)**
Codex: runs `PRAGMA wal_checkpoint(TRUNCATE)` + `VACUUM` on
`logs_2.sqlite` (logs), `state_5.sqlite`, `thread_history_1.sqlite`,
`queue_1.sqlite`, `goals_1.sqlite`, `memories_1.sqlite`.
Claude Code and Pi declare no fixed DB list: their homes are searched for
`*.sqlite` / `*.sqlite3` / `*.db` at scan time, so VACUUM applies automatically
if such a database ever appears.

> `logs_2.sqlite` holds diagnostics only — not conversation history (that lives
> in state/sessions). If it grows abnormally (>100 MB), you may additionally
> choose "back up then rebuild empty" to reclaim everything; Codex recreates it
> on next start. `state`/`threads`/`goals`/`memories` are **never deleted**,
> only vacuumed.

## Running the script

Execute `scripts/codex_clean.py` from the skill directory with any available Python:

```powershell
python "<skill>\scripts\codex_clean.py" --scan
```

- `--scan` — read-only scan (safe, default)
- `--clean` — interactive per-item confirmation
- `--clean --yes` — skip interaction, clean all "delete + WAL" safe items
- `--clean --yes --vacuum` — additionally VACUUM the databases (recommended full clean)
- `--clean --yes --rebuild-logs` — additionally allow rebuilding an oversized log DB (>100 MB, backs up first; Codex only)
- `--target codex|claude-code|pi|all` — which agent's data to clean (default `codex`)
- `--age N` — only handle temp files **older than N days**, keeping newer ones (delete items only; preview with `--scan --age 7`)
- `--exclude LIST` / `--only LIST` — skip or keep items by `name` or `agent:name`
- `--dry-run` — print what `--clean` would do, change nothing
- `--list-targets` — show supported agents, homes and capabilities
- `--check N` — exit code **3** once reclaimable space reaches N MB (automation)
- `--json` — structured output. Scan mode adds a per-item `planned_action`; clean mode (`--clean --yes --json`) reports `estimated_bytes` / `actual_freed_bytes` / `delta_bytes` plus the `protected_untouched` list
- `--lang en|zh|auto` — output language (defaults to client language auto-detection)

## Execution rules

1. Run `--scan` first and present the results as a list (size + kind
   delete/vacuum/rebuild per item). Use `--target all` when the user wants to
   sweep every installed agent.
   - If the user wants only accumulated old junk while keeping recent caches,
     preview with `--scan --age N` (e.g. N=7).
2. Clean only after per-item confirmation.
   - Plain deletes (tmp / plugin-cache) may proceed once confirmed.
   - VACUUM items: explain "keeps data, only shrinks" — generally recommended.
   - Log-DB rebuild: explicitly state "the original DB is backed up" and get
     separate confirmation.
3. After running, re-scan and report freed space, failures, and residual risk.
4. If the user asks to clear **conversation history / state data**, state clearly
   that this is not cache cleaning and would lose sessions. Only consider it with
   separate, explicit, per-item confirmation — it is never part of automated cleanup.
