#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Codex cache/log full cleaner (v2.1) — i18n enabled.

Safely cleans regenerable cache/log/WAL files under ~/.codex, using a strict
whitelist and a confirm-before-clean workflow. Protected data (conversations,
state DBs, config, executables, user projects) is NEVER touched.

Cleanable targets (each confirmed before running):
  A. Delete (regenerable):  .tmp / tmp / plugins/cache
  B. VACUUM shrink log DB:   logs_2.sqlite (space reclaimed, data kept)
  C. WAL/SHM checkpoint:     merge & truncate sqlite WAL files
  D. Rebuild oversized log DB: back up then recreate (>100 MB, opt-in)

Usage:
  python codex_clean.py --scan [--lang zh|en|auto]   # read-only scan (default)
  python codex_clean.py --clean                       # interactive confirm
  python codex_clean.py --clean --yes                 # non-interactive safe items
  python codex_clean.py --clean --yes --vacuum        # also VACUUM the DBs
  python codex_clean.py --json                        # machine-readable output

Language detection order: --lang > CODEX_CLEAN_LANG > LANG/LC_ALL > OS UI lang > en.
Exit codes: 0 success; 2 bad args.
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

CODEX_HOME = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")

# ---------------------------------------------------------------- i18n ----
_MSGS = {
    "en": {
        "prog.desc": "Codex cache/log cleaner v2.1",
        "scan.title": "=== Codex cleanable items (read-only scan) ===",
        "scan.codedir": "Codex directory: {path}",
        "scan.reclaim": "Total reclaimable (incl. VACUUM): {size}",
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
        "clean.freed": "Estimated space freed: {size}",
        "clean.tip": "Tip: deleted .tmp/plugins-cache and rebuilt log DB will be auto-recreated by Codex on next start.",
        "db.notexists": "not found",
        "db.vacuum_ok": "VACUUM + WAL cleanup done",
        "db.vacuum_fail": "failed: {err}",
        "db.wal_ok": "WAL checkpointed",
        "delete_ok": "deleted",
        "delete_fail": "failed: {err}",
        "rebuild_ok": "backed up to {name} and rebuilt (Codex recreates empty DB on next start)",
        "rebuild_fail": "failed: {err}",
    },
    "zh": {
        "prog.desc": "Codex 缓存/日志完整清理器 v2.1",
        "scan.title": "=== Codex 可清理项(只读扫描) ===",
        "scan.codedir": "Codex 目录: {path}",
        "scan.reclaim": "全部可回收(含VACUUM): {size}",
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
        "clean.freed": "预计释放: {size}",
        "clean.tip": "提示: 删除的 .tmp/plugins-cache 和重建的日志库, Codex 下次启动会自动重建所需部分。",
        "db.notexists": "不存在",
        "db.vacuum_ok": "VACUUM+WAL清理完成",
        "db.vacuum_fail": "失败: {err}",
        "db.wal_ok": "WAL 已 checkpoint",
        "delete_ok": "已删除",
        "delete_fail": "失败: {err}",
        "rebuild_ok": "已备份到 {name} 并重建(Codex下次启动自动生成空库)",
        "rebuild_fail": "失败: {err}",
    },
}

_LANG = "en"


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


def _resolve_lang(lang_arg: str) -> str:
    if lang_arg in ("en", "zh"):
        return lang_arg
    # auto: env override > locale env > OS UI language
    for env in ("CODEX_CLEAN_LANG", "LANG", "LC_ALL"):
        v = os.environ.get(env, "")
        if v.lower().startswith("zh"):
            return "zh"
        if v.lower().startswith("en"):
            return "en"
    return _detect_sys_lang()


# ------------------------------------------------------- target lists -----
DELETABLE = [
    ("tmp", CODEX_HOME / ".tmp", "desc.tmp"),
    ("tmp2", CODEX_HOME / "tmp", "desc.tmp2"),
    ("plugin-cache", CODEX_HOME / "plugins" / "cache", "desc.plugin-cache"),
]

SQLITE_DBS = [
    ("logs-db", CODEX_HOME / "logs_2.sqlite", "desc.logs-db"),
    ("state-db", CODEX_HOME / "state_5.sqlite", "desc.state-db"),
    ("threads-db", CODEX_HOME / "thread_history_1.sqlite", "desc.threads-db"),
    ("queue-db", CODEX_HOME / "queue_1.sqlite", "desc.queue-db"),
    ("goals-db", CODEX_HOME / "goals_1.sqlite", "desc.goals-db"),
    ("memories-db", CODEX_HOME / "memories_1.sqlite", "desc.memories-db"),
]

