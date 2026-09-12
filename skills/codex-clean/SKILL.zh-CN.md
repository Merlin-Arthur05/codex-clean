---
name: codex-clean
allowed-tools: Bash, Read
description: "面向 AI 编程 agent 的运行时缓存/日志清理——只针对 agent 自身产生的可再生数据(~/.codex、~/.claude、~/.pi/agent)，与通用电脑清理(qing-li-dian-nao)完全不同：不清电脑磁盘、不整理文件、不扫项目目录。适用场景：编程 agent 磁盘占用膨胀、日志/临时文件过多、logs_2.sqlite 及 WAL 巨大、SSD 写入量大时使用。触发词：清理Codex缓存、Codex日志太多、Codex占空间、codex cache clean、codex log clean、codex SSD占用、clean up codex、清理Claude缓存、清理Pi缓存。独有能力：①对 Codex 的 SQLite 库执行 VACUUM + WAL checkpoint(TRUNCATE)——这是通用清理工具没有的、针对 Codex 日志库/WAL 膨胀的专用手段；②logs_2.sqlite(仅诊断日志、非会话)超过100MB可备份后重建；③输出支持中英双语随客户端语言切换(--lang/CODEX_CLEAN_LANG)；④纯标准库零依赖；⑤`--age N` 按文件年龄只清超过 N 天的过期临时文件(保留近期文件，避免误删正在使用的缓存)；⑥`--json` 输出含每项的 planned_action 预览，以及清理后“预估释放 vs 实际释放”对比；⑦一个 `--target` 参数即可选择 codex / claude-code / pi / all。安全边界：只删可重建缓存、只真空不删库内数据，绝不触碰会话历史(sessions)、state/记忆/目标库内容、auth.json/config.toml/settings.json、bin/runtimes 可执行文件、已安装的包及用户项目。默认先只读扫描列清单，逐项确认后才执行。"
---

# Agent 缓存与日志清理

[English](SKILL.md) | 简体中文

清理 AI 编程 agent 自身产生的、可安全重建或收缩的缓存、日志、WAL 文件，释放磁盘空间：

| Agent | 数据目录 | 选择方式 |
|---|---|---|
| **Codex**(默认) | `~/.codex`(`CODEX_HOME`) | 默认，或 `--target codex` |
| **Claude Code** | `~/.claude`(`CLAUDE_HOME`) | `--target claude-code` |
| **Pi** | `~/.pi/agent`(`PI_AGENT_HOME`) | `--target pi` |
| 以上全部 | — | `--target all` |

Codex 是主力目标、支持最深(SQLite VACUUM、日志库重建)。每个 agent 复用同一套
“扫描 → 确认 → 清理”流程与保护清单安全契约。

## 和通用清理技能（如 qing-li-dian-nao）的区别

| 维度 | 本技能 codex-clean | 通用电脑清理（qing-li-dian-nao 等） |
|---|---|---|
| 清理对象 | 只针对 **agent 应用自身** 家目录下的运行时数据 | 整台电脑：C 盘、下载/桌面/文档、大文件/重复文件 |
| 不碰 | 你的文件、项目目录、已安装的包 | agent 的会话/日志 DB 结构通常不在其清单内 |
| 独有能力 | **SQLite VACUUM + WAL checkpoint(TRUNCATE)** 处理 `logs_2.sqlite`/WAL 膨胀；超大日志库备份重建 | 通用磁盘扫描、Docker/WSL/浏览器缓存等 |
| 输出 | 中英双语，随客户端语言（`--lang`/`CODEX_CLEAN_LANG`） | 一般为单一语言 |
| 触发时机 | 用户明确说某个 agent 的缓存/日志/占用时才用；**不要**在“清电脑/C 盘/整理文件”场景误触发 | 用户说“清理电脑/整理文件/找大文件”时触发 |

> 一句话：**codex-clean 是编程 agent 的“自体清洁”，不是电脑管家**。若用户要求清理电脑/磁盘，应交给通用清理技能而非本技能。

## 核心契约

- **只针对指定 agent 自己**，不清理用户的电脑文件、不清理其他工具。
- **先扫描、后清理**。默认调用扫描模式列出可处理项、各占多少空间，列给用户，**逐项确认**后才执行对应清理。
- **绝不清理/绝不删数据**（保护清单）：
  - agent 可执行文件与运行时：`%LOCALAPPDATA%\OpenAI\Codex\bin`、`runtimes`
  - 对话历史：`~/.codex/sessions`、`~/.claude/projects`、`~/.pi/agent/sessions`
  - 状态 / 记忆 / 目标：`state_5.sqlite`、`thread_history_1.sqlite`、`memories_1.sqlite`、`goals_1.sqlite`、`queue_1.sqlite`（这些库**只做 VACUUM/WAL 清理，绝不删库内数据**）
  - 配置与凭证：`config.toml`、`auth.json`、`settings.json`、`trust.json`、`models.json`、`model-catalogs`、`backups`
  - 已安装内容：`skills/`、`plugins/`、`extensions/`、`~/.pi/agent/npm`（**用户已安装的包**）、`~/.pi/agent/git`
  - 用户的任何项目工作目录

