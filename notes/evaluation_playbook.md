# Evaluation Playbook (标准评测流程)

目标：让任何新接手的 AI/工程师都能按统一流程**启动评测 → 分析 → 迭代 → 归档**，并保证可复现、可对比、可回放。

## 0) 单一真相与规范入口
- 必读规范：`ARCHIETECTURE.md`（Normative 章节 + 0.3 权威锚点表）
- 执行规则：`AGENTS.md`
- 迭代规则与基线：`notes/iteration_journal.md`

## 1) 评测分层（必须）
评测分两层（见 `notes/iteration_journal.md`）：
- Tier‑A：历史可比基线回归（固定 opponents v1）
- Tier‑P：强对手压力评测（固定 opponents v3）

> 任何改动必须至少跑 Tier‑A + Tier‑P，并记录两者均值/方差。

## 2) 基线与对手套件
- 基线版本以 `notes/iteration_journal.md` 为准（baseline_id / scenario / opponents / seeds / hands）。
- 对手套件必须**版本化冻结**（见 R12），禁止覆盖旧套件。
- OpponentPool 默认使用 `specs/opponents/pools/system_bot_pool_v2.json`（包含 elite/aggressive reg 套件）。

## 3) 标准评测流程

### Step A：准备
- 读取 `notes/iteration_journal.md` 当前基线与评测矩阵
- 确认 policy / scenario / opponents / actionspace 一致
- strict_mode 必须为 True（由 scenario/CLI 保证）

### Step B：并行跑 Tier‑A / Tier‑P
示例（Tier‑A）：
```
python -m poker2.cli.scrimmage_batch \
  --scenario coinpoker_7max_mw_v3_actionspace_v2 \
  --profile internal_profile_v1 \
  --policy system_bot_policy_v3 \
  --opponents system_bot_league_7max_frozen_v1 \
  --hands 2000 --seeds [2000,2001,2002,2003,2004,2005] \
  --jobs <CPU-1> --out-dir tmp/tierA_run \
  --opponent-compliance --opponent-compliance-jobs 4
```

示例（Tier‑P）：
```
python -m poker2.cli.scrimmage_batch \
  --scenario coinpoker_7max_mw_v3_actionspace_v2 \
  --profile internal_profile_v1 \
  --policy system_bot_policy_v3 \
  --opponents system_bot_league_7max_frozen_v3 \
  --hands 2000 --seeds [2000,2001,2002,2003,2004,2005] \
  --jobs <CPU-1> --out-dir tmp/tierP_run \
  --opponent-compliance --opponent-compliance-jobs 4
```

产物：
- `tmp/.../scrimmage_batch.json`
- `tmp/.../seed_XXXX/scrimmage_report.json`
- `tmp/.../seed_XXXX/scrimmage_eventstream.ndjson`
- `tmp/.../opponent_compliance.json`（对手合规校验）

### Step B‑Plus：OpponentPool 评测（PSRO‑lite）
在准备设为新基线时，跑对手池评测（更抗过拟合）：
```
python -m poker2.cli.pool_eval \
  --pool specs/opponents/pools/system_bot_pool_v2.json \
  --scenario coinpoker_7max_mw_v3_actionspace_v2 \
  --profile internal_profile_v1 \
  --policy system_bot_policy_v3 \
  --hands 2000 --seeds [2000,2001,2002,2003,2004,2005] \
  --suite-jobs 2 --out-dir tmp/pool_eval_run \
  --opponent-compliance
```
输出：`tmp/pool_eval_run/pool_eval_summary.json`

### Step B‑Minus：基线配对对比（推荐）
用于“同矩阵同种子”的配对差异，防止均值误判：
```
python -m poker2.cli.paired_compare \
  --baseline tmp/tierA_baseline/scrimmage_batch.json \
  --candidate tmp/tierA_run/scrimmage_batch.json \
  --metric bb_per_100 --bootstrap 5000 --alpha 0.05 --seed 42 --strict
```
输出：`tmp/tierA_run/paired_compare.json`（包含 Δmean/Δstd/Δse 与 options_hash 对齐检查）

### Step C：构建 retaliation_model（被反制概率模型）
当准备启用/刷新“尺寸反制风险”时，用已有评测批次生成模型：
```
python -m poker2.cli.build_retaliation_model \
  --batches '["tmp/pool_eval_run/suiteA/scrimmage_batch.json","tmp/pool_eval_run/suiteB/scrimmage_batch.json"]' \
  --out artifacts/retaliation_model_v1.json \
  --jobs 4
```
然后更新：
1) `specs/policy_params/system_bot_params_v3.json` 里的 `retaliation_model_ref`
2) `specs/policies/system_bot_policy_v3.json` 的 policy_deps digest + policy_id

### Step C：读取指标与证据桶
- 报告主指标：`analysis.bb_per_100`
- 结构化证据桶：report 内 `bb_flat_postflop_facing_by_street` / `bb_flat_postflop` / `profit_by_players` 等
- 生成迭代证据由 `iteration_protocol` 自动写入 report（见 `poker2/tools/iteration_protocol.py`）

