#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Self-contained regression suite for codex_clean.py (stdlib only).

Run:  python tests/test_codex_clean.py
Exit: 0 = all passed, 1 = at least one failure.

The suite never touches a real agent home: every case points CODEX_HOME /
CLAUDE_HOME / PI_AGENT_HOME at a throwaway temp directory.
"""
from __future__ import annotations

import io
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


def _script_version():
    """Read VERSION from the script (single source of truth for releases)."""
    for line in SCRIPT.read_text(encoding="utf-8").splitlines():
        if line.startswith("VERSION"):
            return line.split("=", 1)[1].strip().strip('"')
    return None


def mkclaude():
    """Fresh fake ~/.claude with both cleanable and protected content."""
    return mkhome("cc_home_", [
        ("cache/x.bin", 50000), ("debug/y.log", 40000),
        ("projects/p.jsonl", 9000), ("memory/m.md", 1000),
        ("skills/s/SKILL.md", 2000), ("settings.json", 100), ("plugins/", 0)])


def mkpi():
    """Fresh fake ~/.pi/agent with cleanable + protected content.

    Mirrors the real layout from pi's source: tmp/extensions/<hash> holds
    temporary package checkouts, npm/ holds user-installed packages, and the
    debug log lives at the agent root.
    """
    return mkhome("pi_home_", [
        ("cache/c.bin", 30000), ("tmp/t.bin", 20000),
        ("tmp/extensions/ab12cd34/node_modules/x/index.js", 5000),
        ("pi-debug.log", 3000),
        ("npm/pkg/index.js", 8000), ("sessions/s.jsonl", 5000),
        ("skills/s/SKILL.md", 1000), ("extensions/ext.ts", 900),
        ("settings.json", 100), ("trust.json", 100),
        ("auth.json", 100), ("models.json", 100)])


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
          set(pnames) == {"pi-cache", "pi-tmp", "pi-logs", "pi-debug-log"},
          str(sorted(pnames)))
    check("T25 pi protects npm/ (user-installed packages)",
          "npm" not in pnames and "sessions" not in pnames and "skills" not in pnames)
    check("T26 pi missing logs dir tolerated",
          all(i["exists"] is False for i in pitems if i["name"] == "pi-logs"))
    check("T27 pi reclaimable = cache + tmp (+tmp/extensions) + debug log",
          sum(i["reclaimable_bytes"] for i in pitems if i["exists"]) == 58000)
    r = run(["--clean", "--yes", "--target", "pi", "--lang", "en"], {"PI_AGENT_HOME": pi})
    check("T28 pi clean succeeded", r.returncode == 0, r.stderr[:200])
    check("T29 pi cache + tmp deleted",
          not (Path(pi) / "cache").exists() and not (Path(pi) / "tmp").exists())
    check("T30 pi PROTECTED survived (npm/sessions/skills/extensions/settings/trust/auth/models)",
          all((Path(pi) / p).exists() for p in ("npm/pkg/index.js", "sessions/s.jsonl",
                                                "skills/s/SKILL.md", "extensions/ext.ts",
                                                "settings.json", "trust.json",
                                                "auth.json", "models.json")))

    # ---------------- Pi plugin / package ecosystem ----------------
    pifx = mkhome("pi_plug_", [
        ("tmp/extensions/deadbeef/npm/node_modules/pkg/i.js", 12000),
        ("tmp/t.log", 4000), ("pi-debug.log", 2000),
        ("npm/node_modules/userpkg/index.js", 7000),
        ("git/github.com/u/r/file.ts", 6000),
        ("extensions/my-ext.ts", 5000), ("skills/s/SKILL.md", 3000),
        ("sessions/s.jsonl", 1000), ("settings.json", 100),
        ("trust.json", 100), ("auth.json", 100), ("models.json", 100)])
    plug = json.loads(run(["--scan", "--json", "--target", "pi", "--lang", "en"],
                          {"PI_AGENT_HOME": pifx}).stdout)
    pn = {i["name"]: i for i in plug}
    check("T57 pi cleans its debug log",
          "pi-debug-log" in pn and pn["pi-debug-log"]["exists"])
    check("T58 pi tmp covers nested extension checkouts",
          "pi-tmp" in pn
          and pn["pi-tmp"]["path"].replace("\\", "/").endswith("/tmp")
          and pn["pi-tmp"]["reclaimable_bytes"] == 16000,
          str({k: v["reclaimable_bytes"] for k, v in pn.items()}))
    check("T59 pi reclaimable excludes user packages and clones",
          sum(i["reclaimable_bytes"] for i in plug if i["exists"]) == 18000,
          str(sum(i["reclaimable_bytes"] for i in plug if i["exists"])))
    r = run(["--clean", "--yes", "--target", "pi", "--lang", "en"], {"PI_AGENT_HOME": pifx})
    check("T60 pi plugin cleanup succeeds", r.returncode == 0, r.stderr[:200])
    check("T61 pi tmp/ and debug log removed",
          not (Path(pifx) / "tmp").exists() and not (Path(pifx) / "pi-debug.log").exists())
    check("T62 pi user packages + git clones + extensions + skills survived",
          all((Path(pifx) / p).exists() for p in (
              "npm/node_modules/userpkg/index.js", "git/github.com/u/r/file.ts",
              "extensions/my-ext.ts", "skills/s/SKILL.md", "sessions/s.jsonl",
              "settings.json", "trust.json", "auth.json", "models.json")))

    # ---------------- Pi package manifest (pi install) ----------------
    pkgjson = Path(__file__).resolve().parent.parent / "package.json"
    if pkgjson.exists():
        pk = json.loads(pkgjson.read_text(encoding="utf-8"))
        check("T63 package.json declares a pi manifest", "pi" in pk)
        check("T64 pi manifest points at the extension",
              any("pi-extension" in e for e in pk.get("pi", {}).get("extensions", [])),
              str(pk.get("pi", {}).get("extensions")))
        check("T65 pi manifest exposes the skill directory",
              any("skills" in e for e in pk.get("pi", {}).get("skills", [])),
              str(pk.get("pi", {}).get("skills")))
        check("T66 package version matches script VERSION",
              pk.get("version") == _script_version(),
              f"{pk.get('version')} vs {_script_version()}")
        check("T67 extension entry file exists",
              (Path(__file__).resolve().parent.parent / "pi-extension" / "index.ts").exists())
        check("T68 packaged skill is present",
              (Path(__file__).resolve().parent.parent / "skills" / "codex-clean" / "SKILL.md").exists())

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

    # ---------------- F4: --list-targets ----------------
    tgt = json.loads(run(["--list-targets", "--json"]).stdout)
    check("T39 --list-targets JSON lists every agent",
          {t["name"] for t in tgt} == {"codex", "claude-code", "pi", "opencode"},
          str(sorted(t["name"] for t in tgt)))
    r = run(["--list-targets", "--lang", "en"])
    check("T40 --list-targets text mode prints agents + capabilities",
          "claude-code" in r.stdout and "pi" in r.stdout and "vacuum=" in r.stdout)

    # ---------------- F1: --target all ----------------
    cx2 = mkhome("all_cx_", [(".tmp/a.bin", 10000)])
    cc3 = mkhome("all_cc_", [("cache/c.bin", 20000)])
    pi3 = mkhome("all_pi_", [("cache/p.bin", 30000)])
    oc3 = mkhome("all_oc_", [("opencode/log/l.bin", 40000)])
    allenv = {"CODEX_HOME": cx2, "CLAUDE_HOME": cc3, "PI_AGENT_HOME": pi3,
              "XDG_DATA_HOME": oc3}
    ritems = json.loads(run(["--scan", "--json", "--target", "all"], allenv).stdout)
    ags = {i["agent"] for i in ritems}
    check("T41 --target all covers every agent",
          ags == {"codex", "claude-code", "pi", "opencode"}, str(sorted(ags)))
    r = run(["--scan", "--target", "all", "--lang", "en"], allenv)
    check("T42 --target all prints one section per agent",
          r.stdout.count("directory:") >= 4, r.stdout[:120])
    r = run(["--clean", "--yes", "--target", "all", "--json"], allenv)
    check("T43 --target all clean runs without crashing", r.returncode == 0,
          r.stderr[:150])
    if r.stdout.strip().startswith("{"):
        rep_all = json.loads(r.stdout)
        check("T44 --target all report unions protected lists",
              "sessions" in rep_all.get("protected_untouched", [])
              and "npm" in rep_all.get("protected_untouched", [])
              and "repos" in rep_all.get("protected_untouched", []))
    else:
        check("T44 --target all report unions protected lists", False)

    # ---------------- F2: --exclude / --only ----------------
    fi = json.loads(run(["--scan", "--json", "--target", "all",
                         "--exclude", "pi-cache"], allenv).stdout)
    check("T45 --exclude drops the named item",
          not any(i["agent"] == "pi" and i["name"] == "pi-cache" for i in fi))
    fi = json.loads(run(["--scan", "--json", "--target", "all",
                         "--exclude", "codex"], allenv).stdout)
    check("T46 --exclude can drop a whole agent",
          not any(i["agent"] == "codex" for i in fi))
    fi = json.loads(run(["--scan", "--json", "--target", "all",
                         "--only", "pi-cache"], allenv).stdout)
    check("T47 --only keeps just the matching item",
          [i["name"] for i in fi] == ["pi-cache"], str([i["name"] for i in fi]))
    fi = json.loads(run(["--scan", "--json", "--target", "all",
                         "--exclude", "projects,sessions"], allenv).stdout)
    check("T48 --exclude accepts a comma-separated list",
          not any(i["name"] in ("projects", "sessions") for i in fi))

    # ---------------- F3: --dry-run ----------------
    dr = mkclaude()
    r = run(["--clean", "--yes", "--dry-run", "--target", "claude-code"],
            {"CLAUDE_HOME": dr})
    check("T49 --dry-run exits 0", r.returncode == 0, r.stderr[:150])
    check("T50 --dry-run deletes nothing", (Path(dr) / "cache").exists())
    rep = json.loads(run(["--clean", "--yes", "--dry-run", "--target",
                          "claude-code", "--json"], {"CLAUDE_HOME": dr}).stdout)
    check("T51 --dry-run JSON sets dry_run", rep.get("dry_run") is True)
    check("T52 --dry-run JSON items are 'planned'",
          bool(rep.get("items")) and all(i["status"] == "planned" for i in rep["items"]))
    check("T53 --dry-run protected list still reported",
          "projects" in rep.get("protected_untouched", []))

    # ---------------- F5: --check N ----------------
    chk = mkhome("chk_home_", [(".tmp/a.bin", 2 * 1024 * 1024)])
    r = run(["--scan", "--check", "1"], {"CODEX_HOME": chk})
    check("T54 --check exits 3 when reclaimable >= threshold",
          r.returncode == 3, "rc=%d" % r.returncode)
    r = run(["--scan", "--check", "500"], {"CODEX_HOME": chk})
    check("T55 --check exits 0 when under threshold",
          r.returncode == 0, "rc=%d" % r.returncode)
    r = run(["--scan", "--check", "1", "--json"], {"CODEX_HOME": chk})
    check("T56 --check still emits JSON and exits 3",
          r.returncode == 3 and r.stdout.strip().startswith("["))

    # ---------------- F5: opencode (multi-root agent) ----------------
    oc_data = mkhome("oc_data_", [("opencode/log/l.bin", 40000),
                                  ("opencode/repos/r.txt", 90000)])
    oc_cache = mkhome("oc_cache_", [("opencode/bin/b.bin", 70000)])
    oc_tmp = mkhome("oc_tmp_", [("opencode/t.bin", 30000)])
    ocenv = {"XDG_DATA_HOME": oc_data, "XDG_CACHE_HOME": oc_cache,
             "OPENCODE_TMPDIR": oc_tmp}
    oitems = json.loads(run(["--scan", "--json", "--target", "opencode"], ocenv).stdout)
    _n = lambda p: p.replace("\\", "/")
    opaths = {i["name"]: _n(i["path"]) for i in oitems}
    check("T69 opencode data home = XDG_DATA_HOME + home_sub",
          opaths.get("opencode-log") == _n(oc_data) + "/opencode/log",
          str(opaths.get("opencode-log")))
    check("T70 opencode cache lives under the separate XDG_CACHE_HOME root",
          opaths.get("opencode-cache") == _n(oc_cache) + "/opencode",
          str(opaths.get("opencode-cache")))
    check("T71 opencode tmp lives under the OS temp root, outside the data home",
          opaths.get("opencode-tmp") == _n(oc_tmp) + "/opencode",
          str(opaths.get("opencode-tmp")))
    check("T72 opencode whitelist covers log/cache/tmp",
          {"opencode-log", "opencode-cache", "opencode-tmp"} <= set(opaths),
          str(sorted(opaths)))
    check("T73 opencode never offers user repos for deletion",
          not any("repos" in p for p in opaths.values()), str(sorted(opaths.values())))
    check("T74 opencode is a first-class target for --target all",
          "opencode" in {t["name"] for t in
                         json.loads(run(["--list-targets", "--json"]).stdout)})

    # ---------------- F6: running-process detection ----------------
    sys.path.insert(0, str(SCRIPT.parent))
    try:
        import codex_clean as _cc
    except Exception:
        _cc = None
    if _cc is not None:
        _cc._running_process_names = lambda: {"codex.exe", "pycharm", "opencode"}
        hits = dict(_cc.running_agents(["codex", "claude-code", "pi", "opencode"]))
        check("T75 detects running agents by exact process stem",
              "Codex" in hits and "opencode" in hits, str(hits))
        check("T76 a short name like 'pi' does not match 'pycharm'",
              "Pi" not in hits, str(hits))
        check("T77 absent agents are not reported",
              "Claude Code" not in hits, str(hits))
        _cc._running_process_names = lambda: set()
        check("T78 an unavailable probe reports nothing (never blocks a clean)",
              _cc.running_agents(["codex", "opencode"]) == [], "non-empty")

        # The warning must never pollute JSON stdout -- it breaks json.loads in
        # automation. Drive main() in-process with a faked process list.
        _cc._running_process_names = lambda: {"codex.exe"}
        cxj = mkhome("json_pure_", [(".tmp/a.bin", 12000)])
        _old_home, _old_argv, _old_out, _old_err = (
            os.environ.get("CODEX_HOME"), sys.argv, sys.stdout, sys.stderr)
        _bo, _be = io.StringIO(), io.StringIO()
        try:
            os.environ["CODEX_HOME"] = cxj
            sys.argv = ["codex_clean.py", "--clean", "--yes", "--json", "--lang", "en"]
            sys.stdout, sys.stderr = _bo, _be
            try:
                _cc.main()
            except SystemExit:
                pass
        finally:
            sys.stdout, sys.stderr, sys.argv = _old_out, _old_err, _old_argv
            if _old_home is None:
                os.environ.pop("CODEX_HOME", None)
            else:
                os.environ["CODEX_HOME"] = _old_home
        try:
            json.loads(_bo.getvalue())
            _pure = True
        except Exception:
            _pure = False
        check("T79 JSON stdout stays parseable while the agent is running",
              _pure, _bo.getvalue()[:120])
        check("T80 the running warning is routed to stderr, not stdout",
              "running" in _be.getvalue().lower(), _be.getvalue()[:120])
    else:
        check("T75 import codex_clean for process-detection tests", False)

    for d in _tmpdirs:
        shutil.rmtree(d, ignore_errors=True)

    bad = [n for n, ok_ in results if not ok_]
    print("\n%d/%d passed" % (len(results) - len(bad), len(results)))
    if bad:
        print("FAILED:", bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
