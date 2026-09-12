# codex-clean

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)]()
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

**一个"先确认再清理"的安全工具：回收 AI 编程 Agent 自身的缓存、日志和 WAL 文件占用的磁盘空间。支持 OpenAI Codex、Claude Code 与 Pi。绝不碰你的对话记录、配置和项目文件。**

[English](README.md) | 简体中文

`codex-clean` 只针对每个 Agent 家目录内部**可再生的、Agent 自己产生**的数据：临时下载、缓存、诊断日志及其预写日志（WAL），以及通过 `VACUUM` 回收的状态库空洞。对话历史、状态数据、登录凭证、配置文件和 Agent 可执行文件**一律不碰**。

| Agent | 家目录 | 选择方式 |
|---|---|---|
| **OpenAI Codex**（默认） | `~/.codex`（`CODEX_HOME`） | *（默认）* |
| **Claude Code** | `~/.claude`（`CLAUDE_HOME`） | `--target claude-code` |
| **Pi** | `~/.pi/agent`（`PI_AGENT_HOME`） | `--target pi` |
| *以上全部* | — | `--target all` |

每个 Agent 的家目录都在运行时由其环境变量解析，缺失时回落到默认路径——没有任何一处硬编码到某台机器。

> 同时打包为 [Agent Skill](#安装为技能)（提供[英文](SKILL.md)与[简体中文](SKILL.zh-CN.md)两版），Codex / Claude Code / Pi 通用：说一句"清理 agent 缓存"，它会自动扫描 → 向你确认 → 再清理。

---

## 支持的 Agent

`codex-clean` 当前支持 **三个 Agent**，每个都复用同一套"扫描 -> 确认 -> 清理"流程与保护清单安全契约。新增一个 Agent 只需在 `AGENTS` 注册表里加一条记录——差异是**数据而非分支**。

| Agent | 状态 | 清理内容 |
|---|---|---|
| **OpenAI Codex** | 已支持 | `~/.codex` 临时文件、插件缓存、日志、WAL、状态库空洞 |
| **Claude Code** | 已支持 | `~/.claude` 缓存、调试日志、shell-snapshots、statsig |
| **Pi** | 已支持 | `~/.pi/agent` 缓存、临时文件、日志、调试日志 |
| **opencode** | 规划中 - v1.5.0（[#12](https://github.com/Merlin-Arthur05/codex-clean/issues/12)） | XDG 数据 / 日志 / 缓存 + WAL 模式的 `opencode.db` |

## 与"通用电脑清理"工具的区别

`codex-clean` **不是**磁盘清理器，也不整理文件。市面上（以及本机可能已装的 `qing-li-dian-nao` 之类）通用清理技能，扫的是**整台电脑**的缓存/大文件/重复文件；本工具只处理 **AI 编程 Agent 的运行时数据**，并且具备通用工具没有的能力：

| 维度 | codex-clean | 通用电脑清理 |
|---|---|---|
| 清理对象 | 仅已注册 Agent 自己的家目录（`~/.codex`、`~/.claude`、`~/.pi/agent`） | 整台电脑的磁盘/文件 |
| 独有能力 | SQLite **VACUUM + WAL checkpoint**、超大日志库备份重建 | 通用文件扫描 |
| 输出语言 | 中英双语，随客户端语言自动切换 | 单一语言 |
| 触发时机 | "Codex / Claude Code / Pi 的缓存/日志/占空间" | "清理电脑/整理文件/C盘满了" |

## 为什么需要它

AI 编程 Agent 的家目录里会不断堆积可再生数据。以 Codex（CLI / 桌面版）为例，`~/.codex` 下：

| 项目 | 作用 | 增长情况 |
|---|---|---|
| `~/.codex/.tmp` | 插件/市场的临时下载与解压 | 数百 MB |
| `~/.codex/plugins/cache` | 插件缓存（可重新下载） | 取决于装的插件 |
| `~/.codex/logs_2.sqlite` | 诊断日志库（**不是**对话历史） | 反馈中可达数 GB；WAL 还会带来 SSD 写放大 |

`logs_2.sqlite` 只存诊断日志——删除或重建它**不会影响你的聊天记录**（聊天记录在 `state_5.sqlite` / `sessions/`），这就是清理它安全的原因。同一个原则适用于所有 Agent：只有可再生数据才会进入清理范围。

## 可清理项

以下内容都位于所选 Agent 的家目录内；未列出的项一律受保护。

| Agent | 删除类（可再生） | VACUUM + WAL | 重建日志库 |
|---|---|---|---|
| **Codex** | `.tmp/`、`tmp/`、`plugins/cache/` | 6 个已知 SQLite 库 | 支持，`logs_2.sqlite` > 100 MB 时 |
| **Claude Code** | `cache/`、`debug/`、`shell-snapshots/`、`statsig/` | 自动发现 | 不适用 |
| **Pi** | `cache/`、`tmp/`、`logs/`、`pi-debug.log` | 自动发现 | 不适用 |

- **VACUUM** 执行 `PRAGMA wal_checkpoint(TRUNCATE)` + `VACUUM`：保留数据，只回收空间。
- **自动发现**指扫描时用通配符在 Agent 家目录下查找 `*.sqlite` / `*.sqlite3` / `*.db`，而不是依赖硬编码清单。若某 Agent 没有数据库，该参数会提示"不适用"而非报错。
- Codex 的 `logs_2.sqlite` **只存诊断日志**——重建它绝不会影响聊天记录（聊天记录在 `state_5.sqlite` / `sessions/`）。

## 绝不触碰

各 Agent 由注册表强制维护的保护清单：

- **Codex** —— `bin/`、`runtimes/`、`sessions/`、`config.toml`、`auth.json`、`skills/`、`rules/`、`model-catalogs/`、`backups/`
- **Claude Code** —— `projects/`（你的对话）、`memory/`、`plugins/`、`skills/`、`settings.json`、`config.json`、`sessions/`、`ide/`、`history.jsonl`
- **Pi** —— `sessions/`（对话）、`skills/`、`npm/`（**用户已安装的包**）、`git/`、`bin/`、`tools/`、`prompts/`、`themes/`、`settings.json`、`trust.json`、`auth.json`、`models.json`、`AGENTS.md`、`SYSTEM.md`
- **所有 Agent** —— 状态库**内部的数据**（只 VACUUM，绝不删除），以及你的项目文件与工作目录

### 已知限制

以下是这些 Agent 自身的客观约束，经核实确认，并非本工具的能力缺失。

- **`--rebuild-logs`（Claude Code、Pi）** —— 不适用。两者都没有"超大诊断日志库"这一概念；它们的日志是普通文件（Claude 为 `debug/`，Pi 为 `logs/` 与 `pi-debug.log`），已在删除白名单中。该参数会打印"不适用"提示，而不是报错。
- **`--vacuum`（Claude Code、Pi）** —— **并非**被硬编码为不支持。两者都不声明固定的库清单，而是由扫描时自动发现（见上）。当前核实：`~/.claude` 下为 0 个此类文件，因此参数提示"不适用"；若将来版本引入数据库，VACUUM 会**自动生效，无需改代码**。
- **Pi 的可清理项是"尽力而为"**。Pi 源码只记载了 `~/.pi/agent` 下的用户数据（`sessions/`、`skills/`、`npm/` 为用户安装包、`extensions/` 以及配置文件）。`cache/` / `tmp/` / `logs/` 因其普遍可再生而纳入，且**仅当实际存在时**才会处理；保护清单确保用户数据绝不会被碰。

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

# 6. 只清理 7 天前遗留的临时文件（保留近期文件）
python scripts/codex_clean.py --scan --age 7

# 7. 指定 Agent（Codex 为默认）
python scripts/codex_clean.py --scan --target claude-code
python scripts/codex_clean.py --scan --target pi

# 8. 一次巡检所有 Agent
python scripts/codex_clean.py --scan --target all

# 9. 机器可读输出（含每项的"将要执行什么"预览）
python scripts/codex_clean.py --scan --json

# 10. 指定输出语言：en | zh | auto（默认自动）
python scripts/codex_clean.py --scan --lang zh

# 11. 跳过或只保留指定项（项名或 agent:项名，逗号分隔）
python scripts/codex_clean.py --scan --target all --exclude "state-db,pi-cache"
python scripts/codex_clean.py --scan --target all --only claude-cache

# 12. 预演清理，不做任何改动
python scripts/codex_clean.py --clean --dry-run --target codex

# 13. 查看支持的 Agent 及其能力
python scripts/codex_clean.py --list-targets

# 14. 自动化：可回收达到 500 MB 时以退出码 3 返回
python scripts/codex_clean.py --scan --check 500
```

### `--age N` 按文件年龄过滤

加上 `--age N` 后，删除类项目**只处理修改时间在 N 天之前的文件**，较新的文件保留不动。适合不想清空整个缓存、只想清掉长期堆积垃圾的场景，也避免误删 Agent 正在使用的近期缓存。

- 扫描时：`size` 显示的是**符合条件的**（即可回收的）大小，`total_size` 显示目录总大小
- 清理时：只删除够老的文件，并顺带清掉因此变空的目录
- 只对删除类生效；VACUUM / 重建类不受影响（它们只收缩已有数据库，不涉及文件新旧）

### `--json` 输出格式

**扫描模式**（`--scan --json`）返回数组，每项在 `name`/`kind`/`size` 等稳定字段之外，附带将执行动作的预览：

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
  "ok": true, "dry_run": false, "version": "1.6.0",
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
`--json` 输出保留稳定的 `name`/`kind` 键供机器解析，仅 `desc`/`action` 字段随语言本地化。

> **最佳实践**：执行 `--clean` 前**完全退出目标 Agent**，避免进程仍持有被删文件的句柄——否则磁盘空间要等进程退出后才真正释放。

## 安装为技能

`codex-clean` 只提供一份 `SKILL.md`，遵循 **Agent Skills 开放标准**，因此同一份主体可用于 Codex、Claude Code 与 Pi，只有安装路径与 frontmatter 不同：

| Agent | 安装路径 | 调用方式 |
|---|---|---|
| **Codex** | `~/.codex/skills/codex-clean/` | 说"清理 Codex 缓存" |
| **Claude Code** | `~/.claude/skills/codex-clean/` | **`/codex-clean`** |
| **Pi** | `~/.pi/agent/skills/codex-clean/` | 说"清理 agent 缓存" |

```bash
# Codex
mkdir -p ~/.codex/skills/codex-clean
cp SKILL.zh-CN.md ~/.codex/skills/codex-clean/   # 或 SKILL.md 英文版
cp -r scripts ~/.codex/skills/codex-clean/

# Claude Code —— 目录名即斜杠命令
mkdir -p ~/.claude/skills/codex-clean
cp SKILL.zh-CN.md ~/.claude/skills/codex-clean/  # frontmatter 加 `allowed-tools: Bash, Read`
cp -r scripts ~/.claude/skills/codex-clean/

# Pi
mkdir -p ~/.pi/agent/skills/codex-clean
cp SKILL.zh-CN.md ~/.pi/agent/skills/codex-clean/
cp -r scripts ~/.pi/agent/skills/codex-clean/
```

之后直接开口即可——Agent 会读取本技能、扫描，并在清理前与你确认。

## 安装为 Pi 包

本仓库同时是一个 Pi 包（`package.json` 中带 `pi` 清单），因此 Pi 还能获得原生工具与斜杠命令，而不只是技能：

```bash
pi install git:github.com/Merlin-Arthur05/codex-clean
```

将注册：

- **工具** —— `agent_cache_scan`、`agent_cache_clean`、`agent_cache_targets`
- **命令** —— `/clean-agents`（扫描 → 确认 → 清理）

该扩展是一层薄封装，实际调用同一个 Python 脚本，因此在各 Agent 中行为完全一致。它会在运行时探测 `python3` / `py -3` / `python`，绝不假定固定的解释器路径。

## 路线图

- WAL 增长看护（定期扫描提醒）。
- 可选的 Windows 计划任务自集成（严格 opt-in）。
- **opencode**（[anomalyco/opencode](https://github.com/anomalyco/opencode)）——其 XDG 数据/日志/缓存目录，以及 WAL 模式的 `opencode.db`。见 [#12](https://github.com/Merlin-Arthur05/codex-clean/issues/12)。
- Claude Code `projects/` 对话 JSONL 的 **opt-in** 按年龄清理（显式开关 + 逐项确认，绝不默认开启）。
- 运行时进程检测：目标 Agent 仍在运行时给出提醒（[#8](https://github.com/Merlin-Arthur05/codex-clean/issues/8)）。

以上均跟踪于 [项目看板](https://github.com/users/Merlin-Arthur05/projects/3)。

## 过滤、预演与自动化

| 参数 | 作用 |
|---|---|
| `--target all` | 一次巡检全部已注册的 agent |
| `--exclude LIST` | 按 `项名` 或 `agent:项名` 跳过（逗号分隔） |
| `--only LIST` | 只保留列出的项（`--exclude` 的反义） |
| `--dry-run` | 打印 `--clean` 将要执行的计划，不做任何改动 |
| `--list-targets` | 打印支持的 agent、其数据目录与能力 |
| `--check N` | 可回收空间达到 N MB 时以退出码 **3** 返回（0=关闭） |

说明：

- 过滤只能**收窄**白名单。受保护项从来不在扫描结果里，因此任何模式都无法把它"放回"。
- `--dry-run` 复用 `--json` 扫描输出中已有的 `planned_action` 数据，
  所以预演与真实执行描述的是同一批动作。
- 退出码：`0` 正常，`2` 参数错误，`3` 可回收量达到 `--check` 阈值。

## 测试

```bash
python tests/test_codex_clean.py          # 68 项回归检查，仅用标准库
node   tests/test_pi_extension.mjs        # Pi 扩展加载测试（未装 Pi 时自动跳过）
```

Python 测试通过把各 Agent 的家目录环境变量指向临时目录，永远不会触碰真实的 agent 数据。

## 许可

[MIT](LICENSE) © Merlin-Arthur05

## 贡献

见 [CONTRIBUTING.md](CONTRIBUTING.zh-CN.md)（[English](CONTRIBUTING.md)）。欢迎 PR——但安全契约是硬红线：不引入破坏性默认值、受保护项必须始终受保护、只用标准库。