LOGS_REBUILD_MB = 100


# ------------------------------------------------------------- helpers ----
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


def scan():
    items = []
    for name, path, dkey in DELETABLE:
        sz = _size_of(path)
        items.append({
            "kind": "delete", "name": name, "path": str(path),
            "desc": _t(dkey), "size_bytes": sz, "size": human(sz),
            "exists": path.exists(), "action": _t("action.delete", size=human(sz)),
        })
    for name, db_path, dkey in SQLITE_DBS:
        main, wal, shm = _db_sizes(db_path)
        total = main + wal + shm
        has_db = db_path.exists()
        items.append({
            "kind": "vacuum", "name": name, "path": str(db_path),
            "desc": _t(dkey), "size_bytes": total, "size": human(total),
            "exists": has_db, "db_main": main, "db_wal": wal, "db_shm": shm,
            "action": _t("action.vacuum"),
        })
        if name == "logs-db" and main > LOGS_REBUILD_MB * 1024 * 1024:
            items.append({
                "kind": "rebuild", "name": "logs-rebuild", "path": str(db_path),
                "desc": _t("desc.logs-rebuild", mb=LOGS_REBUILD_MB),
                "size_bytes": main, "size": human(main), "exists": True,
                "action": _t("action.rebuild", size=human(main)),
            })
    return items


def vacuum_db(db_path: Path) -> tuple[bool, str]:
    if not db_path.exists():
        return False, _t("db.notexists")
    try:
        con = sqlite3.connect(str(db_path), timeout=5)
        con.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        con.execute("VACUUM;")
        con.commit()
        con.close()
        return True, _t("db.vacuum_ok")
    except Exception as e:
        return False, _t("db.vacuum_fail", err=e)


def delete_item(path: Path) -> tuple[bool, str]:
    try:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink()
        return True, _t("delete_ok")
    except Exception as e:
        return False, _t("delete_fail", err=e)


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


# ----------------------------------------------------------------- main ----
def main():
    global _LANG
    ap = argparse.ArgumentParser(description=_t("prog.desc"))
    ap.add_argument("--scan", action="store_true", help="read-only scan (default)")
    ap.add_argument("--clean", action="store_true", help="run cleanup (confirm each item)")
    ap.add_argument("--yes", action="store_true", help="auto-confirm (skip interaction)")
    ap.add_argument("--vacuum", action="store_true", help="allow DB VACUUM (with --clean)")
    ap.add_argument("--rebuild-logs", action="store_true",
                    help="allow rebuilding oversized log DB (with --clean)")
    ap.add_argument("--lang", choices=["en", "zh", "auto"], default="auto",
                    help="output language (default: auto-detect)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    _LANG = _resolve_lang(args.lang)
    items = scan()

    if not args.clean:
        if args.json:
            print(json.dumps(items, ensure_ascii=False, default=str))
            return 0
        print(_t("scan.title"))
        print(_t("scan.codedir", path=CODEX_HOME))
        print()
        for it in items:
            exists = "✓" if it["exists"] else "·"
            print(f"  [{it['kind']:<6}] {it['size']:>10}  {it['name']:<14} {it['desc']}")
            if it["exists"]:
                print(f"              {it['path']}")
        tot = sum(i["size_bytes"] for i in items if i["exists"])
        print(f"\n{_t('scan.reclaim', size=human(tot))}")
        print(_t("scan.hint"))
        print(_t("scan.hint2"))
        return 0

    # ---- cleanup mode ----
    allow_vacuum = args.vacuum
    allow_rebuild = args.rebuild_logs

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
        print(_t("confirm.autoyes"))
    else:
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

    print(_t("clean.title"))
    freed = 0
    for it in items:
        if it["name"] not in confirmed:
            continue
        if it["kind"] == "delete":
            ok, msg = delete_item(Path(it["path"]))
            if ok:
                freed += it["size_bytes"]
            print(f"  {('✓' if ok else '✗')} {it['name']}: {msg}")
        elif it["kind"] == "vacuum":
            if allow_vacuum:
                ok, msg = vacuum_db(Path(it["path"]))
                freed += it.get("db_wal", 0)
                print(f"  {('✓' if ok else '✗')} {it['name']} (VACUUM): {msg}")
        elif it["kind"] == "rebuild":
            if allow_rebuild:
                ok, msg = rebuild_logs(Path(it["path"]))
                if ok:
                    freed += it["size_bytes"]
                print(f"  {('✓' if ok else '✗')} {it['name']} (rebuild): {msg}")

    print(f"\n{_t('clean.freed', size=human(freed))}")
    print(_t("clean.tip"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
