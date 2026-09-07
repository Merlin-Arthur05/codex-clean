#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Self-contained regression suite for codex_clean.py (stdlib only).

Run:  python tests/test_codex_clean.py
Exit: 0 = all passed, 1 = at least one failure.

The suite never touches a real agent home: every case points CODEX_HOME /
CLAUDE_HOME / PI_AGENT_HOME at a throwaway temp directory.
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


def mkhome(prefix, files):
    d = tempfile.mkdtemp(prefix=prefix)
    _tmpdirs.append(d)
    for rel, size in files:
        if rel.endswith("/"):
            os.makedirs(Path(d) / rel, exist_ok=True)
        else:
            mk(d, rel, size)
    return d


def mkclaude():
    """Fresh fake ~/.claude with both cleanable and protected content."""
    return mkhome("cc_home_", [
        ("cache/x.bin", 50000), ("debug/y.log", 40000),
        ("projects/p.jsonl", 9000), ("memory/m.md", 1000),
        ("skills/s/SKILL.md", 2000), ("settings.json", 100), ("plugins/", 0)])


def mkpi():
    """Fresh fake ~/.pi/agent with cleanable + protected content."""
    return mkhome("pi_home_", [
        ("cache/c.bin", 30000), ("tmp/t.bin", 20000),
        ("npm/pkg/index.js", 8000), ("sessions/s.jsonl", 5000),
        ("skills/s/SKILL.md", 1000), ("settings.json", 100),
        ("trust.json", 100), ("auth.json", 100)])


def main() -> int:
    # ---------------- Codex: backwards compatibility ----------------
    cx = mkhome("cx_home_", [(".tmp/a.bin", 100000), ("tmp/b.bin", 30000),
                             ("plugins/cache/c.bin", 20000),
                             ("sessions/keep.jsonl", 5000), ("config.toml", 100)])
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

    # ---------------- Claude Code ----------------
    cc = mkclaude()
    citems = json.loads(run(["--scan", "--json", "--target", "claude-code", "--lang", "en"],
                            {"CLAUDE_HOME": cc}).stdout)
    cnames = [i["name"] for i in citems]
    check("T7  claude target scans its own home", all(i["agent"] == "claude-code" for i in citems))
    check("T8  claude emits only whitelisted deletes",
          set(cnames) == {"claude-cache", "claude-debug", "claude-shell-snapshots", "claude-statsig"},
          str(sorted(cnames)))
    check("T9  claude has no vacuum item while it has no SQLite",
          not any(i["kind"] == "vacuum" for i in citems))
    check("T10 claude never lists protected dirs",
          not any(n in cnames for n in ("projects", "memory", "skills", "settings.json")))
    check("T11 missing dirs tolerated (exists=false)",
          all(i["exists"] is False for i in citems
              if "snapshots" in i["name"] or "statsig" in i["name"]))
    check("T12 claude reclaimable = cache + debug only",
          sum(i["reclaimable_bytes"] for i in citems if i["exists"]) == 90000)

    r = run(["--scan", "--vacuum", "--target", "claude-code", "--lang", "en"], {"CLAUDE_HOME": cc})
    check("T13 --vacuum on claude reports 'does not apply'", "does not apply" in r.stdout)
    check("T14 --vacuum on claude still exits 0", r.returncode == 0)
    r = run(["--scan", "--rebuild-logs", "--target", "claude-code", "--lang", "en"],
            {"CLAUDE_HOME": cc})
    check("T15 --rebuild-logs on claude reports 'does not apply'", "does not apply" in r.stdout)

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

    # ---------------- Pi ----------------
    pi = mkpi()
    pitems = json.loads(run(["--scan", "--json", "--target", "pi", "--lang", "en"],
                            {"PI_AGENT_HOME": pi}).stdout)
    pnames = [i["name"] for i in pitems]
    check("T23 pi target scans its own home", all(i["agent"] == "pi" for i in pitems))
    check("T24 pi emits only whitelisted deletes",
          set(pnames) == {"pi-cache", "pi-tmp", "pi-logs"}, str(sorted(pnames)))
    check("T25 pi protects npm/ (user-installed packages)",
          "npm" not in pnames and "sessions" not in pnames and "skills" not in pnames)
    check("T26 pi missing logs dir tolerated",
          all(i["exists"] is False for i in pitems if i["name"] == "pi-logs"))
    check("T27 pi reclaimable = cache + tmp only",
          sum(i["reclaimable_bytes"] for i in pitems if i["exists"]) == 50000)
    r = run(["--clean", "--yes", "--target", "pi", "--lang", "en"], {"PI_AGENT_HOME": pi})
    check("T28 pi clean succeeded", r.returncode == 0, r.stderr[:200])
    check("T29 pi cache + tmp deleted",
          not (Path(pi) / "cache").exists() and not (Path(pi) / "tmp").exists())
    check("T30 pi PROTECTED survived (npm/sessions/skills/settings/trust/auth)",
          all((Path(pi) / p).exists() for p in ("npm/pkg/index.js", "sessions/s.jsonl",
                                                "skills/s/SKILL.md", "settings.json",
                                                "trust.json", "auth.json")))

    # ---------------- VACUUM is data-driven, not hardcoded ----------------
    ccdb = mkclaude()
    mk(ccdb, "history.sqlite", 4096)          # simulate a future SQLite file
    ditems = json.loads(run(["--scan", "--json", "--target", "claude-code", "--lang", "en"],
                            {"CLAUDE_HOME": ccdb}).stdout)
    check("T31 discovered SQLite becomes a vacuum item (not hardcoded off)",
          any(i["kind"] == "vacuum" and i["name"] == "history" for i in ditems),
          str([i["name"] for i in ditems]))
    r = run(["--scan", "--vacuum", "--target", "claude-code", "--lang", "en"], {"CLAUDE_HOME": ccdb})
    check("T32 with a DB present, 'does not apply' is gone",
          "does not apply" not in r.stdout, r.stdout[:160])

    # ---------------- --age works for non-Codex agents ----------------
    ccage = mkclaude()
    aged = run(["--scan", "--json", "--age", "7", "--target", "claude-code"],
               {"CLAUDE_HOME": ccage}).stdout
    check("T33 --age applies to claude deletes too", "age_filter_days" in aged)

    # ---------------- CLI / i18n ----------------
    check("T34 invalid --target rejected with exit 2",
          run(["--scan", "--target", "nope"]).returncode == 2)
    r = run(["--help", "--lang", "zh"])
    check("T35 zh --help is localized and lists --target",
          "--target" in r.stdout and "agent" in r.stdout)
    check("T36 --target help lists all three agents",
          all(a in run(["--help", "--lang", "en"]).stdout for a in ("codex", "claude-code", "pi")))

    # ---------------- WAL watchdog hint ----------------
    wx = tempfile.mkdtemp(prefix="wal_home_")
    _tmpdirs.append(wx)
    with open(Path(wx) / "logs_2.sqlite-wal", "wb") as f:
        f.truncate(40 * 1024 * 1024)
    check("T37 WAL hint shown when WAL > 32MB",
          "WAL totals" in run(["--scan", "--lang", "en"], {"CODEX_HOME": wx}).stdout)
    check("T38 no WAL hint for a small WAL",
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
