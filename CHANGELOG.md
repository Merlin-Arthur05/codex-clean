# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Nothing yet.

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
