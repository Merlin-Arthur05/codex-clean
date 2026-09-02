#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Codex 自身缓存/日志完整清理器 (v2)。

清理 Codex 工作目录里【安全、可再生】的缓存与日志，采用【逐项确认】模式。
本脚本绝不自动触碰受保护数据(对话历史/状态/记忆/配置/二进制)。

可处理项(逐项确认后执行):
  A. 纯删除(可再生):  .tmp / tmp / plugins/cache
  B. 日志库 VACUUM 收缩: 对 logs_2.sqlite 等运行 VACUUM, 释放空洞空间(保留诊断数据)
  C. WAL/SHM checkpoint 清理: 各 sqlite 的 -wal/-shm 安全合并清理
  D. 超限日志库重建: 日志库超过阈值时, 备份后重建(可选, 需额外确认)

用法:
  python codex_clean.py --scan          # 只读扫描, 列出所有可处理项+大小(默认)
  python codex_clean.py --clean         # 进入逐项确认模式(交互询问哪些项要清)
  python codex_clean.py --clean --yes   # 跳过交互, 清理全部"纯删除+WAL"安全项
  python codex_clean.py --clean --yes --vacuum   # 含日志库 VACUUM
  python codex_clean.py --json          # 结构化输出

退出码: 0 成功; 2 参数错误
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

# ---- A. 纯删除项(可再生) ----
DELETABLE = [
    ("tmp",         CODEX_HOME / ".tmp",      "临时下载/解压缓存(插件/市场)"),
    ("tmp2",        CODEX_HOME / "tmp",       "Codex 临时目录"),
    ("plugin-cache",CODEX_HOME / "plugins"/"cache", "插件缓存(可重新下载)"),
]

# ---- B/C. sqlite 库列表(VACUUM + WAL 清理) ----
SQLITE_DBS = [
    ("logs-db",  CODEX_HOME / "logs_2.sqlite",  "运行日志库"),
    ("state-db", CODEX_HOME / "state_5.sqlite", "会话状态库(仅VACUUM/WAL,不清数据)"),
    ("threads-db",CODEX_HOME / "thread_history_1.sqlite", "线程历史库(仅VACUUM/WAL)"),
    ("queue-db", CODEX_HOME / "queue_1.sqlite", "队列库(仅VACUUM/WAL)"),
    ("goals-db", CODEX_HOME / "goals_1.sqlite", "目标库(仅VACUUM/WAL)"),
    ("memories-db",CODEX_HOME / "memories_1.sqlite", "记忆库(仅VACUUM/WAL)"),
]

# 日志库超过该 MB 才提示"可重建"(日志可删, 其他库只vacuum不清数据)
LOGS_REBUILD_MB = 100


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
    """返回 (主库, wal, shm) 字节。"""
    main = _size_of(db_path)
    wal = _size_of(Path(str(db_path) + "-wal"))
    shm = _size_of(Path(str(db_path) + "-shm"))
    return main, wal, shm


def scan():
    """返回所有可处理项的详细信息。"""
    items = []
    for name, path, desc in DELETABLE:
        sz = _size_of(path)
        items.append({
            "kind": "delete", "name": name, "path": str(path), "desc": desc,
            "size_bytes": sz, "size": human(sz), "exists": path.exists(),
            "action": f"删除 {human(sz)}",
        })
    # 数据库 VACUUM/WAL 项
    for name, db_path, desc in SQLITE_DBS:
        main, wal, shm = _db_sizes(db_path)
        total = main + wal + shm
        has_db = db_path.exists()
        items.append({
            "kind": "vacuum", "name": name, "path": str(db_path), "desc": desc,
            "size_bytes": total, "size": human(total), "exists": has_db,
            "db_main": main, "db_wal": wal, "db_shm": shm,
            "action": f"VACUUM收缩+WAL清理(可回收估算)",
        })
        # 额外标记: 日志库超大(可重建)
        if name == "logs-db" and main > LOGS_REBUILD_MB * 1024 * 1024:
            items.append({
                "kind": "rebuild", "name": "logs-rebuild", "path": str(db_path),
                "desc": f"日志库超过{LOGS_REBUILD_MB}MB, 建议重建(备份后删, 保留诊断可VACUUM)",
                "size_bytes": main, "size": human(main), "exists": True,
                "action": f"备份并重建日志库(可回收 {human(main)})",
            })
    return items


def vacuum_db(db_path: Path) -> tuple[bool, str]:
    """对 sqlite 执行 checkpoint + VACUUM 收缩。保留数据。"""
    if not db_path.exists():
        return False, "不存在"
    try:
        con = sqlite3.connect(str(db_path), timeout=5)
        con.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        con.execute("VACUUM;")
        con.commit()
        con.close()
        return True, "VACUUM+WAL清理完成"
    except Exception as e:
        return False, f"失败: {e}"


def clean_wal(db_path: Path) -> tuple[bool, str]:
    """只 checkpoint + 清空 WAL, 不动主库数据。"""
    if not db_path.exists():
        return False, "主库不存在"
    try:
        con = sqlite3.connect(str(db_path), timeout=5)
        con.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        con.commit()
        con.close()
        return True, "WAL已checkpoint"
    except Exception as e:
        return False, f"失败: {e}"


