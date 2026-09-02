# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2026-09-02

### Added

- Initial open-source release.
- `codex_clean.py` v2 CLI:
  - `--scan` read-only scan (default) with per-item sizes and total reclaimable space.
  - `--clean` interactive per-item confirmation mode.
  - `--clean --yes` non-interactive cleanup of all safe "delete + WAL" items.
  - `--clean --yes --vacuum` additionally runs `PRAGMA wal_checkpoint(TRUNCATE)` + `VACUUM` on Codex's SQLite databases (data preserved, space reclaimed).
  - `--clean --yes --rebuild-logs` optionally backs up and rebuilds an oversized `logs_2.sqlite` (>100 MB).
  - `--json` structured output for tooling.
- Cleanup targets (strict whitelist, all regenerable):
  - `~/.codex/.tmp`, `~/.codex/tmp`, `~/.codex/plugins/cache`
  - VACUUM/WAL on `logs_2.sqlite`, `state_5.sqlite`, `thread_history_1.sqlite`, `queue_1.sqlite`, `goals_1.sqlite`, `memories_1.sqlite`
- Codex Agent Skill packaging (`SKILL.md`) with trigger phrases in Chinese/English.
- README, LICENSE (MIT), CONTRIBUTING, `.gitignore`.
