# Poker2

一个面向德州扑克 AI / 规则验证 / 回放分析的研究型工程仓库。它不是“只有一个训练脚本”的项目，而是一套带有契约、事件流、门禁、回放和批量评测能力的框架。

这个仓库的核心目标有 3 个：

- 让每次执行都可重放、可追溯、可验证。
- 让规则、哈希、门禁、评测口径保持单一真相。
- 让策略试验、批量对局、基线对比、故障定位都能落到结构化产物。

如果你是第一次接触这个项目，建议按本文的顺序操作：

1. 先安装依赖并跑 `doctor`。
2. 再跑一手 `run_hand`，确认本机环境正常。
3. 然后学会 `replay` 和 `stats`。
4. 最后再进入 `scrimmage` / `eval_full` / `loop`。

## 项目能力

- 单手运行：从 HRC `settings.json` 生成可回放 `EventStream`。
- 批量对局：按 `scenario/profile/policy/opponents` 跑多手评测。
- 回放定位：按 `hand_id` / `decision_id + state_hash` 精确回放。
- 统计与门禁：对 `EventStream` 和 golden fixtures 做一致性校验。
- 基线评测：支持 Tier-A / Tier-P / paired compare / pool eval / BR proxy。
- 自动化优化 loop：支持手动启动高级迭代工具链。

## 仓库结构

```text
poker2/
├── poker2/                  # 主 Python 包
│   ├── cli/                 # 命令行入口
│   ├── protocol/            # 契约对象、哈希、事件模型
│   ├── environment/         # 执行环境与账本
│   ├── runtime/             # 策略、注册表、运行时逻辑
│   ├── gates/               # 各类 Gate / Guard
│   └── engines/             # 求解器与可选 Rust/PyO3 绑定
├── specs/                   # scenario / policy / profile / opponents / ruleset
├── fixtures/                # 内置 golden fixtures 与 eventstream
├── tests/                   # pytest 测试集
├── tools/                   # loop、launchd、清理、辅助脚本
├── notes/                   # 迭代日志与评测协议
├── ARCHIETECTURE.md         # 架构规范唯一权威文档
└── AGENTS.md                # AI/工具协作约束
```

## Git / GitHub 发布建议

这个项目已经是一个 Git 仓库，不需要重新 `git init`。上传到 GitHub 前，建议按下面的边界管理内容。

### 应该提交到仓库的内容

- `poker2/`：核心源码
- `specs/`：scenario / policy / profile / opponents / ruleset / preflop 数据
- `fixtures/`：内置 golden fixtures、eventstream、pack
- `tests/`：自动化测试
- `tools/`：可复用脚本
- `notes/`：规范性笔记和评测协议
- `contractkit/`
- `README.md`、`ARCHIETECTURE.md`、`AGENTS.md`
- `pyproject.toml`、`requirements.txt`、`requirements-dev.txt`
- `.gitignore`、`.gitattributes`

### 不应该提交到仓库的内容

- `.venv/`、`venv/`、`env/`
- `tmp/`：运行时输出、loop 中间结果、实验临时文件
- `artifacts/`：本地构建和实验产物
- `worktrees/`：本地 worktree 副本
- `.pytest_cache/`、`.ruff_cache/`、`__pycache__/`、`.coverage*`
- `.pydeps/`：本地分析图/依赖图输出
- `target/`、`.cargo/`、`tools/.venv_maturin/`
- `.DS_Store`、`.idea/`、`.vscode/`

### 当前仓库已经做好的 Git 配置

- `.gitignore`：忽略本地环境、缓存、运行产物、Rust 构建目录
- `.gitattributes`：强制 `json/ndjson/sh/py/md` 使用 LF，避免跨平台换行问题

这样处理后，别人从 GitHub 拉下来时看到的是“源码 + 规范 + specs + fixtures + tests”，而不是你的本地环境和跑出来的临时产物。

## 环境要求

