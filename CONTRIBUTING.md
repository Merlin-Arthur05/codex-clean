# Contributing to codex-clean

[English](CONTRIBUTING.md) | [简体中文](CONTRIBUTING.zh-CN.md)

Thanks for your interest! This is a small, focused tool — here's how to help without stepping on its safety design.

## Ground rules

The whole point of `codex-clean` is **safety**: it only ever touches a strict whitelist of Codex's own regenerable cache/log files, and it never auto-deletes conversation history, state databases, configs, or user project files.

Any contribution must preserve that contract:

- **No new destructive defaults.** If you add a cleanup target, it must be clearly safe to recreate, and it must remain opt-in / confirm-before-run.
- **Keep protected items protected.** `sessions/`, `state_*`, `thread_history_*`, `memories_*`, `goals_*`, `auth.json`, `config.toml`, `bin`, `runtimes` are never touched.
- **Pure stdlib only.** `codex_clean.py` currently has zero third-party dependencies — keep it that way (it's meant to run anywhere Python runs).

## Workflow

1. Fork the repo and create a feature branch.
2. Make your change.
3. Add/adjust tests: use the `CODEX_HOME` env override (the script already honors it) to test against a scratch directory — never against a real `~/.codex`.
4. Run the script's `--scan` against your scratch dir to confirm the change works.
5. Open a pull request describing the change and why it's safe.

## Code style

- Python 3.8+ compatible.
- Keep functions small and documented.
- `--json` output must remain stable — tooling may parse it.

## Testing

```powershell
# Create a throwaway fake CODEX_HOME and test against it
$env:CODEX_HOME = "$env:TEMP\codex-clean-test"
python scripts/codex_clean.py --scan
python scripts/codex_clean.py --clean --yes --vacuum
```

Then delete the scratch dir. Never run `--clean` against your real `~/.codex` while testing.

## Questions

Open an issue first for anything non-trivial so we can align before you spend effort.
