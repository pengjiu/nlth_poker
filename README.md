# Poker2

`Poker2` 是一个面向 No-Limit Texas Hold'em 的研究型工程仓库，目标不是“跑一段训练脚本”，而是把策略执行、契约校验、事件流、回放、门禁和批量评测组织成一套可复现、可追溯、可验证的系统。

它的核心价值有三点：

- 同一输入应得到稳定、可重放的执行结果。
- 规则、哈希、契约和评测口径必须保持单一真相。
- 策略试验、基线比较、回归诊断必须落到结构化产物，而不是散落日志。

## 项目能力

- 单手执行：从 HRC 风格 `settings.json` 生成 `EventStream`
- 批量对局：按 `scenario / profile / policy / opponents` 跑多手评测
- 精确回放：按 `hand_id` 或 `decision_id + state_hash` 定位决策点
- 契约与门禁：对协议对象、fixtures、eventstream 做严格校验
- 基线评测：支持 Tier-A / Tier-P / paired compare / pool eval / BR proxy
- 自动化迭代：提供 loop 与相关辅助脚本，但默认只建议手动启动

## 仓库内容

下面这些关键资产已经随仓库提供，GitHub 新 clone 后就应该存在：

- `specs/preflop/hrc_hand2/`
  完整翻前节点数据目录，当前仓库内约 7858 个文件
- `fixtures/internal/`
  内置 golden fixtures、eventstream、pack
- `specs/retaliation/retaliation_model_v1.json`
  系统策略默认使用的 retaliation model 静态资产
- `specs/`
  scenarios、policies、policy params、profiles、opponents、rulesets、spot policies

运行过程中生成的临时结果仍然会落在：

- `tmp/`
- `artifacts/`

这两类目录属于运行输出，不是规范真相来源。

## 仓库结构

```text
poker2/
├── poker2/                  # 主 Python 包
│   ├── cli/                 # 命令行入口
│   ├── protocol/            # 契约对象、哈希、事件模型
│   ├── environment/         # 执行环境与账本
│   ├── runtime/             # 策略、注册表、运行时逻辑
│   ├── gates/               # 各类 Gate / Guard
│   └── engines/             # 求解器与可选 Rust / PyO3 绑定
├── specs/                   # scenarios / policies / rulesets / opponents / static assets
├── fixtures/                # 内置 fixtures 与 eventstream
├── tests/                   # pytest 测试
├── tools/                   # loop、launchd、清理、辅助脚本
├── notes/                   # 迭代日志与评测协议
├── ARCHIETECTURE.md         # 架构规范唯一权威文档
└── README.md                # 项目入口文档
```

## 环境要求

- Python `>= 3.11`
- macOS / Linux / WSL
- 推荐使用虚拟环境

可选依赖：

- `rustc`
- `cargo`
- `maturin`

只有在你要启用 postflop Rust / PyO3 绑定时，才需要 Rust 工具链。纯 Python 主链路可以先不装。

## 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
pip install -e .
```

说明：

- `requirements.txt` 是运行时依赖
- `requirements-dev.txt` 包含测试与开发依赖
- `pip install -e .` 让你可以直接使用 `python -m poker2.cli.xxx`

## 快速开始

### 1. 先跑最小健康检查

```bash
python3 -m poker2.cli.doctor contractkit-vectors
```

期望输出为 JSON，且 `status=pass`。

### 2. 跑一手牌，生成自己的 EventStream

```bash
python3 -m poker2.cli.run_hand \
  --settings specs/preflop/settings.json \
  --out tmp/readme_demo_hand.ndjson \
  --rounding-mode floor \
  --starting-stacks-by-seat '{"1":10000,"2":10000}' \
  --button-seat 1 \
  --no-reopen-on-short-allin
```

执行成功后会生成：

- `tmp/readme_demo_hand.ndjson`
- 一段 JSON 输出，包含 `event_stream_digest`、`run_id`、`scenario_id`、`options_hash`

### 3. 回放这手牌

```bash
python3 -m poker2.cli.replay \
  --eventstream tmp/readme_demo_hand.ndjson \
  --strict
```

如果要定位某个决策点：

```bash
python3 -m poker2.cli.replay \
  --eventstream tmp/readme_demo_hand.ndjson \
  --decision-id <id> \
  --state-hash <hash> \
  --strict
```

### 4. 验证内置 fixtures

```bash
python3 -m poker2.cli.stats fixtures-pack \
  --pack fixtures/internal/internal_ruleset_v1_pack.json \
  --ruleset specs/rulesets/internal_ruleset_v1.json \
  --strict
