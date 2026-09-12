# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.6.0] - 2026-09-12

### Added
- **Pi package / extension (#10)**: the repo is now installable as a Pi package
  (`package.json` with a `pi` manifest). It registers three tools — `agent_cache_scan`,
  `agent_cache_clean`, `agent_cache_targets` — and the `/clean-agents` command (scan ->
  confirm -> clean). The extension is a thin wrapper over the same Python script, so
  behaviour is identical in every agent, and it probes `python3` / `py -3` / `python` at
  runtime instead of assuming a fixed interpreter path.
- **Portable agent resolution**: every agent home is resolved from its environment
  variable (`CODEX_HOME` / `CLAUDE_HOME` / `PI_AGENT_HOME`) with a fallback to the default
  path, so nothing is tied to a specific machine. Pi's real layout was verified against
  the source (`src/config.ts`, `src/core/package-manager.ts`), which corrected the earlier
  `pi-plugin-cache` entry — Pi's `tmp/extensions/<hash>/` checkouts are now counted and
  `npm/`, `git/`, `extensions/`, `bin/`, `tools/` are explicitly protected.
- **`tests/test_pi_extension.mjs`**: loads `pi-extension/index.ts` through Pi's own
  `discoverAndLoadExtensions`, asserting the registered tools, their schemas and the
  confirmation gate. Skips cleanly (exit 0) when Pi is not installed.

### Changed
- READMEs condensed and unified: one feature/whitelist/protection table covering all
  three agents, one install section per channel (skill / Pi package), and a trimmed
  roadmap. Fixed malformed "Supported agents" table rows and removed claims that no
  longer matched reality (Pi's stale "planned v1.4.0" row).
- Test suite 56 -> **68** checks.

### Compatibility
Backward compatible with v1.5.0: no flag changed meaning, and the default target is still
Codex.

## [1.5.0] - 2026-09-09

### Added
- **`--target all`**: sweep every registered agent in one run. Item identity changed
  from `name` to `(agent, name)` internally so identically named items of different
  agents can never be confused during confirmation or execution.
- **`--exclude LIST` / `--only LIST` (#6)**: filter items by `name`, `agent:name`, or a
  whole agent; comma separated. Filtering can only narrow the whitelist.
- **`--dry-run`**: print the plan `--clean` would execute (reusing the existing
  `planned_action` data) without touching anything. JSON mode reports `dry_run: true`
  and per-item `status: "planned"`.
- **`--list-targets`**: print supported agents with their resolved home, capabilities and
  whitelists; `--json` for machine consumption.
- **`--check N`**: exit code **3** when reclaimable space reaches N MB (0 = off), so
  scheduled jobs and CI can react without parsing output.

### Changed
- Scan output groups items per agent (one section per agent when several are selected).
- Clean JSON report adds `targets`, `agent_homes`, and a per-item `agent` field;
  `protected_untouched` is the union of the selected agents' protected entries.

### Compatibility
Backward compatible with v1.4.0: every flag keeps its meaning, single-target behaviour is
byte-identical, all pre-existing JSON keys are retained and the new ones are additive.


## [1.4.0] - 2026-09-07

### Added
- **Pi support (#10)**: `--target pi` cleans `~/.pi/agent` (override `PI_AGENT_HOME`).
  Whitelist: `cache/`, `tmp/`, `logs/` (best-effort, only if present). Protects
  `sessions/`, `skills/`, `npm/` (user-installed packages), `settings.json`,
  `trust.json`, `auth.json`, `AGENTS.md`, `SYSTEM.md`. Paths verified against the
  official docs of `earendil-works/pi`.
- **SQLite auto-discovery**: agents without a fixed DB list (Claude Code, Pi) now have
  `*.sqlite` / `*.sqlite3` / `*.db` discovered at runtime, so `--vacuum` is driven by
  data instead of a hardcoded "unsupported" flag.

### Fixed
- `--vacuum` on an agent whose home contains no SQLite now reports "does not apply" based
  on what was actually found, rather than a static per-agent capability.

### Documented
- Known limitations for Claude Code and Pi (`--rebuild-logs` not applicable; `--vacuum`
  depends on discovered databases; Pi's cleanable set is best-effort) — recorded both in
  the README and in a LIMITATIONS comment block next to the `AGENTS` registry.

### Compatibility
Backward compatible with v1.3.0: default target is still `codex`, all flags and JSON keys
unchanged, and Codex keeps its explicit six-database list (no behaviour change).


## [1.3.0] - 2026-09-07

### Added

- **Bilingual docs**: `SKILL` and `CONTRIBUTING` now ship in two languages
  (`SKILL.md` / `SKILL.zh-CN.md`, `CONTRIBUTING.md` / `CONTRIBUTING.zh-CN.md`),
  matching the existing `README.md` / `README.zh-CN.md` split. Convention: the
  un-suffixed file is English, `.zh-CN.md` is Chinese, and each links to the other.
- **opencode support scheduled**: new issues #12 (opencode cleanup targets, with
  every path verified against the `anomalyco/opencode` source) and #11 (refactor
  cleanup targets into a per-agent registry), both under Milestone v1.3.0.
- **Claude Code support scheduled**: new issues #13 (`~/.claude` cleanup target) and #14 (ship as a `/codex-clean` Claude Code skill / slash command), both under Milestone v1.3.0. Verified against a live `~/.claude` install: data is JSONL rather than SQLite, so VACUUM and log-DB rebuild do not apply - these become per-agent capability flags, not hardcoded branches. Planning only; no code or version change in this entry.
- The project board now carries a bilingual README documenting the versioning
  rules, the milestones, and the safety contract.
- **Multi-agent target registry (#11)**: cleanup targets are now declared as data in a
  single `AGENTS` registry instead of module-level constants. Adding an agent is one entry;
  there is no agent-specific branching in the scan/clean flow.
- **Claude Code support (#13)**: `--target claude-code` cleans `~/.claude`
  (override with `CLAUDE_HOME`). Whitelist: `cache/`, `debug/`, `shell-snapshots/`,
  `statsig/`. Protects `projects/` (conversations), `memory/`, `plugins/`, `skills/`,
  `settings.json`, `config.json`, `sessions/`, `ide/`, `history.jsonl`.
- **Claude Code skill install docs (#14)**: `~/.claude/skills/codex-clean/SKILL.md` exposes
  a `/codex-clean` slash command (Agent Skills open standard, shared SKILL.md body).
- **WAL watchdog hint (#4)**: scan prints a hint when WAL files total more than 32 MB.

### Changed

- Scan title and directory line are now agent-aware (`Codex ...` / `Claude Code ...`).
- Item name column widened to 24 chars so longer agent-specific names stay aligned.
- JSON output gains `agent` and `agent_home`; `codex_home` and every pre-existing key are
  kept, so v1.2.x consumers keep working.

- Code comments and docstrings condensed and kept uniformly English: module
  docstring 25 -> 11 lines, multi-line function docstrings collapsed to one line
  where possible, ASCII banner separators replaced with short section markers.
  Comments-only change (627 -> 606 lines), verified by the full self-test suite.
- Repository description is now bilingual; added topics (codex, cleanup, cache,
  sqlite, vacuum, disk-space, cli, python, developer-tools).

> No version bump: documentation, comments and issue planning only.
> The script's `VERSION` remains `1.2.1`.

### Fixed

- **Scan listing numbers now add up.** The size column showed each database's
  total size (main + WAL + SHM) while the "Estimated reclaimable" footer summed
  only the reclaimable amounts (the WAL, for VACUUM items). On a real
  `~/.codex` the listed column added up to 129.5 MB against a 107.3 MB footer —
  a 22.2 MB overstatement. The column now shows the reclaimable amount and
  annotates the database total in parentheses, e.g.
  `logs-db  13.4 MB  (DB total 34.0 MB)`. The JSON contract is unchanged:
  `size_bytes` still reports the total and `reclaimable_bytes` the reclaimable
  amount.
- Restored the Chinese `SKILL.md` in the local skill install, which the previous
  commit had overwritten with the new English canonical. The repo keeps English
  as canonical; the local install matches the user's Chinese Codex client.

## [1.2.1] - 2026-09-04

### Fixed

- **Accurate "reclaimable" total**: the scan's "Estimated reclaimable" figure previously
  summed the full SQLite database file sizes (main + WAL + SHM), which overstated what
  cleanup can actually free - VACUUM only reclaims the WAL and internal free pages, not the
  live data. Each item now reports a `reclaimable_bytes` amount (delete = deletable size;
  vacuum = WAL size; rebuild = log DB size) and the total is summed from these, so the
  number reflects reality.
- **`--clean` estimate consistency**: the clean-mode `estimated` figure now uses the same
  `reclaimable_bytes` basis as the scan, so "estimated vs actual" is apples-to-apples.

### Changed

- Scan output and the `--json` item list are now sorted by `reclaimable_bytes`
  (largest first) for easier triage.
- Removed a redundant directory walk in the scan (size + age are now computed in a single
  pass), slightly reducing scan time on large cache trees.

## [1.2.0] - 2026-09-04

### Added

- **`--age N` filter**: delete items now optionally target only files older than
  N days; newer files are kept. Scan reports `eligible_bytes` / `eligible_files`
  vs `total_bytes` / `total_files`; clean removes only aged files and prunes
  directories left empty. Applies to delete items only.
- **`--json` dry-run preview**: every scan item now carries a structured
  `planned_action` object (`type`, `target`, `reclaimable_bytes`, `reversible`,
  `confirm_required`, `age_filter_days`), plus `safe` and age eligibility fields,
  so callers can preview what cleaning would do before asking the user.
- **`--json` estimated vs actual**: `--clean --yes --json` returns a report with
  `estimated_bytes`, `actual_freed_bytes`, `delta_bytes`, a per-item
  `status`/`estimated_bytes`/`actual_bytes`, and a `protected_untouched` list.
- **README.zh-CN.md**: full Chinese translation, including a comparison section
  against generic computer-cleanup skills.
- README: `--age` and `--json` documentation, "Not a generic computer cleaner"
  positioning section, link to the Chinese README.

### Changed

- VACUUM now reports the **measured** reclaimed bytes (main DB + WAL + SHM before
  vs after) instead of assuming the WAL size, making the estimated-vs-actual
  delta meaningful.
- Script version constant is now the single source of truth (`VERSION = "1.2.0"`),
  kept in sync with the release tag; `prog.desc` renders it via an i18n template.

### Fixed

- `--lang` now affects the `--help` screen and per-argument help text. Previously
  argparse built its help before the language was resolved, so `--help` was
  always English. Language is now pre-scanned from `sys.argv` /
  `CODEX_CLEAN_LANG` before the parser is constructed.

## [1.1.0] - 2026-09-02

### Added

- i18n: user-facing output (scan list, confirm prompts, results) now supports
  English and Chinese. Language resolution: `--lang en|zh|auto` →
  `CODEX_CLEAN_LANG` env → `LANG`/`LC_ALL` → OS UI language → English.
- README: document `--lang` / `CODEX_CLEAN_LANG` usage.
- Roadmap: plan multi-agent support starting with `pi`
  (`@earendil-works/pi-coding-agent`).

### Changed

- SKILL.md description: clearly differentiate from generic computer-cleanup skills
  (e.g. `qing-li-dian-nao`) — codex-clean only targets Codex's own runtime data,
  adds a dedicated comparison section, and highlights unique capabilities
  (SQLite VACUUM/WAL, oversized log rebuild, i18n output, stdlib-only).

## [1.0.0] - 2026-09-02

### Added

- Initial open-source release.
- `codex_clean.py` CLI:
  - `--scan` read-only scan (default) with per-item sizes and total reclaimable space.
  - `--clean` interactive per-item confirmation mode.
  - `--clean --yes` non-interactive cleanup of all safe "delete + WAL" items.
  - `--clean --yes --vacuum` additionally runs `PRAGMA wal_checkpoint(TRUNCATE)` +
    `VACUUM` on Codex's SQLite databases (data preserved, space reclaimed).
  - `--clean --yes --rebuild-logs` optionally backs up and rebuilds an oversized
    `logs_2.sqlite` (>100 MB).
  - `--json` structured output for tooling.
- Cleanup targets (strict whitelist, all regenerable):
  - `~/.codex/.tmp`, `~/.codex/tmp`, `~/.codex/plugins/cache`
  - VACUUM/WAL on `logs_2.sqlite`, `state_5.sqlite`, `thread_history_1.sqlite`,
    `queue_1.sqlite`, `goals_1.sqlite`, `memories_1.sqlite`
- Codex Agent Skill packaging (`SKILL.md`) with trigger phrases in Chinese/English.
- README, LICENSE (MIT), CONTRIBUTING, `.gitignore`.