- Python `>= 3.11`
- macOS / Linux / WSL 均可，本文示例按 `zsh` 写
- 推荐使用虚拟环境

可选依赖：

- `rustc` / `cargo`
- `maturin`

只有在你要使用 postflop Rust / PyO3 绑定时，才需要 Rust 工具链。纯 Python 主链路可以先不装。

## 安装

### 1) 创建虚拟环境

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

### 2) 安装依赖

```bash
pip install -r requirements-dev.txt
pip install -e .
```

说明：

- `requirements.txt` 是运行时最小依赖。
- `requirements-dev.txt` 在最小依赖之上增加了 `pytest` 和 `pytest-cov`。
- `pip install -e .` 让你可以直接用 `python -m poker2.cli.xxx` 调用仓库代码。

## 先理解 2 套入口

这个项目最容易让新手混淆的地方，就是 `--settings` 和 `--scenario` 不是一回事。

### 入口 A：`--settings`

适合：

- 跑单手
- 从 HRC 风格配置直接生成事件流
- 验证 rake / rounding / reopen 这类规则口径

典型命令：

- `python -m poker2.cli.run_hand`
- `python -m poker2.cli.run_batch`
- `python -m poker2.cli.doctor options-hash-from-hrc`

### 入口 B：`--scenario`

适合：

- 跑真实评测
- 批量对局
- 基线比较
- 带 profile / policy / opponents 的完整实验

典型命令：

- `python -m poker2.cli.scrimmage`
- `python -m poker2.cli.scrimmage_batch`
- `python -m poker2.cli.eval_full`

结论：

- 想快速确认程序能跑，用 `--settings`。
- 想跑标准实验，不要只给 `scenario`，要把 `profile + policy + opponents` 一起给齐。

## 快速开始

### 步骤 1：先跑最小健康检查

```bash
python3 -m poker2.cli.doctor contractkit-vectors
```

期望结果：

- 输出 JSON
- `status=pass`

这一步是最便宜的 smoke test。它通过，说明 contract kit 的基础向量校验没坏。

### 步骤 2：跑一手牌，生成自己的 EventStream

```bash
python3 -m poker2.cli.run_hand \
  --settings specs/preflop/settings.json \
  --out tmp/readme_demo_hand.ndjson \
  --rounding-mode floor \
  --starting-stacks-by-seat '{"1":10000,"2":10000}' \
  --button-seat 1 \
  --no-reopen-on-short-allin
```

这条命令已经在当前仓库环境里验证通过。

执行成功后你会拿到：

- `tmp/readme_demo_hand.ndjson`
- 结构化 JSON 输出，包含 `event_stream_digest`、`run_id`、`scenario_id`、`options_hash`

注意：

- `specs/preflop/settings.json` 里 `eqmodel.raked=true`，所以必须显式给 `--rounding-mode`。
- `--starting-stacks-by-seat` 必须是合法 JSON 字符串。
- `--button-seat` 必须和玩家座位一致。

### 步骤 3：回放这手牌

```bash
python3 -m poker2.cli.replay \
  --eventstream tmp/readme_demo_hand.ndjson \
  --strict
```

如果你想定位某个决策点，可以再加：

```bash
--decision-id <id> --state-hash <hash>
```

规则：

- 只给 `--decision-id` 不够，必须同时给 `--state-hash`
- 这是为了保证定位是可重放、可唯一确认的

### 步骤 4：验证内置 golden fixtures

```bash
python3 -m poker2.cli.stats fixtures-pack \
  --pack fixtures/internal/internal_ruleset_v1_pack.json \
  --ruleset specs/rulesets/internal_ruleset_v1.json \
  --strict
```

这条命令也已在当前仓库环境里验证通过。

如果它通过，说明：

- fixture pack 结构没坏
- eventstream digest 一致
- 规则口径与 pack 绑定一致

## 新手最常用命令

