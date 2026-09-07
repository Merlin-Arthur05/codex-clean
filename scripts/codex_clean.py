#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Clean regenerable cache/log/WAL files of AI coding agents (whitelist, confirm before clean).

Agents live in the AGENTS registry: codex (default) and claude-code. Per-agent
differences (home path, data format, optional capabilities such as VACUUM) are
data, not branches. Protected data (conversations, config, projects) is never touched.

Usage: codex_clean.py [--scan | --clean] [--age N] [--vacuum] [--rebuild-logs]
                      [--target codex|claude-code|pi] [--json] [--lang en|zh|auto] [--yes]
Lang order: --lang > CODEX_CLEAN_LANG > LANG/LC_ALL > OS UI lang > en.
Exit codes: 0 ok, 2 bad args.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
import time
from pathlib import Path

# Single source of truth: keep in sync with the GitHub Release tag (v1.4.0).
VERSION = "1.4.0"

# Per-agent registry. Adding an agent = one entry here; nothing else branches on
# the agent. Paths are relative to the agent home and resolved at scan time.
#   deletable   -> (item name, relative path, i18n description key)
#   dbs         -> (item name, relative path, i18n key); empty = no SQLite at all
#   capabilities-> optional features that do not apply to every agent
# ---------------------------------------------------------------------------
# Known per-agent LIMITATIONS (verified, not oversights -- see README):
#
#   --rebuild-logs  (claude-code, pi)
#       Neither agent has an "oversized diagnostic log DB". Their logs are plain
#       files (claude: debug/, pi: logs/) already covered by the delete whitelist,
#       so there is no database to rebuild. The flag reports "does not apply".
#
#   --vacuum  (claude-code, pi)
#       Not hardcoded as unsupported: these agents declare no fixed DB list and set
#       discover_dbs=True, so scan() picks up any *.sqlite / *.sqlite3 / *.db found
#       in their home. Verified today: 0 such files under ~/.claude, so --vacuum
#       reports "does not apply" because there is nothing to shrink. If a future
#       release ships a database, VACUUM starts working with no code change.
# ---------------------------------------------------------------------------
AGENTS = {
    "codex": {
        "label": "Codex",
        "home_env": "CODEX_HOME",
        "home_rel": ".codex",
        "deletable": [
            ("tmp", ".tmp", "desc.tmp"),
            ("tmp2", "tmp", "desc.tmp2"),
            ("plugin-cache", "plugins/cache", "desc.plugin-cache"),
        ],
        "dbs": [
            ("logs-db", "logs_2.sqlite", "desc.logs-db"),
            ("state-db", "state_5.sqlite", "desc.state-db"),
            ("threads-db", "thread_history_1.sqlite", "desc.threads-db"),
            ("queue-db", "queue_1.sqlite", "desc.queue-db"),
            ("goals-db", "goals_1.sqlite", "desc.goals-db"),
            ("memories-db", "memories_1.sqlite", "desc.memories-db"),
        ],
        "protected": [
            "sessions", "config.toml", "auth.json", "backups", "backups_state",
            "cc-switch-model-catalog.json", "rules", "skills",
        ],
        "rebuild_db": "logs-db",
        "discover_dbs": False,
        "capabilities": {"vacuum": True, "rebuild_logs": True},
    },
    "claude-code": {
        "label": "Claude Code",
        "home_env": "CLAUDE_HOME",
        "home_rel": ".claude",
        # Conversations are JSONL; no fixed DB list -> databases are discovered
        # at runtime (see the LIMITATIONS block above).
        "deletable": [
            ("claude-cache", "cache", "desc.claude-cache"),
            ("claude-debug", "debug", "desc.claude-debug"),
            ("claude-shell-snapshots", "shell-snapshots", "desc.claude-snapshots"),
            ("claude-statsig", "statsig", "desc.claude-statsig"),
        ],
        "dbs": [],
        "protected": [
            "projects", "memory", "plugins", "skills", "settings.json", "config.json",
            "backups", "sessions", "ide", "history.jsonl",
        ],
        "rebuild_db": None,
        "discover_dbs": True,
        "capabilities": {"vacuum": True, "rebuild_logs": False},
    },
    "pi": {
        "label": "Pi",
        "home_env": "PI_AGENT_HOME",
        "home_rel": ".pi/agent",
        # Verified against the official docs (earendil-works/pi,
        # packages/coding-agent/docs/settings.md): ~/.pi/agent holds sessions/,
        # skills/, npm/ (user-installed packages), settings.json, trust.json,
        # auth.json, AGENTS.md, SYSTEM.md -- all user data, all protected.
        # No regenerable cache is documented; cache/ tmp/ logs/ are offered
        # best-effort and only if present (missing dirs are simply reported as
        # "does not exist", never created or assumed).
        "deletable": [
            ("pi-cache", "cache", "desc.pi-cache"),
            ("pi-tmp", "tmp", "desc.pi-tmp"),
            ("pi-logs", "logs", "desc.pi-logs"),
        ],
        "dbs": [],
        "protected": [
            "sessions", "skills", "npm", "settings.json", "trust.json",
            "auth.json", "AGENTS.md", "SYSTEM.md",
        ],
        "rebuild_db": None,
        "discover_dbs": True,
        "capabilities": {"vacuum": True, "rebuild_logs": False},
    },
}