```

## 两套入口，先分清楚

这个项目最容易让新手混淆的地方，是 `--settings` 和 `--scenario` 完全不是一回事。

### `--settings`

适合：

- 跑单手
- 从 HRC 风格配置直接生成事件流
- 验证 rake / rounding / reopen 等规则口径

典型命令：

- `python -m poker2.cli.run_hand`
- `python -m poker2.cli.run_batch`
- `python -m poker2.cli.doctor options-hash-from-hrc`

### `--scenario`

适合：

- 跑标准评测
- 跑完整实验闭包
- 带 `profile / policy / opponents` 的批量对局

典型命令：

- `python -m poker2.cli.scrimmage`
- `python -m poker2.cli.scrimmage_batch`
- `python -m poker2.cli.eval_full`

结论：

- 想确认环境能跑，用 `--settings`
- 想跑正式实验，用 `--scenario + --profile + --policy + --opponents`

## 常用命令

| 目标 | 命令 | 说明 |
| --- | --- | --- |
| 最小健康检查 | `python3 -m poker2.cli.doctor contractkit-vectors` | 推荐第一条命令 |
| 单手生成事件流 | `python3 -m poker2.cli.run_hand ...` | 从 `settings.json` 跑一手牌 |
| 批量单手导出 | `python3 -m poker2.cli.run_batch ...` | 连续生成多手 `ndjson` |
| 回放事件流 | `python3 -m poker2.cli.replay --eventstream ...` | 看某手牌或某个决策点 |
| 检查 fixtures | `python3 -m poker2.cli.stats fixtures-pack ...` | 校验 golden fixtures |
| 检查单个事件流 | `python3 -m poker2.cli.stats eventstream ...` | 对单个 `ndjson` 跑统计 |
| 跑一轮评测 | `python3 -m poker2.cli.scrimmage ...` | 标准实验入口 |
| 跑完整评测矩阵 | `python3 -m poker2.cli.eval_full ...` | Tier-A / Tier-P / pool / BR |

## 标准评测示例

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

至少会生成：

- `tmp/readme_scrimmage_demo/scrimmage_report.json`

如果你只是确认环境是否通畅，不要一开始就跑 `scrimmage`。先把 `doctor`、`run_hand`、`replay`、`stats` 跑通。

## 配置对象说明

### `scenario`

定义实验语义闭包，例如：

- 规则集
- action space
- preflop / postflop 引用
- opponents / mw ladder / triad

示例：

- [specs/scenarios/internal_hu_v1.json](specs/scenarios/internal_hu_v1.json)
- [specs/scenarios/coinpoker_7max_mw_v3_actionspace_v2.json](specs/scenarios/coinpoker_7max_mw_v3_actionspace_v2.json)

### `profile`

定义运行预算与并发配置，例如：

- worker 数
- Monte Carlo rollout 预算

示例：

- [specs/profiles/internal_profile_v1.json](specs/profiles/internal_profile_v1.json)

### `policy`

定义系统策略闭包。当前正式基线请看：

- [notes/iteration_journal.md](notes/iteration_journal.md)

### `opponents`

定义对手套件。

示例：

- [specs/opponents/suites/system_bot_league_7max_frozen_v1.json](specs/opponents/suites/system_bot_league_7max_frozen_v1.json)

### `settings.json`

这是 HRC 风格设置文件，适合 `run_hand` / `run_batch` / `doctor options-hash-from-hrc`。

现成示例：

- [specs/preflop/settings.json](specs/preflop/settings.json)

如果 `eqmodel.raked=true`：

- 必须显式给 `--rounding-mode`
- 某些命令还需要显式给 `--reopen-on-short-allin` 或 `--no-reopen-on-short-allin`

## 输出产物

### `EventStream`

- 格式：NDJSON
- 每行 LF 结尾
- 第一行是 header

常见位置：

- `tmp/*.ndjson`
- `artifacts/<run_id>/eventstream/eventstream.ndjson`

### Manifest / Report

典型目录结构：

```text
artifacts/<run_id>/
├── eventstream/
├── manifest/
└── report/
```

常见文件：

- `runspec.json`
- `run_manifest.json`
- `report.json`
- `doctor_report.json`

真正的规范真相来源仍然是：

- [ARCHIETECTURE.md](ARCHIETECTURE.md)
- [notes/iteration_journal.md](notes/iteration_journal.md)

## 测试

运行全部测试：

```bash
pytest
```

只跑常见子集：

```bash
pytest tests/test_run_hand_tool_cli.py
pytest tests/test_replay_cli.py
pytest tests/test_stats_cli.py
```

当前仓库默认启用了覆盖率门槛：

- `--cov-fail-under=95`

## 手动 loop

当前仓库建议只手动启动 loop，不要默认后台自动拉起。

启动：

```bash
zsh tools/ralph_autopilot_start.sh
```

停止：

```bash
zsh tools/ralph_autopilot_stop.sh
```

查看状态：

```bash
zsh tools/launchd_status_ralph_loop.sh
```

如果你明确需要 launchd：

```bash
zsh tools/launchd_install_ralph_loop.sh
zsh tools/launchd_uninstall_ralph_loop.sh
```

## 常见问题

### `MISSING_ROUNDING_MODE`

原因：

- `settings.json` 启用了 rake，但命令没有提供 `--rounding-mode`

### `JSON_PARSE_FAIL`

原因：

- `--starting-stacks-by-seat` 不是合法 JSON

正确写法：

```bash
'{"1":10000,"2":10000}'
```

### `mw_ladder_id is required when multi-way may occur`

原因：

- 你给了可能进入多人局的配置，但没有提供完整 multi-way 语义闭包

建议：

- 优先使用已经打包好的 `scenario`

### `Iteration protocol validation failed: ['EVIDENCE_INCOMPLETE']`

原因：

- `scrimmage` 手数太少，证据不足

建议：

- 增加 `--hands`
- 或先从 `run_hand / replay / stats` 入手

## 推荐阅读顺序

1. [README.md](README.md)
2. [ARCHIETECTURE.md](ARCHIETECTURE.md)
3. [notes/iteration_journal.md](notes/iteration_journal.md)
4. [poker2/cli](poker2/cli)
5. [tests](tests)