| 目标 | 命令 | 说明 |
| --- | --- | --- |
| 最小健康检查 | `python3 -m poker2.cli.doctor contractkit-vectors` | 最推荐的第一条命令 |
| 单手生成事件流 | `python3 -m poker2.cli.run_hand ...` | 从 `settings.json` 跑一手牌 |
| 批量单手导出 | `python3 -m poker2.cli.run_batch ...` | 连续生成多手 `ndjson` |
| 回放事件流 | `python3 -m poker2.cli.replay --eventstream ...` | 看某手牌或某个决策点 |
| 检查 fixtures | `python3 -m poker2.cli.stats fixtures-pack ...` | 校验 golden fixtures |
| 检查单个事件流 | `python3 -m poker2.cli.stats eventstream ...` | 对单个 `ndjson` 跑统计/一致性 |
| 跑一轮评测 | `python3 -m poker2.cli.scrimmage ...` | 标准实验入口 |
| 跑完整评测矩阵 | `python3 -m poker2.cli.eval_full ...` | Tier-A / Tier-P / pool / BR |

## 标准评测示例

如果你想跑真正的实验，不要从 `pipeline eval` 开始。对新手来说，最稳妥的是直接用 `scrimmage`。

```bash
python3 -m poker2.cli.scrimmage \
  --scenario coinpoker_7max_mw_v3_actionspace_v2 \
  --profile internal_profile_v1 \
  --policy system_bot_policy_v3_retaliation_weight_v1 \
  --opponents system_bot_league_7max_frozen_v1 \
  --hands 20 \
  --seed 2000 \
  --artifact-mode lean \
  --quiet \
  --out-dir tmp/readme_scrimmage_demo
```

这条命令已经在当前仓库环境里验证通过。

执行成功后至少会生成：

- `tmp/readme_scrimmage_demo/scrimmage_report.json`

重要提醒：

- `scrimmage` 不是“只给一个 scenario 就能跑”的脚本。
- 对局手数太少时，可能因为 `iteration_protocol` 证据不足而 fail-fast。
- 如果你只是想确认环境通不通，先跑 `doctor` 和 `run_hand`，不要一上来就跑 `scrimmage`。

## 配置说明

### `scenario`

定义实验语义闭包，例如：

- 规则集
- action space
- preflop / postflop 引用
- 适用的 opponent suite / mw ladder / triad

示例文件：

- [specs/scenarios/internal_hu_v1.json](specs/scenarios/internal_hu_v1.json)
- [specs/scenarios/coinpoker_7max_mw_v3_actionspace_v2.json](specs/scenarios/coinpoker_7max_mw_v3_actionspace_v2.json)

### `profile`

定义运行预算和并发配置，例如：

- worker 数
- Monte Carlo rollout 预算

示例文件：

- [specs/profiles/internal_profile_v1.json](specs/profiles/internal_profile_v1.json)

### `policy`

定义系统策略闭包。

基线相关名称可参考 [notes/iteration_journal.md](notes/iteration_journal.md) 中“当前基线”段落。

### `opponents`

定义对手套件。

示例文件：

- [specs/opponents/suites/system_bot_league_7max_frozen_v1.json](specs/opponents/suites/system_bot_league_7max_frozen_v1.json)

### `settings.json`

这是 HRC 风格设置文件，适合 `run_hand` / `run_batch` / `doctor options-hash-from-hrc`。

项目里现成可用的示例：

- [specs/preflop/settings.json](specs/preflop/settings.json)

如果 `eqmodel.raked=true`：

- 你必须显式给 `--rounding-mode`
- 某些命令还需要显式给 `--reopen-on-short-allin` 或 `--no-reopen-on-short-allin`

## 输出产物怎么看

### `EventStream`

文件格式：

- NDJSON
- LF 结尾
- 第一行是 header

常见路径：

- `tmp/*.ndjson`
- `artifacts/<run_id>/eventstream/eventstream.ndjson`

### `Manifest / Report`

典型目录结构：

```text
artifacts/<run_id>/
├── eventstream/
├── manifest/
└── report/
```