def agent_home(target: str) -> Path:
    """Resolve an agent's data directory (env override wins, mirroring CODEX_HOME)."""
    spec = AGENTS[target]
    return Path(os.environ.get(spec["home_env"]) or (Path.home() / spec["home_rel"]))

# i18n
_MSGS = {
    "en": {
        "prog.desc": "Codex cache/log cleaner v{v}",
        "scan.title": "=== {label} cleanable items (read-only scan) ===",
        "scan.codedir": "{label} directory: {path}",
        "scan.agefilter": "Age filter: only files older than {days} days are counted",
        "scan.reclaim": "Estimated reclaimable: {size}",
        "scan.of_total": "  (DB total {size})",
        "scan.hint": "\nRun --clean to confirm item-by-item; --clean --yes to clean all safe items;",
        "scan.hint2": "add --vacuum to allow DB VACUUM; add --rebuild-logs to rebuild oversized log DB.",
        "desc.tmp": "Temp download/extract cache (plugins/marketplaces)",
        "desc.tmp2": "Codex temp directory",
        "desc.plugin-cache": "Plugin cache (re-downloadable)",
        "desc.logs-db": "Runtime log DB",
        "desc.state-db": "Session state DB (VACUUM/WAL only, data kept)",
        "desc.threads-db": "Thread history DB (VACUUM/WAL only)",
        "desc.queue-db": "Queue DB (VACUUM/WAL only)",
        "desc.goals-db": "Goals DB (VACUUM/WAL only)",
        "desc.memories-db": "Memories DB (VACUUM/WAL only)",
        "desc.logs-rebuild": "Log DB exceeds {mb}MB; rebuild recommended (backup then recreate; VACUUM keeps diagnostics)",
        "action.delete": "Delete {size}",
        "action.delete_aged": "Delete files older than {days}d ({size})",
        "action.vacuum": "VACUUM shrink + WAL cleanup (est. reclaim)",
        "action.rebuild": "Back up and rebuild log DB (reclaim {size})",
        "clean.none": "No cleanable safe items found (pure deletes gone? or add --vacuum/--rebuild-logs).",
        "confirm.autoyes": "Auto-confirmed via --yes for:",
        "confirm.title": "=== Items to confirm ===",
        "confirm.prompt": "\nEnter numbers to clean (comma separated), all=everything, or empty=cancel:",
        "confirm.invalid": "Invalid input, cancelled.",
        "confirm.cancelled": "Cancelled.",
        "confirm.none": "No items selected.",
        "clean.title": "\n=== Running cleanup ===",
        "clean.estimated": "Estimated: {size}",
        "clean.actual": "Actually freed: {size}",
        "clean.delta": "Delta vs estimate: {delta}",
        "clean.freed": "Estimated space freed: {size}",
        "clean.tip": "Tip: deleted .tmp/plugins-cache and rebuilt log DB will be auto-recreated by Codex on next start.",
        "db.notexists": "not found",
        "db.vacuum_ok": "VACUUM + WAL cleanup done",
        "db.vacuum_fail": "failed: {err}",
        "db.wal_ok": "WAL checkpointed",
        "delete_ok": "deleted",
        "delete_aged_ok": "removed {n} files older than {days}d ({size})",
        "delete_fail": "failed: {err}",
        "rebuild_ok": "backed up to {name} and rebuilt (Codex recreates empty DB on next start)",
        "rebuild_fail": "failed: {err}",
        "arg.age": "only clean temp files older than N days (0 = no filter)",
        "arg.scan": "read-only scan (default)",
        "arg.clean": "run cleanup (confirm each item)",
        "arg.yes": "auto-confirm, skip interaction (required with --clean --json)",
        "arg.vacuum": "allow DB VACUUM (with --clean)",
        "arg.rebuild": "allow rebuilding oversized log DB (with --clean)",
        "arg.lang": "output language (default: auto-detect)",
        "arg.json": "machine-readable output",
        "arg.target": "which agent's data to clean (default: codex)",
        "scan.wal_hint": "Hint: WAL totals {size} - consider a periodic --clean --vacuum.",
        "scan.no_vacuum": "Note: --vacuum does not apply - no SQLite databases found under this target.",
        "scan.no_rebuild": "Note: this target has no oversized log DB, so --rebuild-logs does not apply.",
        "desc.claude-cache": "Claude Code cache (regenerable)",
        "desc.claude-debug": "Claude Code debug logs (regenerable)",
        "desc.claude-snapshots": "Shell snapshots (regenerable)",
        "desc.claude-statsig": "Statsig/telemetry cache (regenerable)",
        "desc.pi-cache": "Pi cache (regenerable; best-effort, cleaned only if present)",
        "desc.pi-tmp": "Pi temp files (regenerable; best-effort)",
        "desc.pi-logs": "Pi logs (regenerable; best-effort)",
        "desc.discovered-db": "Auto-discovered SQLite DB (VACUUM/WAL only, data kept)",
        "json.est_vs_act": "estimated={est} actual={act} delta={delta}",
    },
    "zh": {
        "prog.desc": "Codex 缓存/日志完整清理器 v{v}",
        "scan.title": "=== {label} 可清理项(只读扫描) ===",
        "scan.codedir": "{label} 目录: {path}",
        "scan.agefilter": "年龄过滤: 仅统计超过 {days} 天的文件",
        "scan.reclaim": "预计可回收: {size}",
        "scan.of_total": "  (库总 {size})",
        "scan.hint": "\n运行 --clean 逐项确认; --clean --yes 全清安全项;",
        "scan.hint2": "加 --vacuum 允许 VACUUM; 加 --rebuild-logs 允许重建超大日志库。",
        "desc.tmp": "临时下载/解压缓存(插件/市场)",
        "desc.tmp2": "Codex 临时目录",
        "desc.plugin-cache": "插件缓存(可重新下载)",
        "desc.logs-db": "运行日志库",
        "desc.state-db": "会话状态库(仅VACUUM/WAL,不清数据)",
        "desc.threads-db": "线程历史库(仅VACUUM/WAL)",
        "desc.queue-db": "队列库(仅VACUUM/WAL)",
        "desc.goals-db": "目标库(仅VACUUM/WAL)",
        "desc.memories-db": "记忆库(仅VACUUM/WAL)",
        "desc.logs-rebuild": "日志库超过 {mb}MB, 建议重建(备份后重建; VACUUM保留诊断数据)",
        "action.delete": "删除 {size}",
        "action.delete_aged": "删除超过 {days} 天的文件 ({size})",
        "action.vacuum": "VACUUM收缩+WAL清理(可回收估算)",
        "action.rebuild": "备份并重建日志库(可回收 {size})",
        "clean.none": "没有可清理的安全项(纯删除项已无? 或需加 --vacuum/--rebuild-logs)",
        "confirm.autoyes": "已通过 --yes 自动确认以下项:",
        "confirm.title": "=== 待确认清理项 ===",
        "confirm.prompt": "\n输入要清理的编号(逗号分隔), 或 all=全部, 或空=取消:",
        "confirm.invalid": "输入无效, 取消",
        "confirm.cancelled": "取消",
        "confirm.none": "未选择任何项",
        "clean.title": "\n=== 执行清理 ===",
        "clean.estimated": "预估: {size}",
        "clean.actual": "实际释放: {size}",
        "clean.delta": "与预估差值: {delta}",
        "clean.freed": "预计释放: {size}",
        "clean.tip": "提示: 删除的 .tmp/plugins-cache 和重建的日志库, Codex 下次启动会自动重建所需部分。",
        "db.notexists": "不存在",
        "db.vacuum_ok": "VACUUM+WAL清理完成",
        "db.vacuum_fail": "失败: {err}",
        "db.wal_ok": "WAL 已 checkpoint",
        "delete_ok": "已删除",
        "delete_aged_ok": "已删除 {n} 个超过 {days} 天的文件 ({size})",
        "delete_fail": "失败: {err}",
        "rebuild_ok": "已备份到 {name} 并重建(Codex下次启动自动生成空库)",
        "rebuild_fail": "失败: {err}",
        "arg.age": "仅清理超过 N 天的临时文件 (0=不过滤)",
        "arg.scan": "只读扫描(默认)",
        "arg.clean": "执行清理(逐项确认)",
        "arg.yes": "自动确认, 跳过交互(--clean --json 时必需)",
        "arg.vacuum": "允许数据库 VACUUM (配合 --clean)",
        "arg.rebuild": "允许重建超大日志库 (配合 --clean)",
        "arg.lang": "输出语言(默认自动检测)",
        "arg.json": "机器可读输出",
        "arg.target": "要清理哪个 agent 的数据(默认: codex)",
        "scan.wal_hint": "提示: WAL 合计 {size}, 建议定期执行 --clean --vacuum。",
        "scan.no_vacuum": "说明: --vacuum 不适用——该目标下未发现 SQLite 数据库。",
        "scan.no_rebuild": "说明: 该目标没有超大日志库, --rebuild-logs 不适用。",
        "desc.claude-cache": "Claude Code 缓存(可再生)",
        "desc.claude-debug": "Claude Code 调试日志(可再生)",
        "desc.claude-snapshots": "Shell 快照(可再生)",
        "desc.claude-statsig": "Statsig/遥测缓存(可再生)",
        "desc.pi-cache": "Pi 缓存(可再生; 尽力而为, 仅当存在时清理)",
        "desc.pi-tmp": "Pi 临时文件(可再生; 尽力而为)",
        "desc.pi-logs": "Pi 日志(可再生; 尽力而为)",
        "desc.discovered-db": "自动发现的 SQLite 库(仅VACUUM/WAL, 保留数据)",
        "json.est_vs_act": "预估={est} 实际={act} 差值={delta}",
    },
}