### Step D：对手合规校验（必做）
评估对手是否“常客范围”：
```
python -m poker2.cli.opponent_compliance \
  --batch tmp/tierP_run/scrimmage_batch.json \
  --out tmp/tierP_run/opponent_compliance.json \
  --jobs 4
```
该 JSON 会给出 aggregate 的 VPIP/PFR/3bet/4bet/AF 以及是否落入合理区间。

### Step D‑Plus：关键桶覆盖检查（必做）
确保关键桶样本量足够，避免“优化噪声”：
```
python -m poker2.cli.coverage_check \
  --batch tmp/tierP_run/scrimmage_batch.json \
  --min-n 20
```
输出：`tmp/tierP_run/coverage_check.json`

### Step E：BR(π) 压力入口（重要改动/拟设基线必做）
轻量 BR‑proxy（多对手并行，取“最坏套件”）：
```
python -m poker2.cli.br_proxy \
  --scenario coinpoker_7max_mw_v3_actionspace_v2 \
  --profile internal_profile_v1 \
  --policy system_bot_policy_v3 \
  --hands 2000 --seeds [2000,2001,2002,2003,2004,2005] \
  --candidates system_bot_league_7max_elite_reg_v1,system_bot_league_7max_aggressive_reg_v1,system_bot_league_7max_frozen_v3 \
  --suite-jobs 2 --out-dir tmp/br_proxy_run \
  --opponent-compliance --opponent-compliance-jobs 4
```
输出：`tmp/br_proxy_run/br_proxy_summary.json`

### Step F：Actionspace 微扰稳定性（拟设基线必做）
使用轻度动作空间微扰（不是 v3 那种大改）：
```
python -m poker2.cli.scrimmage_batch \
  --scenario coinpoker_7max_mw_v3_actionspace_v2_micro066 \
  --profile internal_profile_v1 \
  --policy system_bot_policy_v3 \
  --opponents system_bot_league_7max_frozen_v3 \
  --hands 2000 --seeds [2000,2001,2002,2003,2004,2005] \
  --jobs <CPU-1> --out-dir tmp/micro_actionspace_run \
  --opponent-compliance
```
要求：总体 EV 不崩盘，关键桶（OOP Facing=Y turn/river）不灾难性恶化。

## 4) 双层基线（确认基线）
主基线之外，必须再跑一组“确认基线”（2×(6×2000)），用于排除运气成分：
```
python -m poker2.cli.scrimmage_batch \
  --scenario coinpoker_7max_mw_v3_actionspace_v2 \
  --profile internal_profile_v1 \
  --policy system_bot_policy_v3 \
  --opponents system_bot_league_7max_frozen_v1 \
  --hands 2000 --seeds [2010,2011,2012,2013,2014,2015] \
  --jobs <CPU-1> --out-dir tmp/tierA_confirm_run \
  --opponent-compliance --opponent-compliance-jobs 4
```
两组均需 paired + bootstrap CI；仅当两组均显著优于基线，才允许升级基线。

## 5) 一键全量评测（推荐）
并行执行 Tier‑A/Tier‑P + 双层基线 + OpponentPool + BR‑proxy：
```
python -m poker2.cli.eval_full \
  --scenario coinpoker_7max_mw_v3_actionspace_v2 \
  --profile internal_profile_v1 \
  --policy system_bot_policy_v3 \
  --tierA-opponents system_bot_league_7max_frozen_v1 \
  --tierP-opponents system_bot_league_7max_frozen_v3 \
  --pool specs/opponents/pools/system_bot_pool_v2.json \
  --hands 2000 --seeds [2000,2001,2002,2003,2004,2005] \
  --confirm-seeds [2010,2011,2012,2013,2014,2015] \
  --out-dir tmp/full_eval_run \
  --opponent-compliance
```
产物：`tmp/full_eval_run/eval_full_summary.json`

## 6) 结果归档（必须）
每轮只新增一条摘要，写入 `notes/iteration_journal.md`：
- 记录 Tier‑A + Tier‑P 的 mean/std
- 记录 3 条证据桶（E1/E2/E3）
- 记录对手合规是否落入合理区间
- 若跑了 BR‑proxy，记录最坏套件与 mean/std

## 7) 基线更新规则（执行）
- 只有在 **Tier‑P 明显提升** + **Tier‑A 不退化** + **无灾难回归** 时更新基线。
- 更新基线必须记录 opponents_suite_id / scenario_id / actionspace_id / options_hash。

## 8) 常用定位路径
- 评测输出目录：`tmp/<run_name>/`
- 单 seed 报告：`seed_XXXX/scrimmage_report.json`
- 事件回放：`seed_XXXX/scrimmage_eventstream.ndjson`
- 报告查看：`poker2/cli/scrimmage_views.py` / `poker2/cli/analyze_report.py`

## 9) 注意事项（强制）
- 统计只能读 EventStream（见 ARCHIETECTURE.md 5.1/5.1.1）。
- 任何换算必须在 ActionAdapter / TreePathMappingSpec / Environment canonicalize→legalize 中完成（3.12/3.13/3.1.1）。
- 禁止在 evaluation/metrics/report 层自造动作口径（AGENTS.md）。
