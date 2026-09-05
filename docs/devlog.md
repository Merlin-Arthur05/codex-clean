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


---

## v1.2.1 — Iteration 1 补丁（2026-09-04 发布）

**范围**：v1.2.x 补丁线（非 v1.3 迭代），纯修复与工程优化，无新功能，版本号升 PATCH。

### 优化内容
- **"可回收"总量数值修正（准确性修复）**：原扫描页汇总是把 SQLite 库的主文件大小(主+WAL+SHM)也计入"可回收"，虚高——VACUUM 只回收 WAL 与库内碎片，不回收有效数据。现每项新增 `reclaimable_bytes`（delete=可删量、vacuum=WAL 量、rebuild=主库量），总量只累加它，数字才真实。
- **`--clean` 预估一致化**：清理模式的 estimated 也改用 `reclaimable_bytes`，与扫描口径统一，"预估 vs 实际"才可比。
- **扫描结果按可回收量从大到小排序**，最大头一眼可见，便于取舍。
- **消除一次冗余目录遍历**：deletable 目录的大小与年龄统计合并到单次 walk，大缓存树下扫描略快。

### 验证
- 自测（CODEX_HOME 指向临时目录，不碰真实数据）：`--age 7` 可回收=150KB（仅老文件）、无年龄过滤=200KB（含新文件）、排序降序、`--clean --yes --age 7` 精确释放 150KB 且新文件保留、`--age -1` 退出码 2。全部通过。

### 发布状态
- 版本号升 v1.2.1（PATCH）；脚本 `VERSION` 与 Release 一致。


---

## 2026-09-05 — 文档双语化 + 注释精简 + opencode 列入迭代（无版本迭代）

**范围**：不加新功能、不升版本、不发 Release。仅文档 / 注释 / issue 规划。

### 1. opencode 兼容提上日程（Issue #11 / #12，Milestone v1.3.0）

路径全部从 `anomalyco/opencode` 源码核实，未凭印象编写：

- `packages/core/src/global.ts`：经 `xdg-basedir` 解析 —— `data = $XDG_DATA_HOME/opencode`、
  `log = <data>/log`、`repos = <data>/repos`、`cache = $XDG_CACHE_HOME/opencode`、
  `bin = <cache>/bin`、`tmp = os.tmpdir()/opencode`。
- `packages/core/src/database/database.ts` 与 `drizzle.config.ts`：数据库为 `<data>/opencode.db`，
  且显式执行 `PRAGMA journal_mode = WAL` —— 因此存在 `-wal` / `-shm` 文件，
  正好命中本工具已有的 VACUUM + WAL checkpoint 能力。

- **#12** 负责 opencode 的清理目标与保护清单（`repos/` 是用户克隆的仓库、`config/` 含配置与凭证，必须保护）。
- **#11** 负责把清理目标重构为「按 agent 组织的注册表」，避免为第二个、第三个 agent 复制扫描/清理逻辑。

### 2. 代码注释精简并统一英文

注释原本就已是英文，本次核心是**精简**：

- 模块 docstring 25 行 → 11 行；`_pre_scan_lang` / `_age_stats` / `vacuum_db` 的多行 docstring 压成一行（或两行）。
- 分隔横幅（`# ---- i18n ----`）改为短标记（`# i18n`）。
- 文件 627 → 606 行；校验通过：注释中无 CJK 残留、无超长注释行、关键逻辑 token 未丢失。
- 自测 **10/10 通过**：年龄过滤（100KB 老文件计入、50KB 新文件不计入）、可回收量降序、
  `--clean` 精确释放 100KB 且新文件保留、保护清单存在、VACUUM 实测回收 2.0MB、
  `--age -1` 退出码 2、`--help --lang zh` 本地化。确认纯注释改动无行为影响。

### 3. 文档双语化

约定：**无后缀 `.md` = 英文主版，`.zh-CN.md` = 中文版**，两份互相链接。

- 新增 `SKILL.zh-CN.md`（原 SKILL.md 中文内容迁出），`SKILL.md` 改写为英文版
  （frontmatter `description` 保留中英双语触发词，不影响 Codex 触发）。
- 新增 `CONTRIBUTING.zh-CN.md`；英文 `CONTRIBUTING.md` 增加语言切换行。
- 两份 README 的路线图同步补入 opencode / 多 agent 注册表，并互链双语文档。
- 仓库 About 描述改为中英双语，补充 10 个 topics。
- **Project #3 看板 README 首次写入**（此前为空），中英双段：版本规则、里程碑表、安全契约。

### 4. 踩坑记录

- Windows 版 Python 不认 Git Bash 的 `/tmp` 路径，用 `CODEX_HOME=/tmp/xxx` 做冒烟测试会
  静默扫到空目录（全部 0 B，看起来"通过"实则没测到）。测试必须用 Windows 路径
  （如 `C:/Users/.../Temp/...`）或在 Python 内用 `tempfile.mkdtemp()` 建目录。
- 正则替换里若写 `r'...\n...'`（raw string 中的双反斜杠），匹配的是字面 `
` 文本而非换行，
  会静默失配；匹配跨行文本应直接用 `
` 或 `.*?` + `re.S`，并配 `assert` 计数。

### 5. 发布状态

本次为纯文档/注释/规划改动，**未升版本号、未发 Release**；main 上脚本 `VERSION` 仍为 `1.2.1`。