_LANG = "en"
_AGE_DAYS = 0


def _t(key: str, **kw) -> str:
    table = _MSGS.get(_LANG) or _MSGS["en"]
    tmpl = table.get(key) or _MSGS["en"].get(key, key)
    return tmpl.format(**kw) if kw else tmpl


def _detect_sys_lang() -> str:
    """Return OS UI language hint: 'zh' for Chinese, 'en' otherwise."""
    if os.name == "nt":
        try:
            import ctypes
            lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            if (lang_id & 0x3FF) == 0x04:  # Chinese primary language
                return "zh"
        except Exception:
            pass
    return "en"


def _pre_scan_lang(argv: list[str]) -> str:
    """Read the requested language before argparse builds its localized help text."""
    for i, a in enumerate(argv):
        if a == "--lang" and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith("--lang="):
            return a.split("=", 1)[1]
    return os.environ.get("CODEX_CLEAN_LANG") or "auto"


def _resolve_lang(lang_arg: str) -> str:
    if lang_arg in ("en", "zh"):
        return lang_arg
    for env in ("CODEX_CLEAN_LANG", "LANG", "LC_ALL"):
        v = os.environ.get(env, "")
        if v.lower().startswith("zh"):
            return "zh"
        if v.lower().startswith("en"):
            return "en"
    return _detect_sys_lang()


