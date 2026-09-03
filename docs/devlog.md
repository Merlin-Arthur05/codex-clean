# codex-clean 开发日志 / Development Log

> 本文件按迭代记录设计决策、实现要点与审查结论。版本号遵循 semver：变化幅度决定第二位（MINOR，向后兼容的新功能）还是第三位（PATCH，文档/小修）；MAJOR 仅用于不兼容的 API 变更。
> 脚本内 `VERSION` 常量必须与 GitHub Release 版本号完全一致（单一来源）。

---

## v1.2.0 — Iteration 1（2026-09-03 发布）

**范围**：Milestone #1，对应 Issue #1 / #2 / #3，3/3 完成。

### 目标
- **#1 `--json` 增强**：扫描即给出每项"将要做什么"的预览；清理时给出「预估回收 vs 实际回收」对照，便于脚本/CI 消费与审计。
- **#2 `--age N`**：只清理超过 N 天的临时文件，新文件保留，避免误删 Codex 正在使用的缓存。
- **#3 中文文档**：新增 `README.zh-CN.md`，并说明本 skill 与通用"清理电脑"工具的本质区别。

### 实现要点
1. **版本号单一来源**：`VERSION = "1.2.0"`，`prog.desc` 用 `v{v}` 模板引用，发布前只改这一处。
2. **年龄过滤 `_age_stats`**：`days<=0` 视为不过滤；`days>0` 用 `time.time() - days*86400` 作为 cutoff，只统计 `mtime < cutoff` 的文件，并同时报告 `eligible`（符合条件）与 `total`（全部）的字节/文件数。
3. **VACUUM 实测回收量**：`vacuum_db` 测量 VACUUM 前后 `(main+wal+shm)` 的真实差值，而非沿用 WAL 大小——之前的实现让"预估 vs 实际"失去意义。
4. **`--lang` 提前解析**：新增 `_pre_scan_lang`，在 `argparse` 构建 help 文本之前预扫描 `argv` 与 `CODEX_CLEAN_LANG`，修复了 `--help` 永远英文的既有 bug；各参数 help 也做了 i18n。
5. **保护清单显式审计**：`PROTECTED`（sessions/config/auth/backups/skills…）在 `--json` 清理报告中以 `protected_untouched` 字段输出，证明未被触碰。
6. **语言解析顺序**：`--lang` > `CODEX_CLEAN_LANG` > `LANG`/`LC_ALL` > OS UI 语言（Windows 用 `GetUserDefaultUILanguage`，中文主语言 `0x04`）> `en`。

### 代码审查结论
- **安全模型**：严格白名单（仅 `DELETABLE` + `SQLITE_DBS`）+ 逐项确认 + `protected_untouched` 审计，无越权删除路径。✅
- **边界行为**：`--age 0` 不过滤；`--age -1` 经 `ap.error` 以退出码 2 拒绝；`--clean --json` 缺 `--yes` 时安全退出且零删除。✅
- **测试覆盖**：150KB 假目录（100KB 老 + 50KB 新）→ `--age 7` 仅报 100KB 并只删老文件、新文件保留；真实 `~/.codex` 扫描（.tmp 67.7MB + plugin-cache 11.8MB + logs-db 24.5MB）正常；VACUUM 实测 1.5MB 库回收 1.47MB。✅
- **非阻塞改进建议**：扫描页 "Total reclaimable" 当前把 DB 主文件大小也计入总和，会高估可回收量（VACUUM 只回收 WAL + 内部碎片，不回收主数据）。建议只累加 delete 项大小 + WAL 可回收量；JSON 的 `planned_action.reclaimable_bytes` 已较准确（vacuum 取 wal），两者可统一。不影响安全性，留待后续迭代优化。

### 发布状态
- commit `54f260d` → `main`；tag **v1.2.0** 已发布。
- Issues #1 / #2 / #3 由 commit 的 `Closes` 自动关闭；Milestone #1（v1.2.0）已关闭。
- 后续：Milestone #2 **v1.3.0**（增强清理，含 #10 pi agent 支持）、#3 **v1.4.0**（自动任务/进程检测/CI）。
