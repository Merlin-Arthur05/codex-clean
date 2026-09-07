#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Self-contained regression suite for codex_clean.py (stdlib only).

Run:  python tests/test_codex_clean.py
Exit: 0 = all passed, 1 = at least one failure.

The suite never touches a real agent home: every case points CODEX_HOME /
CLAUDE_HOME at a throwaway temp directory.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "codex_clean.py"
PY = sys.executable
results: list[tuple[str, bool]] = []
_tmpdirs: list[str] = []


def run(args, home=None):
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    if home:
        env.update(home)
    return subprocess.run([PY, str(SCRIPT), *args], capture_output=True,
                          text=True, encoding="utf-8", env=env)


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("  PASS  " if cond else "  FAIL  ") + name + ("   " + detail if detail and not cond else ""))


def mk(root, rel, size):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "wb") as f:
        f.write(b"x" * size)
    return p


def mkclaude():
    """Fresh fake ~/.claude with both cleanable and protected content."""
    d = tempfile.mkdtemp(prefix="cc_home_")
    _tmpdirs.append(d)
    mk(d, "cache/x.bin", 50000)          # cleanable
    mk(d, "debug/y.log", 40000)          # cleanable
    mk(d, "projects/p.jsonl", 9000)      # protected (conversations)
    mk(d, "memory/m.md", 1000)           # protected
    mk(d, "skills/s/SKILL.md", 2000)     # protected
    mk(d, "settings.json", 100)          # protected
    os.makedirs(Path(d) / "plugins", exist_ok=True)
    return d


def main() -> int:
    # ---------------- Codex: backwards compatibility ----------------
    cx = tempfile.mkdtemp(prefix="cx_home_")
    _tmpdirs.append(cx)
    mk(cx, ".tmp/a.bin", 100000)
    mk(cx, "tmp/b.bin", 30000)
    mk(cx, "plugins/cache/c.bin", 20000)
    mk(cx, "sessions/keep.jsonl", 5000)
    mk(cx, "config.toml", 100)

    items = json.loads(run(["--scan", "--json", "--lang", "en"], {"CODEX_HOME": cx}).stdout)
    names = [i["name"] for i in items]
    check("T1  codex is still the default target", all(i["agent"] == "codex" for i in items))
    check("T2  codex item names unchanged",
          set(names) >= {"tmp", "tmp2", "plugin-cache", "logs-db", "state-db"}, str(sorted(names)))
    check("T3  codex keeps SQLite vacuum items", any(i["kind"] == "vacuum" for i in items))
    check("T4  codex protected entries are not cleanable", "sessions" not in names)
    check("T5  codex reclaimable total is accurate",
          sum(i["reclaimable_bytes"] for i in items if i["exists"]) == 150000)
    check("T6  codex --age still works",
          run(["--scan", "--json", "--age", "7"], {"CODEX_HOME": cx}).returncode == 0)

    # ---------------- Claude Code: new target ----------------
    cc = mkclaude()
    citems = json.loads(run(["--scan", "--json", "--target", "claude-code", "--lang", "en"],
                            {"CLAUDE_HOME": cc}).stdout)
    cnames = [i["name"] for i in citems]
    check("T7  claude target scans its own home", all(i["agent"] == "claude-code" for i in citems))
    check("T8  claude emits only whitelisted deletes",
          set(cnames) == {"claude-cache", "claude-debug", "claude-shell-snapshots", "claude-statsig"},
          str(sorted(cnames)))
    check("T9  claude produces NO vacuum items (no SQLite)",
          not any(i["kind"] == "vacuum" for i in citems))
    check("T10 claude never lists protected dirs",
          not any(n in cnames for n in ("projects", "memory", "skills", "settings.json")))
    check("T11 missing dirs are tolerated (exists=false)",
          all(i["exists"] is False for i in citems
              if "snapshots" in i["name"] or "statsig" in i["name"]))
    check("T12 claude reclaimable = cache + debug only",
          sum(i["reclaimable_bytes"] for i in citems if i["exists"]) == 90000)

    # ---------------- capability degradation ----------------
    r = run(["--scan", "--vacuum", "--target", "claude-code", "--lang", "en"], {"CLAUDE_HOME": cc})
    check("T13 --vacuum on claude prints a capability note", "does not apply" in r.stdout)
    check("T14 --vacuum on claude still exits 0", r.returncode == 0)
    r = run(["--scan", "--rebuild-logs", "--target", "claude-code", "--lang", "en"],
            {"CLAUDE_HOME": cc})
    check("T15 --rebuild-logs on claude prints a note", "does not apply" in r.stdout)

    # ---------------- cleaning respects the whitelist ----------------
    r = run(["--clean", "--yes", "--target", "claude-code", "--lang", "en"], {"CLAUDE_HOME": cc})
    check("T16 claude clean succeeded", r.returncode == 0, r.stderr[:200])
    check("T17 claude cache deleted", not (Path(cc) / "cache").exists())
    check("T18 claude debug deleted", not (Path(cc) / "debug").exists())
    check("T19 claude PROTECTED entries survived",
          all((Path(cc) / p).exists() for p in ("projects/p.jsonl", "memory/m.md",
                                                "skills/s/SKILL.md", "settings.json")))

    cc2 = mkclaude()
    r = run(["--clean", "--yes", "--target", "claude-code", "--json"], {"CLAUDE_HOME": cc2})
    ok = r.stdout.strip().startswith("{")
    check("T20 claude clean emits JSON", ok, r.stdout[:120])
    if ok:
        rep = json.loads(r.stdout)
        check("T21 clean JSON carries agent", rep.get("agent") == "claude-code")
        check("T22 clean JSON protected list is the claude one",
              "projects" in rep.get("protected_untouched", [])
              and "config.toml" not in rep.get("protected_untouched", []))
    else:
        check("T21 clean JSON carries agent", False)
        check("T22 clean JSON protected list is the claude one", False)

    # ---------------- CLI / i18n ----------------
    check("T23 invalid --target rejected with exit 2",
          run(["--scan", "--target", "nope"]).returncode == 2)
    r = run(["--help", "--lang", "zh"])
    check("T24 zh --help is localized and lists --target",
          "--target" in r.stdout and "agent" in r.stdout)
    cc3 = mkclaude()
    r = run(["--scan", "--target", "claude-code", "--lang", "zh"], {"CLAUDE_HOME": cc3})
    check("T25 zh claude scan renders without crashing",
          r.returncode == 0 and "Claude Code" in r.stdout)
    r = run(["--scan", "--target", "claude-code", "--lang", "en"], {"CLAUDE_HOME": cc3})
    check("T26 en claude scan shows the agent label", "Claude Code directory" in r.stdout)

    # ---------------- WAL watchdog hint ----------------
    wx = tempfile.mkdtemp(prefix="wal_home_")
    _tmpdirs.append(wx)
    with open(Path(wx) / "logs_2.sqlite-wal", "wb") as f:
        f.truncate(40 * 1024 * 1024)
    check("T27 WAL hint shown when WAL > 32MB",
          "WAL totals" in run(["--scan", "--lang", "en"], {"CODEX_HOME": wx}).stdout)
    check("T28 no WAL hint for a small WAL",
          "WAL totals" not in run(["--scan", "--lang", "en"], {"CODEX_HOME": cx}).stdout)

    for d in _tmpdirs:
        shutil.rmtree(d, ignore_errors=True)

    bad = [n for n, ok_ in results if not ok_]
    print("\n%d/%d passed" % (len(results) - len(bad), len(results)))
    if bad:
        print("FAILED:", bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