# Backwards-compatible aliases (Codex stays the default target).
CODEX_HOME = agent_home("codex")
PROTECTED = AGENTS["codex"]["protected"]

LOGS_REBUILD_MB = 100
WAL_WARN_MB = 32


# Helpers
def _size_of(p: Path) -> int:
    if not p.exists():
        return 0
    if p.is_file():
        try:
            return p.stat().st_size
        except Exception:
            return 0
    total = 0
    try:
        for root, _dirs, files in os.walk(p):
            for f in files:
                try:
                    total += (Path(root) / f).stat().st_size
                except Exception:
                    pass
    except Exception:
        pass
    return total


def human(n: int) -> str:
    n = max(0, n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} GB"


def _db_sizes(db_path: Path) -> tuple[int, int, int]:
    main = _size_of(db_path)
    wal = _size_of(Path(str(db_path) + "-wal"))
    shm = _size_of(Path(str(db_path) + "-shm"))
    return main, wal, shm


def _age_stats(root: Path, days: float) -> tuple[int, int, int, int]:
    """Return (eligible_bytes, eligible_count, total_bytes, total_count); days<=0 = no filter."""
    if not root.exists():
        return 0, 0, 0, 0
    cutoff = time.time() - days * 86400 if days > 0 else None
    if root.is_file():
        try:
            st = root.stat()
        except Exception:
            return 0, 0, 0, 0
        old = cutoff is None or st.st_mtime < cutoff
        return (st.st_size, 1, st.st_size, 1) if old else (0, 0, st.st_size, 1)
    eb = ec = tb = tc = 0
    for r, _d, fs in os.walk(root):
        for f in fs:
            try:
                st = (Path(r) / f).stat()
            except Exception:
                continue
            tb += st.st_size
            tc += 1
            if cutoff is None or st.st_mtime < cutoff:
                eb += st.st_size
                ec += 1
    return eb, ec, tb, tc


