---
name: codex-clean
description: "清理 Codex 自身的对话/工作缓存、日志和临时文件，释放磁盘空间、处理 WAL 膨胀时使用。触发词：清理Codex缓存、Codex日志太多、Codex占空间、清理Codex临时文件、codex cache clean、codex log clean、codex SSD占用。默认只读扫描出可安全清理项并给出大小，用户逐项确认后才执行；只清理 Codex 自身可再生缓存/日志(.tmp、plugins/cache)、对日志/状态数据库执行 VACUUM 收缩与 WAL 清理，绝不触碰 Codex 可执行文件、对话历史、状态数据、配置文件、工作项目文件。"
---

# Codex 缓存与日志完整清理

清理 Codex（~/.codex）自身产生的、可安全重建或收缩的缓存、日志、WAL 文件，释放磁盘空间。

## 核心契约

- **只针对 Codex 自己**，不清理用户的电脑文件、不清理其他工具。
- **先扫描、后清理**。默认调用扫描模式列出可处理项、各占多少空间，列给用户，**逐项确认**后才执行对应清理。
- **绝不清理/绝不删数据**（保护清单）：
  - Codex 可执行文件与运行时：`%LOCALAPPDATA%\OpenAI\Codex\bin`、`runtimes`
  - 对话历史：`~/.codex/sessions\`
  - 状态 / 记忆 / 目标：`state_5.sqlite`、`thread_history_1.sqlite`、`memories_1.sqlite`、`goals_1.sqlite`、`queue_1.sqlite`（这些库**只做 VACUUM/WAL 清理，绝不删库内数据**）
  - 配置：`config.toml`、`auth.json`、`model-catalogs\`、`backups\`
  - 用户的任何项目工作目录

## 可处理项（分两类）

**A. 纯删除（可再生，删除后 Codex 按需重建）**
| 项 | 路径 | 说明 |
|---|---|---|
| tmp | `~/.codex/.tmp` | 插件/市场临时下载解压缓存 |
| tmp2 | `~/.codex/tmp` | Codex 临时目录 |
| plugin-cache | `~/.codex/plugins/cache` | 插件缓存，可重新拉取 |

**B. 数据库 VACUUM + WAL 清理（保留数据，只收缩空间）**
对以下库执行 `PRAGMA wal_checkpoint(TRUNCATE)` + `VACUUM`：
`logs_2.sqlite`(日志)、`state_5.sqlite`、`thread_history_1.sqlite`、`queue_1.sqlite`、`goals_1.sqlite`、`memories_1.sqlite`

> logs_2.sqlite 只含诊断日志（不含会话历史，会话在 state/sessions）。若它异常膨胀（>100MB），可额外选择"备份后重建空库"彻底释放（Codex 下次启动自动重建）。state/threads/goals/memories 等**绝不删库**，只 vacuum。

## 调用脚本

用当前环境可用 Python 执行 skill 目录下的 `scripts/codex_clean.py`：

```powershell
python "<skill>\scripts\codex_clean.py" --scan
```

- `--scan`：只读扫描（安全，默认）
- `--clean`：进入逐项确认模式（交互选择要清理的项）
- `--clean --yes`：跳过交互，清理全部"纯删除 + WAL"安全项
- `--clean --yes --vacuum`：额外对数据库执行 VACUUM（推荐完整清理用这个）
- `--clean --yes --rebuild-logs`：额外允许重建超大日志库（>100MB 时建议，先备份）
- `--json`：结构化输出

## 执行规则

1. 先跑 `--scan`，把结果以清单形式呈现给用户（含每项大小、类别 delete/vacuum/rebuild）。
2. 用户逐项确认后再执行。
   - 纯删除项（tmp/plugins-cache）用户确认即可删。
   - VACUUM 项需说明"保留数据只收缩"，一般推荐允许。
   - logs 库重建需特别说明"会备份原库"，用户单独确认。
3. 执行后复扫报告释放量、失败项、残余风险。
4. 若用户提出要清"对话历史/状态数据"，明确告知那不属于缓存清理、删除会丢会话；必须用户单独、明确、逐项确认才考虑清 `sessions` 或对应库——默认绝不纳入自动清理。