## 可处理项

**A. 纯删除（可再生，agent 按需重建）**

| 项 | 路径 | 说明 |
|---|---|---|
| `tmp` | `~/.codex/.tmp` | 插件/市场临时下载解压缓存 |
| `tmp2` | `~/.codex/tmp` | Codex 临时目录 |
| `plugin-cache` | `~/.codex/plugins/cache` | 插件缓存，可重新拉取 |
| `claude-cache` | `~/.claude/cache` | Claude Code 可再生缓存 |
| `claude-debug` | `~/.claude/debug` | Claude Code 调试日志 |
| `claude-shell-snapshots` | `~/.claude/shell-snapshots` | Shell 快照 |
| `claude-statsig` | `~/.claude/statsig` | 遥测缓存 |
| `pi-tmp` | `~/.pi/agent/tmp` | Pi 临时目录（含 `tmp/extensions/<hash>` 包检出） |
| `pi-debug-log` | `~/.pi/agent/pi-debug.log` | Pi 调试日志 |
| `pi-cache`、`pi-logs` | `~/.pi/agent/{cache,logs}` | 尽力而为：仅当实际存在时处理 |

**B. 数据库 VACUUM + WAL 清理（保留数据，只收缩空间）**
Codex：对 `logs_2.sqlite`(日志)、`state_5.sqlite`、`thread_history_1.sqlite`、
`queue_1.sqlite`、`goals_1.sqlite`、`memories_1.sqlite` 执行
`PRAGMA wal_checkpoint(TRUNCATE)` + `VACUUM`。
Claude Code 与 Pi 不声明固定库清单：扫描时自动发现其家目录下的
`*.sqlite` / `*.sqlite3` / `*.db`，因此将来若出现数据库，VACUUM 会自动生效。

> logs_2.sqlite 只含诊断日志（不含会话历史，会话在 state/sessions）。若它异常膨胀（>100MB），可额外选择“备份后重建空库”彻底释放（Codex 下次启动自动重建）。state/threads/goals/memories 等**绝不删库**，只 vacuum。

## 调用脚本

用当前环境可用 Python 执行 skill 目录下的 `scripts/codex_clean.py`：

```powershell
python "<skill>\scripts\codex_clean.py" --scan
```

- `--scan`：只读扫描（安全，默认）
- `--clean`：进入逐项确认模式（交互选择要清理的项）
- `--clean --yes`：跳过交互，清理全部“纯删除 + WAL”安全项
- `--clean --yes --vacuum`：额外对数据库执行 VACUUM（推荐完整清理用这个）
- `--clean --yes --rebuild-logs`：额外允许重建超大日志库（>100MB 时建议，先备份；仅 Codex）
- `--target codex|claude-code|pi|all`：要清理哪个 agent 的数据（默认 `codex`）
- `--age N`：只处理**修改时间超过 N 天**的临时文件，较新的文件保留（只对删除类生效；`--scan --age 7` 可先预览）
- `--exclude LIST` / `--only LIST`：按 `项名` 或 `agent:项名` 跳过 / 只保留
- `--dry-run`：只显示 `--clean` 将要做什么，不做任何改动
- `--list-targets`：列出支持的 agent、其数据目录与能力
- `--check N`：可回收空间达到 N MB 时以退出码 **3** 返回（自动化）
- `--json`：结构化输出。扫描模式每项含 `planned_action`（将要执行的动作与可回收量）；清理模式（`--clean --yes --json`）输出 `estimated_bytes` / `actual_freed_bytes` / `delta_bytes` 的预估与实际对比，以及 `protected_untouched` 保护清单
- `--lang en|zh|auto`：输出语言（默认按客户端语言自动检测）

## 执行规则

1. 先跑 `--scan`，把结果以清单形式呈现给用户（含每项大小、类别 delete/vacuum/rebuild）。
   - 用户想一次巡检所有已装 agent 时用 `--target all`。
   - 若用户只想清“堆积的旧垃圾”而保留近期缓存，用 `--scan --age N`（如 N=7）先预览符合条件的量。
2. 用户逐项确认后再执行。
   - 纯删除项（tmp/plugins-cache）用户确认即可删。
   - VACUUM 项需说明“保留数据只收缩”，一般推荐允许。
   - logs 库重建需特别说明“会备份原库”，用户单独确认。
3. 执行后复扫报告释放量、失败项、残余风险。
4. 若用户提出要清“对话历史/状态数据”，明确告知那不属于缓存清理、删除会丢会话；必须用户单独、明确、逐项确认才考虑清 `sessions` 或对应库——默认绝不纳入自动清理。