def _planned_action(kind: str, path: str, reclaim_bytes: int, days: int) -> dict:
    """Structured dry-run preview of what cleaning this item would do."""
    return {
        "type": kind,
        "target": path,
        "reclaimable_bytes": reclaim_bytes,
        "reclaimable": human(reclaim_bytes),
        "reversible": kind == "vacuum",  # vacuum keeps data; deletes do not
        "confirm_required": True,
        "age_filter_days": days if (days > 0 and kind == "delete") else None,
    }


def scan(age_days: int = 0, target: str = "codex"):
    spec = AGENTS.get(target) or AGENTS["codex"]
    home = agent_home(target)
    caps = spec["capabilities"]
    items = []
    for name, rel, dkey in spec["deletable"]:
        path = home / rel
        eb, ec, tb, tc = _age_stats(path, age_days)
        # With an age filter only the eligible bytes are actually reclaimable.
        sz = eb if age_days > 0 else tb
        action = (_t("action.delete_aged", days=age_days, size=human(sz))
                  if age_days > 0 else _t("action.delete", size=human(sz)))
        items.append({
            "kind": "delete", "name": name, "path": str(path), "agent": target,
            "desc": _t(dkey), "size_bytes": sz, "size": human(sz),
            "exists": path.exists(), "action": action,
            "age_filter_days": age_days if age_days > 0 else None,
            "eligible_bytes": eb, "eligible_size": human(eb),
            "eligible_files": ec, "total_files": tc,
            "total_bytes": tb, "total_size": human(tb),
            "reclaimable_bytes": sz,
            "planned_action": _planned_action("delete", str(path), sz, age_days),
            "safe": True,
        })
    if caps["vacuum"]:
        db_specs = list(spec["dbs"])
        # No fixed DB list -> discover SQLite files at runtime. Finding none is
        # normal for agents that store JSONL; --vacuum then reports "does not apply".
        if spec.get("discover_dbs"):
            for pat in ("*.sqlite", "*.sqlite3", "*.db"):
                for p in sorted(home.glob(pat)):
                    if p.is_file() and all(p.name != r for _n, r, _k in db_specs):
                        db_specs.append((p.stem, p.name, "desc.discovered-db"))
        for name, rel, dkey in db_specs:
            db_path = home / rel
            main, wal, shm = _db_sizes(db_path)
            total = main + wal + shm
            has_db = db_path.exists()
            items.append({
                "kind": "vacuum", "name": name, "path": str(db_path), "agent": target,
                "desc": _t(dkey), "size_bytes": total, "size": human(total),
                "exists": has_db, "db_main": main, "db_wal": wal, "db_shm": shm,
                "action": _t("action.vacuum"),
                "age_filter_days": None,
                "reclaimable_bytes": wal,
                "planned_action": _planned_action("vacuum", str(db_path), wal, 0),
                "safe": True,
            })
            if spec["rebuild_db"] == name and main > LOGS_REBUILD_MB * 1024 * 1024:
                items.append({
                    "kind": "rebuild", "name": "logs-rebuild", "path": str(db_path),
                    "agent": target,
                    "desc": _t("desc.logs-rebuild", mb=LOGS_REBUILD_MB),
                    "size_bytes": main, "size": human(main), "exists": True,
                    "action": _t("action.rebuild", size=human(main)),
                    "age_filter_days": None,
                    "reclaimable_bytes": main,
                    "planned_action": _planned_action("rebuild", str(db_path), main, 0),
                    "safe": False,  # destructive: requires explicit --rebuild-logs
                })
    # Surface the biggest reclaimable wins first for easier triage.
    items.sort(key=lambda i: i.get("reclaimable_bytes", 0), reverse=True)
    return items


