# 贡献指南（简体中文）

[English](CONTRIBUTING.md) | 简体中文

感谢你的关注！这是一个小而专注的工具——以下是既能帮上忙、又不破坏其安全设计的参与方式。

## 底线原则

`codex-clean` 的全部意义在于**安全**：它只触碰 Codex 自身可再生缓存/日志文件的严格白名单，绝不自动删除对话历史、状态数据库、配置或用户项目文件。

任何贡献都必须维持这条契约：

- **不引入新的破坏性默认值。** 新增清理目标必须明确可再生，且必须保持 opt-in / 执行前确认。
- **受保护项必须始终受保护。** `sessions/`、`state_*`、`thread_history_*`、`memories_*`、`goals_*`、`auth.json`、`config.toml`、`bin`、`runtimes` 一律不碰。
- **只用标准库。** `codex_clean.py` 目前零第三方依赖——请保持（它应当能在任何有 Python 的地方跑起来）。

## 工作流

1. Fork 仓库并创建特性分支。
2. 做出你的改动。
3. 新增/调整测试：用 `CODEX_HOME` 环境变量覆盖（脚本已支持）指向一个临时目录测试——**绝不要**拿真实的 `~/.codex` 测。
4. 对临时目录运行 `--scan`，确认改动生效。
5. 提交 PR，说明改了什么、以及为什么它是安全的。

## 代码风格

- 兼容 Python 3.8+。
- 函数保持短小并有文档说明。
- 注释与文档字符串使用英文。
- `--json` 输出必须保持稳定——可能有工具在解析它。

## 测试

```powershell
# 建一个一次性的假 CODEX_HOME 并针对它测试
$env:CODEX_HOME = "$env:TEMP\codex-clean-test"
python scripts/codex_clean.py --scan
python scripts/codex_clean.py --clean --yes --vacuum
```

测完删除临时目录。测试期间**绝不要**对真实的 `~/.codex` 执行 `--clean`。

## 疑问

非琐碎的改动请先开 issue 对齐思路，避免白费功夫。