def delete_item(path: Path) -> tuple[bool, str]:
    try:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink()
        return True, "已删除"
    except Exception as e:
        return False, f"失败: {e}"


def rebuild_logs(db_path: Path) -> tuple[bool, str]:
    """超大日志库: 备份后重建空库(释放空间)。"""
    if not db_path.exists():
        return False, "不存在"
    stamp = time.strftime("%Y%m%d-%H%M%S")
    bak = Path(str(db_path) + f".bak-{stamp}")
    try:
        shutil.copy2(db_path, bak)
        # 关闭连接后删原库
        for suffix in ("", "-wal", "-shm"):
            p = Path(str(db_path) + suffix)
            if p.exists():
                p.unlink()
        return True, f"已备份到 {bak.name} 并重建(Codex下次启动自动生成空库)"
    except Exception as e:
        return False, f"失败: {e}"


def estimate_free(items, confirmed) -> int:
    """估算确认项能释放多少(VACUUM按 wal+50%主库空洞粗估)。"""
    total = 0
    for it in items:
        if it["name"] not in confirmed:
            continue
        if it["kind"] == "delete":
            total += it["size_bytes"]
        elif it["kind"] == "vacuum":
            # vacuum 粗略可回收 wal+部分
            total += it.get("db_wal", 0)
        elif it["kind"] == "rebuild":
            total += it["size_bytes"]
    return total


def main():
    ap = argparse.ArgumentParser(description="Codex 缓存/日志完整清理器 v2")
    ap.add_argument("--scan", action="store_true", help="只读扫描(默认)")
    ap.add_argument("--clean", action="store_true", help="执行清理(逐项确认)")
    ap.add_argument("--yes", action="store_true", help="自动确认(跳过交互)")
    ap.add_argument("--vacuum", action="store_true",
                    help="允许对数据库执行 VACUUM(需配合--clean)")
    ap.add_argument("--rebuild-logs", action="store_true",
                    help="允许重建超大日志库(需配合--clean)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    items = scan()

    if not args.clean:
        # 只读扫描
        if args.json:
            print(json.dumps(items, ensure_ascii=False, default=str))
            return 0
        print("=== Codex 可清理项(只读扫描) ===")
        print(f"Codex 目录: {CODEX_HOME}\n")
        for it in items:
            exists = "✓" if it["exists"] else "·"
            print(f"  [{it['kind']:<6}] {it['size']:>10}  {it['name']:<14} {it['desc']}")
            if it["exists"]:
                print(f"              {it['path']}")
        tot = sum(i["size_bytes"] for i in items if i["exists"])
        print(f"\n全部可回收(含VACUUM): {human(tot)}")
        print("\n运行 --clean 逐项确认; --clean --yes 全清安全项; 加 --vacuum 允许VACUUM;")
        print("加 --rebuild-logs 允许重建超大日志库。")
        return 0

    # ---- 清理模式 ----
    # 1. 确定允许的动作集
    allow_vacuum = args.vacuum
    allow_rebuild = args.rebuild_logs

    # 2. 选定候选: 纯删除项 + (若允许) vacuum/rebuild 项
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
        print("没有可清理的安全项(纯删除项已无? 或需加 --vacuum/--rebuild-logs)")
        return 0

    # 3. 确认
    confirmed = []
    if args.yes:
        confirmed = [c["name"] for c in candidates]
        print("已通过 --yes 自动确认以下项:")
    else:
        print("=== 待确认清理项 ===")
        for i, c in enumerate(candidates):
            print(f"  [{i+1}] {c['name']:<16} ({c['size']:>8})  {c['desc']}")
        print("\n输入要清理的编号(逗号分隔), 或 all=全部, 或空=取消:")
        try:
            resp = input("> ").strip().lower()
        except EOFError:
            resp = ""
        if resp in ("all", "a"):
            confirmed = [c["name"] for c in candidates]
        elif resp:
            try:
                idxs = [int(x) for x in resp.split(",") if x.strip()]
                confirmed = [candidates[i-1]["name"] for i in idxs
                             if 1 <= i <= len(candidates)]
            except ValueError:
                print("输入无效, 取消")
                return 0
        else:
            print("取消")
            return 0

    if not confirmed:
        print("未选择任何项")
        return 0

    # 4. 执行
    print("\n=== 执行清理 ===")
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
                print(f"  {('✓' if ok else '✗')} {it['name']}(VACUUM): {msg}")
        elif it["kind"] == "rebuild":
            if allow_rebuild:
                ok, msg = rebuild_logs(Path(it["path"]))
                if ok:
                    freed += it["size_bytes"]
                print(f"  {('✓' if ok else '✗')} {it['name']}(重建): {msg}")

    print(f"\n预计释放: {human(freed)}")
    print("提示: 删除的 .tmp/plugins-cache 和重建的日志库, Codex 下次启动会自动重建所需部分。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