def vacuum_db(db_path: Path) -> tuple[bool, str, int]:
    """VACUUM + WAL checkpoint. Returns (ok, message, reclaimed_bytes).

    reclaimed_bytes is the measured before/after size delta (main + wal + shm).
    """
    if not db_path.exists():
        return False, _t("db.notexists"), 0
    before = sum(_db_sizes(db_path))
    try:
        con = sqlite3.connect(str(db_path), timeout=5)
        con.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        con.execute("VACUUM;")
        con.commit()
        con.close()
        after = sum(_db_sizes(db_path))
        return True, _t("db.vacuum_ok"), max(0, before - after)
    except Exception as e:
        after = sum(_db_sizes(db_path))
        return False, _t("db.vacuum_fail", err=e), max(0, before - after)


def delete_item(path: Path) -> tuple[bool, str]:
    try:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink()
        return True, _t("delete_ok")
    except Exception as e:
        return False, _t("delete_fail", err=e)


def delete_item_aged(path: Path, days: int) -> tuple[bool, str, int]:
    """Delete only files older than `days`; keep newer ones. Returns (ok, msg, freed)."""
    cutoff = time.time() - days * 86400
    freed = 0
    removed = 0
    failed = 0
    try:
        if path.is_file():
            st = path.stat()
            if st.st_mtime < cutoff:
                freed += st.st_size
                path.unlink()
                removed += 1
        else:
            for r, _d, fs in os.walk(path):
                for f in fs:
                    p = Path(r) / f
                    try:
                        st = p.stat()
                        if st.st_mtime < cutoff:
                            p.unlink()
                            freed += st.st_size
                            removed += 1
                    except Exception:
                        failed += 1
            # Drop directories that became empty (never the root itself).
            for r, _d, fs in os.walk(path, topdown=False):
                if str(Path(r)) == str(path):
                    continue
                try:
                    if not os.listdir(r):
                        os.rmdir(r)
                except Exception:
                    pass
    except Exception as e:
        return False, _t("delete_fail", err=e), freed
    msg = _t("delete_aged_ok", n=removed, days=days, size=human(freed))
    if failed:
        msg += f" ({failed} skipped)"
    return True, msg, freed


