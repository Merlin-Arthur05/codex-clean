# codex-clean

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)]()
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

[English](README.md) | 简体中文

**一个"先确认再清理"的安全工具：只回收 Codex 自身的缓存、日志和 WAL 文件占用的磁盘空间，绝不碰你的对话记录、配置和项目文件。**

`codex-clean` 只针对 `~/.codex` 内部**可再生的、Codex 自己产生**的数据：插件的临时下载、插件缓存、诊断日志库 `logs_2.sqlite` 及其预写日志（WAL），以及通过 `VACUUM` 回收的状态库空洞。对话历史、状态数据、登录凭证、配置文件和 Codex 可执行文件**一律不碰**。

> 同时打包为 [Codex Agent Skill](#安装为-codex-技能)（提供[英文](SKILL.md)与[简体中文](SKILL.zh-CN.md)两版）：在 Codex 里说一句"清理 Codex 缓存"，它会自动扫描 → 向你确认 → 再清理。

---

## 与"通用电脑清理"工具的区别

`codex-clean` **不是**磁盘清理器，也不整理文件。市面上（以及本机可能已装的 `qing-li-dian-nao` 之类）通用清理技能，扫的是**整台电脑**的缓存/大文件/重复文件；本工具只处理 **Codex 一个应用的运行时数据**，并且具备通用工具没有的能力：

| 维度 | codex-clean | 通用电脑清理 |
|---|---|---|
| 清理对象 | 仅 Codex 自身 `~/.codex` | 整台电脑的磁盘/文件 |
| 独有能力 | SQLite **VACUUM + WAL checkpoint**、超大日志库备份重建 | 通用文件扫描 |
| 输出语言 | 中英双语，随客户端语言自动切换 | 单一语言 |
| 触发时机 | "Codex 缓存/日志/占空间" | "清理电脑/整理文件/C盘满了" |

## 为什么需要它

Codex（CLI / 桌面版）在 `~/.codex` 下有几样东西会无上限增长：

| 项目 | 作用 | 增长情况 |
|---|---|---|
| `~/.codex/.tmp` | 插件/市场的临时下载与解压 | 数百 MB |
| `~/.codex/plugins/cache` | 插件缓存（可重新下载） | 取决于装的插件 |
| `~/.codex/logs_2.sqlite` | 诊断日志库（**不是**对话历史） | 反馈中可达数 GB；WAL 还会带来 SSD 写放大 |

`logs_2.sqlite` 只存诊断日志——删除或重建它**不会影响你的聊天记录**（聊天记录在 `state_5.sqlite` / `sessions/`），这就是清理它安全的原因。

## 可清理项（严格白名单）

**A. 删除类（可再生，Codex 按需重建）**

| 项 | 路径 |
|---|---|
| `tmp` | `~/.codex/.tmp` |
| `tmp2` | `~/.codex/tmp` |
| `plugin-cache` | `~/.codex/plugins/cache` |

**B. VACUUM + WAL 清理（保留数据，只回收空间）**——对以下库执行 `PRAGMA wal_checkpoint(TRUNCATE)` + `VACUUM`：

`logs_2.sqlite` · `state_5.sqlite` · `thread_history_1.sqlite` · `queue_1.sqlite` · `goals_1.sqlite` · `memories_1.sqlite`

**C. 重建超大日志库（可选）**——当 `logs_2.sqlite` 超过 100 MB 时，先备份再让 Codex 重建空库。

## 绝不触碰

- Codex 可执行文件与运行时：`bin/`、`runtimes/`
- 对话历史：`sessions/`
- 状态/记忆/目标库**内部的数据**（只 VACUUM，绝不删除）
- 配置：`config.toml`、`auth.json`、`model-catalogs/`、`backups/`
- 你的项目文件与工作目录

## 安装

```bash
git clone https://github.com/Merlin-Arthur05/codex-clean.git
cd codex-clean
python scripts/codex_clean.py --scan
```

纯 Python 3.8+ 标准库实现，零依赖。

## 用法

```bash
# 1. 只读扫描（默认，安全）——列出可回收项及大小
python scripts/codex_clean.py --scan

# 2. 交互清理：逐项确认后才执行
python scripts/codex_clean.py --clean

# 3. 非交互：清理所有安全项
python scripts/codex_clean.py --clean --yes

# 4. 推荐全量清理：连 SQLite 库一起 VACUUM
python scripts/codex_clean.py --clean --yes --vacuum

# 5. 顺带重建超大日志库（>100MB，会先备份）
python scripts/codex_clean.py --clean --yes --rebuild-logs

# 6. 只清理 7 天前遗留的临时文件（保留近期文件，避免误删正在用的缓存）
python scripts/codex_clean.py --scan --age 7
python scripts/codex_clean.py --clean --yes --age 7

# 7. 机器可读输出（含每项的"将要执行什么"预览）
python scripts/codex_clean.py --scan --json

# 8. JSON 清理报告（预估释放 vs 实际释放）
python scripts/codex_clean.py --clean --yes --vacuum --json

# 9. 指定输出语言：en | zh | auto（默认自动）
python scripts/codex_clean.py --scan --lang zh
```

### `--age N` 按文件年龄过滤

加上 `--age N` 后，删除类项目**只处理修改时间在 N 天之前的文件**，较新的文件保留不动。适合不想清空整个缓存、只想清掉长期堆积垃圾的场景，也避免误删 Codex 正在使用的近期缓存。

- 扫描时：`size` 显示的是**符合条件的**（即可回收的）大小，`total_size` 显示目录总大小
- 清理时：只删除够老的文件，并顺带清掉因此变空的目录
- 只对删除类生效；VACUUM / 重建类不受影响（它们只收缩已有数据库，不涉及文件新旧）

### `--json` 输出格式

**扫描模式**（`--scan --json`）返回数组，每项在 `name`/`kind`/`size` 等稳定字段之外，新增 v1.2.0 的预览字段：

```jsonc
{
  "name": "tmp", "kind": "delete", "path": "...", "size": "200.0 KB",
  "age_filter_days": 7,
  "eligible_bytes": 204800, "eligible_files": 1, "total_files": 2,
  "total_size": "230.0 KB",
  "planned_action": {
    "type": "delete", "target": "...",
    "reclaimable_bytes": 204800, "reclaimable": "200.0 KB",
    "reversible": false, "confirm_required": true, "age_filter_days": 7
  },
  "safe": true
}
```

**清理模式**（`--clean --yes --json`）返回报告对象，核心是**预估 vs 实际**的对比：

```jsonc
{
  "ok": true, "dry_run": false, "version": "1.2.0",
  "estimated_bytes": 215040, "actual_freed_bytes": 204800, "delta_bytes": -10240,
  "items": [
    { "name": "tmp", "kind": "delete", "status": "ok",
      "estimated_bytes": 204800, "actual_bytes": 204800, "message": "..." }
  ],
  "protected_untouched": ["sessions", "config.toml", "auth.json", "..."]
}
```

> `--clean --json` 必须与 `--yes` 同用（JSON 模式无法交互确认）。

VACUUM 的 `actual_bytes` 是**实测收缩量**（`VACUUM` 前后主库 + WAL + SHM 的体积差），不是估算——所以你看到的差值就是真实收益与预估的偏差。

### 输出语言

面向用户的文本（扫描列表、确认提示、结果、命令行帮助）均已本地化。解析顺序：
`--lang` 参数 → `CODEX_CLEAN_LANG` 环境变量 → `LANG`/`LC_ALL` → 操作系统 UI 语言 → 英文。

因此在中文客户端里直接 `CODEX_CLEAN_LANG=zh` 或 `--lang zh` 即可；英文环境默认英文。

> **最佳实践**：执行 `--clean` 前**完全退出 Codex**（CLI、桌面版、IDE 扩展），避免进程仍持有被删文件的句柄——否则磁盘空间要等进程退出后才真正释放。

## 安装为 Codex 技能

```bash
mkdir -p ~/.codex/skills/codex-clean
cp SKILL.zh-CN.md ~/.codex/skills/codex-clean/   # 或 SKILL.md 英文版
cp -r scripts ~/.codex/skills/codex-clean/
```

之后在 Codex 里直接说：**"清理 Codex 缓存"** / **"Codex 日志太多"** / **"Codex 占空间"** / **"clean Codex cache"** ——它会读取本技能、扫描，并在清理前与你确认。

## 路线图

- WAL 增长看护（定期扫描提醒）。
- 可选的 Windows 计划任务自集成（严格 opt-in）。
- `--exclude` 跳过指定数据库。
- **多 agent 支持**——把清理目标扩展到其他 AI 编程 CLI，套用同一套"扫描-确认-清理 + 保护清单"规则：
  - **pi**（[@earendil-works/pi-coding-agent](https://www.npmjs.com/package/@earendil-works/pi-coding-agent)）
    ——探测其数据/缓存/日志目录（如 `~/.pi`）。见 [#10](https://github.com/Merlin-Arthur05/codex-clean/issues/10)。
  - **opencode**（[anomalyco/opencode](https://github.com/anomalyco/opencode)）——其 XDG
    数据/日志/缓存目录，以及 WAL 模式的 `opencode.db`（Linux 下为
    `~/.local/share/opencode/opencode.db`）。见 [#12](https://github.com/Merlin-Arthur05/codex-clean/issues/12)。
  - 把清理目标重构为**按 agent 组织的注册表**，新增 agent 只需加一条规格。见
    [#11](https://github.com/Merlin-Arthur05/codex-clean/issues/11)。

以上均跟踪于 [项目看板](https://github.com/users/Merlin-Arthur05/projects/3)。

## 许可

[MIT](LICENSE) © Merlin-Arthur05

## 贡献

见 [CONTRIBUTING.md](CONTRIBUTING.zh-CN.md)（[English](CONTRIBUTING.md)）。欢迎 PR——但安全契约是硬红线：不引入破坏性默认值、受保护项必须始终受保护、只用标准库。