你通常会看到：

- `runspec.json`
- `run_manifest.json`
- `report.json`
- `doctor_report.json`

### `tmp/`

`tmp/` 是实验输出区，不是规范定义区。可以删临时结果，但不要把它当成唯一真相来源。

真正的规范来源是：

- [ARCHIETECTURE.md](ARCHIETECTURE.md)
- [AGENTS.md](AGENTS.md)
- [notes/iteration_journal.md](notes/iteration_journal.md)

## 测试

运行全部测试：

```bash
pytest
```

只跑某一类：

```bash
pytest tests/test_run_hand_tool_cli.py
pytest tests/test_replay_cli.py
pytest tests/test_stats_cli.py
```

当前 `pyproject.toml` 配置了覆盖率要求：

- `--cov-fail-under=95`

所以测试不只是“能跑”，还要求覆盖率过线。

## 高级用法

### 完整评测

你可以用 `eval_full` 跑更完整的矩阵：

```bash
python3 -m poker2.cli.eval_full --help
```

它适合：

- Tier-A / Tier-P 评测
- paired compare
- pool eval
- BR proxy

但不适合第一次上手就跑，因为耗时和资源需求都更高。

### Pipeline

项目提供了 `pipeline` 子命令：

```bash
python3 -m poker2.cli.pipeline --help
```

但它更偏向内部流程编排，不是最推荐的新手入口。尤其是 `pipeline eval` 依赖运行上下文和 fixture 约束，第一次使用更容易踩到 fail-fast。

### 自动 loop

当前仓库建议只手动启动 loop，不要默认后台自动拉起。

手动启动：

```bash
zsh tools/ralph_autopilot_start.sh
```

手动停止：

```bash
zsh tools/ralph_autopilot_stop.sh
```

查看状态：

```bash
zsh tools/launchd_status_ralph_loop.sh
```

如果你明确要安装到 launchd：

```bash
zsh tools/launchd_install_ralph_loop.sh
zsh tools/launchd_uninstall_ralph_loop.sh
```

不建议新手一开始就碰 loop。先把单手、回放、fixtures、scrimmage 跑明白，再进入自动化优化。

## 常见报错与解决方式

### 1) `MISSING_ROUNDING_MODE`

原因：

- `settings.json` 里启用了 rake，但你没有传 `--rounding-mode`

解决：

- 补上 `--rounding-mode floor`
- 或者确认你的 `settings.json` 是否真的需要 rake

### 2) `JSON_PARSE_FAIL`

原因：

- `--starting-stacks-by-seat` 不是合法 JSON

正确写法：

```bash
'{"1":10000,"2":10000}'
```

### 3) `mw_ladder_id is required when multi-way may occur`

原因：

- 你给了会产生多人局面的配置，但没有完整提供 multi-way 语义闭包

解决：

- 优先使用已经打包好的 `scenario`
- 不要自己随意拼参数

### 4) `Iteration protocol validation failed: ['EVIDENCE_INCOMPLETE']`

原因：

- `scrimmage` 的手数太少，报告证据不足

解决：

- 增加 `--hands`
- 或先从 `run_hand` / `replay` / `stats` 学起

### 5) `MISSING_FIXTURE`

原因：

- 某些 `pipeline` 路径依赖内置 fixture 或特定上下文

解决：

- 新手先不要从 `pipeline eval` 入手
- 先用本文的 `run_hand` 和 `scrimmage`

## 推荐阅读顺序

如果你想真正读懂这个项目，而不是只会复制命令，按这个顺序看：

1. [README.md](README.md)
2. [ARCHIETECTURE.md](ARCHIETECTURE.md)
3. [notes/iteration_journal.md](notes/iteration_journal.md)
4. [poker2/cli](poker2/cli)
5. [tests](tests)

## License

仓库内未发现明确的开源许可证文件。如果你准备对外开源，建议补一个 `LICENSE`，再公开发布。