def rebuild_logs(db_path: Path) -> tuple[bool, str]:
    if not db_path.exists():
        return False, _t("db.notexists")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    bak = Path(str(db_path) + f".bak-{stamp}")
    try:
        shutil.copy2(db_path, bak)
        for suffix in ("", "-wal", "-shm"):
            p = Path(str(db_path) + suffix)
            if p.exists():
                p.unlink()
        return True, _t("rebuild_ok", name=bak.name)
    except Exception as e:
        return False, _t("rebuild_fail", err=e)


# CLI
def main():
    global _LANG, _AGE_DAYS
    # Resolve language before building the parser so --help is localized too.
    _LANG = _resolve_lang(_pre_scan_lang(sys.argv))
    ap = argparse.ArgumentParser(description=_t("prog.desc", v=VERSION))
    ap.add_argument("--scan", action="store_true", help=_t("arg.scan"))
    ap.add_argument("--clean", action="store_true", help=_t("arg.clean"))
    ap.add_argument("--yes", action="store_true", help=_t("arg.yes"))
    ap.add_argument("--vacuum", action="store_true", help=_t("arg.vacuum"))
    ap.add_argument("--rebuild-logs", action="store_true", help=_t("arg.rebuild"))
    ap.add_argument("--age", type=int, default=0, metavar="N", help=_t("arg.age"))
    ap.add_argument("--target", choices=sorted(AGENTS), default="codex",
                    help=_t("arg.target"))
    ap.add_argument("--lang", choices=["en", "zh", "auto"], default="auto",
                    help=_t("arg.lang"))
    ap.add_argument("--json", action="store_true", help=_t("arg.json"))
    args = ap.parse_args()

    if args.age < 0:
        ap.error("--age must be >= 0")

    _LANG = _resolve_lang(args.lang)
    _AGE_DAYS = args.age
    spec = AGENTS[args.target]
    home = agent_home(args.target)
    items = scan(args.age, args.target)

    if not args.clean:
        if args.json:
            print(json.dumps(items, ensure_ascii=False, default=str))
            return 0
        print(_t("scan.title", label=spec["label"]))
        print(_t("scan.codedir", label=spec["label"], path=home))
        if args.vacuum and not any(i["kind"] == "vacuum" for i in items):
            print(_t("scan.no_vacuum"))
        if args.rebuild_logs and not spec["capabilities"]["rebuild_logs"]:
            print(_t("scan.no_rebuild"))
        if args.age > 0:
            print(_t("scan.agefilter", days=args.age))
        print()
        for it in items:
            # Column shows the reclaimable amount so it sums to the footer; the DB
            # total is annotated when the two differ (VACUUM reclaims the WAL only).
            disp = it.get("reclaimable_bytes", it["size_bytes"])
            note = _t("scan.of_total", size=it["size"]) if disp != it["size_bytes"] else ""
            print(f"  [{it['kind']:<6}] {human(disp):>10}  {it['name']:<24} {it['desc']}{note}")
            if it["exists"]:
                print(f"              {it['path']}")
        wal_total = sum(i.get("db_wal", 0) for i in items if i["kind"] == "vacuum")
        if wal_total > WAL_WARN_MB * 1024 * 1024:
            print(_t("scan.wal_hint", size=human(wal_total)))
        tot = sum(i.get("reclaimable_bytes", 0) for i in items if i["exists"])
        print(f"\n{_t('scan.reclaim', size=human(tot))}")
        print(_t("scan.hint"))
        print(_t("scan.hint2"))
        return 0

    # --- cleanup ---
    allow_vacuum = args.vacuum and spec["capabilities"]["vacuum"]
    allow_rebuild = args.rebuild_logs and spec["capabilities"]["rebuild_logs"]

    candidates = []
    for it in items:
        if not it["exists"]:
            continue
        if it["kind"] == "delete":
            candidates.append(it)
        elif it["kind"] == "vacuum" and allow_vacuum:
            candidates.append(it)
        elif it["kind"] == "rebuild" and allow_rebuild:
            candidates.append(it)

    if not candidates:
        print(_t("clean.none"))
        return 0

    confirmed = []
    if args.yes:
        confirmed = [c["name"] for c in candidates]
        if not args.json:
            print(_t("confirm.autoyes"))
    else:
        if args.json:
            # Non-interactive JSON mode requires --yes.
            print(_t("confirm.none"))
            return 0
        print(_t("confirm.title"))
        for i, c in enumerate(candidates):
            print(f"  [{i + 1}] {c['name']:<16} ({c['size']:>8})  {c['desc']}")
        print(_t("confirm.prompt"))
        try:
            resp = input("> ").strip().lower()
        except EOFError:
            resp = ""
        if resp in ("all", "a"):
            confirmed = [c["name"] for c in candidates]
        elif resp:
            try:
                idxs = [int(x) for x in resp.split(",") if x.strip()]
                confirmed = [candidates[i - 1]["name"] for i in idxs
                             if 1 <= i <= len(candidates)]
            except ValueError:
                print(_t("confirm.invalid"))
                return 0
        else:
            print(_t("confirm.cancelled"))
            return 0

    if not confirmed:
        print(_t("confirm.none"))
        return 0

    estimated = sum(c.get("reclaimable_bytes", c["size_bytes"])
                    for c in candidates if c["name"] in confirmed)
    results = []
    freed = 0

    if not args.json:
        print(_t("clean.title"))

    for it in items:
        if it["name"] not in confirmed:
            continue
        est = it["size_bytes"]
        if it["kind"] == "delete":
            if args.age > 0:
                ok, msg, got = delete_item_aged(Path(it["path"]), args.age)
            else:
                ok, msg = delete_item(Path(it["path"]))
                got = est if ok else 0
            if ok:
                freed += got
            results.append({"name": it["name"], "kind": "delete",
                            "status": "ok" if ok else "failed",
                            "estimated_bytes": est, "actual_bytes": got if ok else 0,
                            "message": msg})
            if not args.json:
                print(f"  {('✓' if ok else '✗')} {it['name']}: {msg}")
        elif it["kind"] == "vacuum":
            if allow_vacuum:
                # `got` is the measured shrink (before - after), not just the WAL size.
                ok, msg, got = vacuum_db(Path(it["path"]))
                freed += got
                results.append({"name": it["name"], "kind": "vacuum",
                                "status": "ok" if ok else "failed",
                                "estimated_bytes": est, "actual_bytes": got,
                                "message": msg})
                if not args.json:
                    print(f"  {('✓' if ok else '✗')} {it['name']} (VACUUM): {msg}")
        elif it["kind"] == "rebuild":
            if allow_rebuild:
                ok, msg = rebuild_logs(Path(it["path"]))
                got = est if ok else 0
                if ok:
                    freed += got
                results.append({"name": it["name"], "kind": "rebuild",
                                "status": "ok" if ok else "failed",
                                "estimated_bytes": est, "actual_bytes": got,
                                "message": msg})
                if not args.json:
                    print(f"  {('✓' if ok else '✗')} {it['name']} (rebuild): {msg}")

    if args.json:
        print(json.dumps({
            "ok": True,
            "dry_run": False,
            "version": VERSION,
            "agent": args.target,
            "agent_home": str(home),
            "codex_home": str(CODEX_HOME),
            "age_filter_days": args.age if args.age > 0 else None,
            "estimated_bytes": estimated,
            "estimated": human(estimated),
            "actual_freed_bytes": freed,
            "actual_freed": human(freed),
            "delta_bytes": freed - estimated,
            "summary": _t("json.est_vs_act", est=human(estimated),
                          act=human(freed), delta=human(freed - estimated)),
            "items": results,
            "protected_untouched": spec["protected"],
        }, ensure_ascii=False, default=str))
        return 0

    print(f"\n{_t('clean.estimated', size=human(estimated))}")
    print(_t("clean.actual", size=human(freed)))
    print(_t("clean.delta", delta=human(freed - estimated)))
    print(_t("clean.tip"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
