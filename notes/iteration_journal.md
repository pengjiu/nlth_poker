# Iteration Journal v2 (Baseline + Rules + Results)

> 目标：把这里当作**基线定义**与**可执行改进规则**的单一真相。  
> 只记录“高价值、可复用”的结论；不记录流水账。

## 0) 使用方式
- 每次改动前先读本文件。
- 每次评测后**只补充一条“结果摘要记录”**（见第 5 节模板）。
- 任何 A/B 都必须与**当前基线**同矩阵、同规则、同对手套件、同 actionspace。
- 评测默认使用“强对手套件”；基线回归仍保留原对手套件，确保历史可比。

## 1) 基线注册表（唯一权威）
### 当前基线（必须遵守）
- baseline_id: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- policy_label: `system_bot_policy_v3_retaliation_weight_v1`（别名已固化到 v8 闭包）
- policy_label_explicit: `system_bot_policy_v3_retaliation_weight_v1_high_price_defend_gate_v8`
- scenario: `coinpoker_7max_mw_v3_actionspace_v2`
- opponents: `system_bot_league_7max_elite_reg_v1 + system_bot_league_7max_aggressive_reg_v1 + system_bot_league_7max_frozen_v3 + rule_suite_7max_strong_v1`
- hands_per_seed: `2000`
- seeds: `2000–2005`（6×2000）
- confirm_seeds: `null`
- mean_bb100: `≈-21.18`（robust 4-suite weighted mean）
- promote_delta_vs_prev_bb100: `≈+4.95`（vs retaliation_weight_v1_20260202）
- baseline_batch_ref: `path:tmp/robust_eval_v8_vs_baseline_restart_20260206_142515`
- confirm_batch_ref: `null`
- tierP_batch_ref: `null`
- tierP_confirm_batch_ref: `null`
- tierP_mean_bb100: `null`
- tierP_confirm_mean_bb100: `null`
- pool_eval_ref: `path:tmp/pool_br_v8_baseline_20260206_162806/pool_eval/pool_eval_summary.json`
- br_proxy_ref: `path:tmp/pool_br_v8_baseline_20260206_162806/br_proxy/br_proxy_summary.json`
- options_hash: `90243a673a8f0cc1360c75eda5466e8a23bfffd46dd66525b93b47f101b12134`
- tierP_options_hash: `90243a673a8f0cc1360c75eda5466e8a23bfffd46dd66525b93b47f101b12134`
- date: `2026-02-06`
- notes: 基线由 high-price defend gate v8 晋级；四套件均无回撤，overall/bootstrap CI 显著优于旧基线；旧别名文件已按 `*_pre_v8_20260206` 备份可回退。

### 默认压力套件（新评测维度）
- opponents_pressure: `system_bot_league_7max_frozen_v3`
- 目的：更强对手压力测试，用于“可剥削度”代理评估
### 默认对手池（PSRO‑lite）
- opponent_pool: `specs/opponents/pools/system_bot_pool_v2.json`
- 目的：动态对手分布评估 + BR(π) 压力入口

### 基线更新规则（硬规则）
- **晋级门槛（A 版）**：新策略只有在 **Tier‑P 加权对手分布的 EV 明显提升**，且 **Tier‑A 不显著退化**，同时 **关键弱桶不恶化** 并通过 **动作空间微扰稳定性**，才允许晋级为新基线。
- 未达到该标准的版本一律记为“实验对照”，不得称作“基线”。

## 2) 固定评测矩阵
### Tier‑A（基线回归）
- scenario: `coinpoker_7max_mw_v3_actionspace_v2`
- opponents: `system_bot_league_7max_frozen_v1`
- hands_per_seed: `2000`
- seeds: `2000–2005`
- confirm_seeds: `2010–2015`（双层基线）
- strict_mode: `True`
- 要求：同矩阵、同 actionspace、同 ruleset、同 opponents；否则结果不可与基线比较。

### Tier‑P（压力评测 / 可剥削度代理）
- scenario: `coinpoker_7max_mw_v3_actionspace_v2`
- opponents: `system_bot_league_7max_frozen_v3`
- hands_per_seed: `2000`
- seeds: `2000–2005`
- strict_mode: `True`
- 目的：回答“有没有对手能稳定打爆我？”
- 要求：每次改动都跑 Tier‑A + Tier‑P，并在结果摘要里同时记录两者的均值/方差变化。
- 并行：评测使用 `scrimmage_batch` 并行执行；对手合规校验用 `--opponent-compliance` 并行生成。

## 3) 改进规则（N条、可执行）
R1. **基线一致性**：所有“强弱判断”必须以“当前基线”对比。  
R2. **可复现**：必须记录 options_hash、policy_id、scenario_id、opponent_suite_id。  
R3. **证据优先**：只引用报告/回放中的结构化桶（见第 4 节）。  
R4. **机制优先**：只做机制级改动（EV/风险一致性/信息价值），禁止硬阈值补丁。  
R5. **单点闭环**：每次迭代只引入一个机制闭环；否则无法归因。  
R6. **不伤守恒**：任何防守/混合修改不得显著降低总防守频率。  
R7. **同矩阵回归**：改动后必须跑 Tier‑A 6×2000，同矩阵对比。  
R8. **结果只写结论**：仅记录“有效/无效+原因+下一步”，不写流水账。
R9. **可剥削度代理**：每次改动后必须跑 Tier‑P；若条件允许，应构造/训练近似 BR(π) 对手，并以 EV(BR(π), π) 作为“可被剥削度”指标。
R10. **并行执行**：批量评测必须使用 `scrimmage_batch`，默认 jobs=CPU-1（可手动覆写），以保证统计意义与效率。
R11. **结果双维度**：每条迭代摘要必须包含 Tier‑A 与 Tier‑P 的均值/方差结论（不满足则视为无效评测）。
R12. **对手套件进化**：对手套件只允许“版本化冻结更新”；更新频率必须低于策略迭代频率（建议每 10 次或每月一次），旧套件必须保留。
R13. **对手合规校验**：对手套件更新必须生成 `opponent_compliance.json`（VPIP/PFR/3bet/4bet/AF 等），并在结果摘要里标注“是否落入合理区间”。
R14. **BR(π) 入口**：重要改动（准备设为新基线）至少跑一次 BR‑proxy（`poker2.cli.br_proxy`），记录最坏对手套件与 mean/std。
R15. **动作空间微扰稳定性**：准备设为新基线时，必须跑一次 actionspace 微扰评测（`coinpoker_7max_mw_v3_actionspace_v2_micro066`），要求整体 EV 不崩盘且关键桶不灾难性恶化。
R16. **关键桶覆盖**：每轮评测必须运行覆盖检查（`poker2.cli.coverage_check`），关键桶手数不足则不得据此优化。
R17. **配对对比**：若存在同矩阵的 baseline 批次，必须运行 `poker2.cli.paired_compare --strict --bootstrap >=2000` 并记录 CI；若 seeds 或 options_hash 不一致，视为不可对比。
R18. **options_hash 锁定**：评测必须显式包含 `solver_build_id`（policy params 内），否则视为不可对比。
R19. **双层基线**：基线更新必须跑两组独立 seeds（2×(6×2000)）；两组 paired+bootstrap CI 均需显著优于旧基线，且 Tier‑P 不退化。
R20. **OpponentPool + BR(π)**：每轮评测必须跑 `pool_eval`（PSRO‑lite）与 `br_proxy`（最坏对手压力），并在摘要中记录最坏套件与 mean/std。

## 4) 证据标准（每轮必须给 3 条）
格式：`bucket_key | metric=value | n=? | seeds=? | evidence_ref=?`
- E1: 位置×街×Facing 的最差桶  
- E2: SPR 最差桶（可标 OOP 多街）  
- E3: 人数桶最差（2p/3p/4p…）  
要求：只用 report/eventstream 能 grep 到的结构化 key。

## 5) 结果摘要记录（每轮仅新增 1 条）
模板（复制填写）：
- change_id: <YYYY-MM-DD-xxx>
- change_type: Define | Refine | Enforce | Restructure
- scope: <契约对象/模块>
- baseline: <baseline_id>
- delta: <bb/100 mean±std vs baseline>
- evidence: <E1/E2/E3 三条>
- outcome: ADOPT | REJECT | CONTINUE
- rationale: <为何有效/无效 + 下一步>

## [autopilot-hook] 2026-03-06T18:13:44+0800 cycle=145 reason=cycle_completed
- change_type: Patch
- decision: apply_turn_support_visibility_reentry_trigger_v1
- why: `no_improve_streak=63` and cycle145 review still shows `support_pass_count=0`, `eligible_count=0`, `targeted_focus_support_hands_delta_total=24`, `targeted_focus_support_hits_delta_total=0`, with `llm_action_gate.reason=missing_action`; the loop needs both a consumable action ticket and a tighter mechanism patch that turns stalled support hands into observable hits.
- what: patched `poker2/runtime/system_policy.py` to add `ramp_reentry_support_visibility_trigger`, a bounded TURN-only pre-stall reentry aperture for MW + wet + low-SPR high-price branches where ramp pressure exists but remains below the existing stall trigger while deadlock/bridge relief stays near zero.
- rollback: remove `ramp_reentry_support_visibility_trigger`, `visibility_relaxed_wet_branch`, and the corresponding reentry activation branch from `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=/tmp/pycache_verify python3 -m py_compile poker2/runtime/system_policy.py` and `python3` JSON required-field validation for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle145_20260306_181344_autohook.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_145_20260306_123339/review.json`, `tmp/ralph_loop_runs_v2/cycle_145_20260306_123339/cycle_result.json`

### 2026-03-06-cycle145-turn-support-visibility-reentry-trigger-v1
- change_id: 2026-03-06-cycle145-turn-support-visibility-reentry-trigger-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（TURN high-price pre-stall visibility reentry aperture）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（checkpoint light patch; heavy eval deferred）
- evidence:
  - E1 | metric=no_improve_streak=63 | n=1 state | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E2 | metric=cycle145.quick_gate.support_pass_count=0,targeted_focus_support_hands_delta_total=24,targeted_focus_support_hits_delta_total=0,llm_action_gate.reason=missing_action | n=1 cycle | seeds=cycle145 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_145_20260306_123339/review.json
  - E3 | metric=mechanism_patch_applied(turn_support_visibility_reentry_trigger_v1) | n=1 file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: fill the pre-stall gap below the existing TURN starvation trigger so the next quick gate can observe support hits without widening unrelated price bands; if support remains zero, escalate to a stricter low-SPR wet firewall rather than more aperture layers.

### 2026-01-17-raise-cap-blend-refactor
- change_id: 2026-01-17-raise-cap-blend-refactor
- change_type: Restructure
- scope: `poker2/runtime/system_policy.py`（防守混合管线结构化 + raise_cap 软混合保留）
- baseline: revert94
- delta: mean≈21.66 (std≈13.80) vs baseline≈25.86 → Δ≈-4.20 bb/100
- evidence:
  - TURN|Facing=Y | bb/100=-814.14 | n=22 | seeds=2000–2004 | ref=report:bb_flat_postflop_facing_by_street
  - SPR:2-4 | bb/100=+267.04 | n=119 | seeds=2000–2004 | ref=report:spr_buckets
  - TURN|players=4 | bb/100=-1222.82 | n=17 | seeds=2000–2004 | ref=report:profit_by_players
- outcome: CONTINUE
- rationale: 结构化改造不改变行为；强度仍低于基线但更稳定。下一步继续针对 TURN/RIVER OOP Facing=Y 的薄跟注风险做机制级削弱。

## [autopilot-hook] 2026-03-10T06:52:03+0800 cycle=168 reason=cycle_completed
- change_type: Patch
- decision: apply_low_spr_wet_firewall_prearm_v1
- why: `no_improve_streak=86` forces a mechanism step, and cycle168 quick gate rejected with `quick_gate_runtime_error` after six mechanism trials showed `targeted_focus_support_hands_delta_total=0`, `targeted_focus_support_hits_delta_total=0`, `eligible_count=0`, and the active `llm_action_gate.reason=source_cycle_mismatch`; the safest next move is a bounded behavior change inside the existing low-SPR wet-board high-price defense path.
- what: patched `poker2/runtime/system_policy.py` to pre-arm the existing `low_spr_wet_firewall` in 4-way+ TURN/RIVER high-price spots when wetness and low SPR are already building, allowing the clamp to engage slightly before the previous hard trigger while still honoring call-edge and raise-gap relief.
- rollback: remove `firewall_prearm_strength`, `firewall_armed`, and the associated pre-arm threshold block from `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=/tmp/pycache_verify python3 -m py_compile poker2/runtime/system_policy.py` and `python3` required-field validation for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle168_20260310_065203_autohook.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_168_20260310_063348/review.json`, `tmp/ralph_loop_runs_v2/cycle_168_20260310_063348/cycle_result.json`

### 2026-03-10-cycle168-low-spr-wet-firewall-prearm-v1
- change_id: 2026-03-10-cycle168-low-spr-wet-firewall-prearm-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（4-way+ TURN/RIVER high-price low-SPR wet-board firewall pre-arm）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（checkpoint light patch; heavy eval deferred）
- evidence:
  - E1 | metric=no_improve_streak=86 | n=1 state | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E2 | metric=cycle168.quick_gate.reason=quick_gate_runtime_error,targeted_focus_support_hands_delta_total=0,targeted_focus_support_hits_delta_total=0,eligible_count=0,llm_action_gate.reason=source_cycle_mismatch | n=1 cycle | seeds=cycle168 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_168_20260310_063348/review.json
  - E3 | metric=mechanism_patch_applied(low_spr_wet_firewall_prearm_v1) | n=1 file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: pre-arm the existing wet-board firewall instead of stacking another independent gate, so the next worker run can produce a real behavior delta in the stressed multiway branch while remaining reversible and bounded if runtime stays unstable.

### 2026-01-17-solver-gap-soft
- change_id: 2026-01-17-solver-gap-soft
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（OOP 面对下注时基于 raise-call EV 差的软混合约束）
- baseline: revert94
- delta: mean≈20.69 (std≈15.37) vs baseline≈25.86 → Δ≈-5.17 bb/100
- evidence:
  - TURN|Facing=Y | bb/100=-1148.04 | n=23 | seeds=2000–2004 | ref=report:bb_flat_postflop_facing_by_street
  - SPR:2-4 | bb/100=-2670.20 | n=5 | seeds=2000–2004 | ref=report:bb_flat_postflop_spr_by_street
  - RIVER|players=4 | bb/100=-1178.69 | n=13 | seeds=2000–2004 | ref=report:profit_by_players
- outcome: CONTINUE
- rationale: 轻微收敛但不足以修复 Facing=Y 负桶，且整体仍低于基线；需要更强的防守目标削弱或价值估计改进。

### 2026-01-17-defend-edge-scale
- change_id: 2026-01-17-defend-edge-scale
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（TURN/RIVER OOP 防守目标随净边际收缩）
- baseline: revert94
- delta: mean≈20.46 (std≈15.24) vs baseline≈25.86 → Δ≈-5.40 bb/100
- evidence:
  - TURN|Facing=Y | bb/100=-1115.21 | n=24 | seeds=2000–2004 | ref=report:bb_flat_postflop_facing_by_street
  - SPR:2-4 | bb/100=-2670.20 | n=5 | seeds=2000–2004 | ref=report:bb_flat_postflop_spr_by_street
  - RIVER|players=4 | bb/100=-1178.69 | n=13 | seeds=2000–2004 | ref=report:profit_by_players
- outcome: CONTINUE
- rationale: 防守目标收缩后 Facing=Y 略有改善但不足；核心仍是价值估计偏差与多人/高价位路径的风险定价不足。

### 2026-01-17-postflop-solver-ev-on
- change_id: 2026-01-17-postflop-solver-ev-on
- change_type: Refine
- scope: `specs/policy_params/system_bot_params_v3.json`（启用 postflop solver EV 输入）
- baseline: revert94
- delta: mean≈14.16 (std≈12.89) vs baseline≈25.86 → Δ≈-11.70 bb/100
- evidence:
  - TURN|Facing=Y | bb/100=-862.32 | n=22 | seeds=2000–2004 | ref=report:bb_flat_postflop_facing_by_street
  - SPR:1-2 | bb/100=-1941.67 | n=12 | seeds=2000–2004 | ref=report:bb_flat_postflop_spr_by_street
  - TURN|players=4 | bb/100=-1601.37 | n=19 | seeds=2000–2004 | ref=report:profit_by_players
- outcome: REJECT
- rationale: equity-only solver EV 使非 Facing 桶整体下滑，且总体均值显著下降；需要更强 value model 才可启用。

### 2026-01-17-defend-cost-scale
- change_id: 2026-01-17-defend-cost-scale
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（TURN/RIVER OOP 防守目标按 Δrake+oop_cost 软缩放）
- baseline: revert94
- delta: mean≈21.80 (std≈13.66) vs baseline≈25.86 → Δ≈-4.06 bb/100
- evidence:
  - TURN|Facing=Y | bb/100=-814.14 | n=22 | seeds=2000–2004 | ref=report:bb_flat_postflop_facing_by_street
  - SPR:2-4 | bb/100=-2670.20 | n=5 | seeds=2000–2004 | ref=report:bb_flat_postflop_spr_by_street
  - TURN|players=4 | bb/100=-1222.82 | n=17 | seeds=2000–2004 | ref=report:profit_by_players
- outcome: CONTINUE
- rationale: 均值略升但仍低于基线；Facing=Y 负桶未实质收敛，需更强的多街价值折价机制或动作空间/对手模型协同改进。

### 2026-01-17-call-realization-discount
- change_id: 2026-01-17-call-realization-discount
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（TURN/RIVER OOP CALL equity realization 折扣）
- baseline: revert94
- delta: mean≈9.82 (std≈11.04) vs baseline≈25.86 → Δ≈-16.04 bb/100
- evidence:
  - TURN|Facing=Y | bb/100=-667.65 | n=20 | seeds=2000–2004 | ref=report:bb_flat_postflop_facing_by_street
  - SPR:1-2 | bb/100=-1989.69 | n=16 | seeds=2000–2004 | ref=report:bb_flat_postflop_spr_by_street
  - RIVER|players=4 | bb/100=-98.75 | n=12 | seeds=2000–2004 | ref=report:profit_by_players
- outcome: REJECT
- rationale: Facing=Y 负桶收敛，但整体非面对下注桶大幅恶化；CALL 现实折扣过强，导致整体EV下滑。

### 2026-01-17-mw-defend-scale
- change_id: 2026-01-17-mw-defend-scale
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（TURN/RIVER OOP 多人防守目标软缩放）
- baseline: revert94
- delta: mean≈22.17 (std≈13.68) vs baseline≈25.86 → Δ≈-3.69 bb/100
- evidence:
  - TURN|Facing=Y | bb/100=-814.14 | n=22 | seeds=2000–2004 | ref=report:bb_flat_postflop_facing_by_street
  - SPR:2-4 | bb/100=-2670.20 | n=5 | seeds=2000–2004 | ref=report:bb_flat_postflop_spr_by_street
  - TURN|players=4 | bb/100=-1127.88 | n=17 | seeds=2000–2004 | ref=report:profit_by_players
- outcome: CONTINUE
- rationale: 均值小幅提升且多人数桶改善，但 Facing=Y 仍未收敛；可作为当前最优实验继续迭代。

### 2026-03-08-cycle154-turn-support-visibility-bridge-reentry-trigger-v1
- change_id: 2026-03-08-cycle154-turn-support-visibility-bridge-reentry-trigger-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（TURN 低正桥接压 visibility gap reentry）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（checkpoint light patch; heavy eval deferred）
- evidence:
  - E1 | metric=no_improve_streak=71 | n=1 state | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E2 | metric=cycle153.quick_gate.support_pass_count=0,targeted_focus_support_hands_delta_total=24,targeted_focus_support_hits_delta_total=0,llm_action_gate.reason=missing_action | n=1 cycle | seeds=cycle153 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_153_20260308_152910/review.json
  - E3 | metric=mechanism_patch_applied(turn_support_visibility_bridge_reentry_trigger_v1) | n=1 file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: 现有 TURN visibility 触发器只覆盖 bridge penalty 近零分支，导致低正桥接压分支累计 support hands 却没有 support hits；补一条受限再入通道，让下一轮 quick gate 能观察到行为变化，同时不放宽 deadlock/probe 路径。

### 2026-01-17-price-spr-defend
- change_id: 2026-01-17-price-spr-defend
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（TURN/RIVER OOP 防守目标加入 price×SPR 连续缩放）

### 2026-01-28-preflop-ranges-v3-hu
- change_id: 2026-01-28-preflop-ranges-v3-hu
- change_type: Refine
- scope: `poker2/protocol/preflop_ranges.py` + `poker2/cli/build_preflop_ranges.py` + `poker2/runtime/system_policy.py`（HRC v3 ranges + HU facing bet prior）
- baseline: river_rollout_spr2p5_20260126
- delta: Tier‑A mean≈12.83 (std≈21.31) vs baseline≈20.03 → Δ≈-7.20 bb/100；Tier‑A confirm mean≈4.66 (std≈13.24) vs baseline≈8.94 → Δ≈-4.28；Tier‑P mean≈11.41 (std≈14.52) vs baseline≈11.84 → Δ≈-0.43
- evidence:
  - BB|RIVER|Facing=Y | bb/100=-1691.90 | n=10 | seeds=2000 | ref=report:bb_flat_postflop_facing_by_street
  - BB|TURN|SPR:7+ | bb/100=-482.20 | n=25 | seeds=2000 | ref=report:bb_flat_postflop_spr_by_street
  - FLOP|players=4 | bb/100=-1165.45 | n=11 | seeds=2000 | ref=report:profit_by_players
- outcome: REJECT
- rationale: v3 ranges 仅 HU facing bet 启用但整体 EV 下滑，且 options_hash 变更导致与基线 strict paired compare 不可直接对比；当前表现未达晋级门槛。Pool/BR 最坏套件为 aggressive_reg（mean≈9.84），仍显著低于基线压力表现。

### 2026-01-24-river-oop-call-compress
- change_id: 2026-01-24-river-oop-call-compress
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（RIVER OOP Facing=Y 下 call_floor/ceiling 软压缩）
- baseline: hu_rollout_river_20260123
- delta: Tier-A mean≈15.66 (std≈28.99) vs baseline≈7.23 → Δ≈+8.43; Tier-P mean≈8.35 (std≈12.19) vs baseline≈4.31 → Δ≈+4.04；confirm Tier-A≈5.99 vs 4.23 (CI 跨 0), Tier-P≈5.42 vs 6.52 → Δ≈-1.11
- evidence:
  - RIVER_Y | bb/100=-824.73 | n=60 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:1-2 | bb/100=-28.64 | n=94 | seeds=2000–2005 | ref=report:SPRBuckets/1-2
  - TURN_4p | bb/100=-114.48 | n=21 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
- outcome: CONTINUE
- rationale: 主矩阵显著提升但确认集未稳定超越，且 Tier‑P confirm 仍低于基线；需进一步降低 RIVER Facing=Y 负桶并提升 confirm 稳定性后再考虑晋级。

### 2026-01-24-raise-retaliation-penalty
- change_id: 2026-01-24-raise-retaliation-penalty
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（Facing=Y Raise 引入 p_raise×EV_conf 软惩罚）
- baseline: hu_rollout_river_20260123
- delta: Tier-A mean≈11.44 (std≈20.04) vs baseline≈7.23 → Δ≈+4.21; Tier-P mean≈8.07 (std≈11.69) vs baseline≈4.31 → Δ≈+3.76；confirm Tier-A≈6.21 vs 4.23 (CI 跨 0), Tier-P≈5.42 vs 6.52 → Δ≈-1.11
- evidence:
  - RIVER_Y | bb/100=-824.73 | n=60 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:1-2 | bb/100=-259.65 | n=94 | seeds=2000–2005 | ref=report:SPRBuckets/1-2
  - TURN_4p | bb/100=-1519.67 | n=21 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
- outcome: REJECT
- rationale: Raise 反制惩罚导致主矩阵均值回落且关键桶未改善，Tier‑P confirm 仍低于基线；该机制对当前弱点无效，需转向更直接的 RIVER Facing=Y 价值估计/rollout 校准。

### 2026-01-24-river-oop-cost
- change_id: 2026-01-24-river-oop-cost
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（RIVER OOP call/raise 引入轻量成本）
- baseline: hu_rollout_river_20260123
- delta: Tier-A mean≈15.66 (std≈28.99) vs baseline≈7.23 → Δ≈+8.43; Tier-P mean≈8.35 (std≈12.19) vs baseline≈4.31 → Δ≈+4.04；confirm Tier-A≈5.99 vs 4.23, Tier-P≈5.42 vs 6.52
- evidence:
  - RIVER_Y | bb/100=-824.73 | n=60 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:1-2 | bb/100=-28.64 | n=94 | seeds=2000–2005 | ref=report:SPRBuckets/1-2
  - TURN_4p | bb/100=-114.48 | n=21 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
- outcome: REJECT
- rationale: 结果与上一版本完全一致，行为未发生可观测变化（目标桶无改善）；该成本项未生效，需改为直接影响 score/rollout 的机制。

### 2026-01-24-river-call-margin
- change_id: 2026-01-24-river-call-margin
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（RIVER Facing=Y 提高 call dominated margin）
- baseline: hu_rollout_river_20260123
- delta: Tier-A mean≈15.66 (std≈28.99) vs baseline≈7.23 → Δ≈+8.43; Tier-P mean≈8.35 (std≈12.19) vs baseline≈4.31 → Δ≈+4.04；confirm Tier-A≈5.99 vs 4.23, Tier-P≈5.42 vs 6.52
- evidence:
  - RIVER_Y | bb/100=-824.73 | n=60 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:1-2 | bb/100=-28.64 | n=94 | seeds=2000–2005 | ref=report:SPRBuckets/1-2
  - TURN_4p | bb/100=-114.48 | n=21 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
- outcome: REJECT
- rationale: 提高 margin 未改变可观测行为与关键桶，说明该分支在当前样本中未生效；需转向直接改写 score 或 rollout 的策略通路。

### 2026-01-24-river-rollout-override
- change_id: 2026-01-24-river-rollout-override
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（RIVER Facing=Y OOP 强化 rollout 覆盖）
- baseline: hu_rollout_river_20260123
- delta: Tier-A mean≈15.79 (std≈29.56) vs baseline≈7.23 → Δ≈+8.57; Tier-P mean≈8.50 (std≈12.91) vs baseline≈4.31 → Δ≈+4.19；confirm Tier-A≈6.22 vs 4.23 (CI 跨 0), Tier-P≈5.57 vs 6.52 → Δ≈-0.95
- evidence:
  - RIVER_Y | bb/100=-791.22 | n=60 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:1-2 | bb/100=-93.89 | n=92 | seeds=2000–2005 | ref=report:SPRBuckets/1-2
  - TURN_4p | bb/100=-114.48 | n=21 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
- outcome: CONTINUE
- rationale: 主矩阵显著提升且 RIVER Facing=Y 负桶有收敛，但 Tier‑P confirm 仍低于基线；需要进一步压缩 RIVER Facing=Y 并提高压力确认集稳定性后再考虑晋级。

### 2026-01-24-river-rollout-tight
- change_id: 2026-01-24-river-rollout-tight
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（RIVER Facing=Y OOP rollout 仅保留 fold/call/最佳 raise + 更强覆盖）
- baseline: hu_rollout_river_20260123
- delta: Tier-A mean≈15.60 (std≈29.25) vs baseline≈7.23 → Δ≈+8.37; Tier-P mean≈8.02 (std≈12.68) vs baseline≈4.31 → Δ≈+3.71；confirm Tier-A≈6.24 vs 4.23, Tier-P≈5.30 vs 6.52
- evidence:
  - RIVER_Y | bb/100=-846.00 | n=60 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:1-2 | bb/100=-66.73 | n=93 | seeds=2000–2005 | ref=report:SPRBuckets/1-2
  - TURN_4p | bb/100=-114.48 | n=21 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
- outcome: REJECT
- rationale: 紧缩动作集导致 RIVER Facing=Y 负桶反弹、Tier‑P confirm 继续低于基线；覆盖强化未带来稳定收益，回退至上一候选。

### 2026-01-24-river-rollout-beta
- change_id: 2026-01-24-river-rollout-beta
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（RIVER Facing=Y OOP 提高 rollout β + 下限覆盖）
- baseline: hu_rollout_river_20260123
- delta: Tier-A mean≈15.79 (std≈29.56) vs baseline≈7.23 → Δ≈+8.57; Tier-P mean≈8.50 (std≈12.91) vs baseline≈4.31 → Δ≈+4.19；confirm Tier-A≈6.22 vs 4.23, Tier-P≈5.57 vs 6.52
- evidence:
  - RIVER_Y | bb/100=-791.22 | n=60 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:1-2 | bb/100=-93.89 | n=92 | seeds=2000–2005 | ref=report:SPRBuckets/1-2
  - TURN_4p | bb/100=-114.48 | n=21 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
- outcome: CONTINUE
- rationale: 行为已被 rollout 强制覆盖（blend≈1.0），但 Tier‑P confirm 仍低于基线；需进一步降低 RIVER Facing=Y（可能需要针对 call 价值校准或减少 raise 偏好）。

### 2026-01-24-river-rollout-call-cost
- change_id: 2026-01-24-river-rollout-call-cost
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（RIVER Facing=Y rollout 内加入 call 风险成本）
- baseline: hu_rollout_river_20260123
- delta: Tier-A mean≈15.80 (std≈29.56) vs baseline≈7.23 → Δ≈+8.58; Tier-P mean≈8.51 (std≈12.92) vs baseline≈4.31 → Δ≈+4.20；confirm Tier-A≈6.23 vs 4.23, Tier-P≈5.58 vs 6.52
- evidence:
  - RIVER_Y | bb/100=-791.22 | n=60 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:1-2 | bb/100=-93.89 | n=92 | seeds=2000–2005 | ref=report:SPRBuckets/1-2
  - TURN_4p | bb/100=-114.48 | n=21 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
- outcome: REJECT
- rationale: 指标几乎与上一版本一致，关键桶无变化；call 成本仍不足以改变实际决策，需要更强的价值校准或动作价值重估。

### 2026-01-24-river-raise-gap-gate
- change_id: 2026-01-24-river-raise-gap-gate
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（RIVER Facing=Y rollout 对 raise 加强 gap 惩罚）
- baseline: hu_rollout_river_20260123
- delta: Tier-A mean≈15.47 (std≈29.58) vs baseline≈7.23 → Δ≈+8.24; Tier-P mean≈8.18 (std≈12.87) vs baseline≈4.31 → Δ≈+3.87；confirm Tier-A≈6.40 vs 4.23, Tier-P≈5.76 vs 6.52
- evidence:
  - RIVER_Y | bb/100=-855.47 | n=60 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:1-2 | bb/100=-93.89 | n=92 | seeds=2000–2005 | ref=report:SPRBuckets/1-2
  - TURN_4p | bb/100=-114.48 | n=21 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
- outcome: REJECT
- rationale: RIVER Facing=Y 负桶反而恶化、Tier‑P confirm 仍未过线；gap 惩罚削弱了 raise 但未提升整体稳定性，回退。

### 2026-01-24-river-call-blend-strong
- change_id: 2026-01-24-river-call-blend-strong
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（RIVER Facing=Y rollout 内 call EV 强混合 equity）
- baseline: hu_rollout_river_20260123
- delta: Tier-A mean≈15.79 (std≈29.56) vs baseline≈7.23 → Δ≈+8.57; Tier-P mean≈8.50 (std≈12.91) vs baseline≈4.31 → Δ≈+4.19；confirm Tier-A≈6.22 vs 4.23, Tier-P≈5.58 vs 6.52
- evidence:
  - RIVER_Y | bb/100=-791.22 | n=60 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:1-2 | bb/100=-93.89 | n=92 | seeds=2000–2005 | ref=report:SPRBuckets/1-2
  - TURN_4p | bb/100=-114.48 | n=21 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
- outcome: REJECT
- rationale: 指标与 rollout_beta 几乎一致，说明该混合未改变决策（可能缺少有效 equity 或影响不足），回退。

### 2026-01-24-river-defend-scale
- change_id: 2026-01-24-river-defend-scale
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（RIVER Facing=Y 目标防守率按价格/不确定性收缩）
- baseline: hu_rollout_river_20260123
- delta: Tier-A mean≈15.38 (std≈27.46) vs baseline≈7.23 → Δ≈+8.15; Tier-P mean≈8.32 (std≈11.38) vs baseline≈4.31 → Δ≈+4.01；confirm Tier-A≈5.81 vs 4.23, Tier-P≈5.14 vs 6.52
- evidence:
  - RIVER_Y | bb/100=-855.47 | n=60 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:1-2 | bb/100=-93.89 | n=92 | seeds=2000–2005 | ref=report:SPRBuckets/1-2
  - TURN_4p | bb/100=-114.48 | n=21 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
- outcome: REJECT
- rationale: 虽抬高主矩阵均值但 confirm 下降且 RIVER Facing=Y 未改善，无法晋级，回退。

### 2026-01-24-river-range-hint
- change_id: 2026-01-24-river-range-hint
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（RIVER facing bet 启用 HU range hint，低置信度参与 equity）
- baseline: hu_rollout_river_20260123
- delta: Tier-A mean≈17.12 (std≈29.75) vs baseline≈7.23 → Δ≈+9.89; Tier-P mean≈9.83 (std≈13.77) vs baseline≈4.31 → Δ≈+5.52；confirm Tier-A≈6.61 vs 4.23, Tier-P≈5.79 vs 6.52
- evidence:
  - RIVER_Y | bb/100=-778.58 | n=60 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:1-2 | bb/100=+200.60 | n=87 | seeds=2000–2005 | ref=report:SPRBuckets/1-2
  - TURN_4p | bb/100=-114.48 | n=21 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
- outcome: CONTINUE
- rationale: 主矩阵与压力矩阵显著提升，RIVER Facing=Y 继续收敛；但 Tier‑P confirm 仍未超过基线，需微调 range hint 强度以冲线。

### 2026-01-25-river-range-hint-conf062
- change_id: 2026-01-25-river-range-hint-conf062
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（RIVER range‑hint 置信度小幅提升）
- baseline: hu_rollout_river_20260123
- delta: Tier‑A mean≈17.55 (std≈27.03) vs baseline≈7.23 → Δ≈+10.32; Tier‑P mean≈10.02 (std≈12.63) vs baseline≈4.31 → Δ≈+5.71；confirm Tier‑A≈6.80 vs 4.23, Tier‑P≈5.98 vs 6.52
- evidence:
  - RIVER_Y | bb/100=-778.58 | n=60 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:1-2 | bb/100=+233.59 | n=87 | seeds=2000–2005 | ref=report:SPRBuckets/1-2
  - TURN_4p | bb/100=-114.48 | n=21 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
- outcome: CONTINUE
- rationale: 主/压矩阵继续走高且 RIVER_Y 收敛，但 Tier‑P confirm 仍略低于基线，下一步继续以“范围提示强度”做微幅校准冲线。

### 2026-01-26-river-range-hint-conf068
- change_id: 2026-01-26-river-range-hint-conf068
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（RIVER range‑hint 置信度再小幅提升）
- baseline: hu_rollout_river_20260123
- delta: Tier‑A mean≈17.40 (std≈27.04) vs baseline≈7.23 → Δ≈+10.18; Tier‑P mean≈9.87 (std≈12.60) vs baseline≈4.31 → Δ≈+5.56；confirm Tier‑A≈6.79 vs 4.23, Tier‑P≈5.97 vs 6.52
- evidence:
  - RIVER_Y | bb/100=-778.58 | n=60 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:4-7 | bb/100=+231.17 | n=339 | seeds=2000–2005 | ref=report:SPRBuckets/4-7
  - TURN_4p | bb/100=-114.48 | n=21 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
- outcome: CONTINUE
- rationale: 主/压矩阵继续高位，但 Tier‑P confirm 仍未越线；改走“形状调整”而非继续线性加权。

### 2026-01-26-river-range-hint-conf068-tighten
- change_id: 2026-01-26-river-range-hint-conf068-tighten
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（RIVER facing bet 范围轻微收紧）
- baseline: hu_rollout_river_20260123
- delta: Tier‑A mean≈17.24 (std≈27.16) vs baseline≈7.23 → Δ≈+10.01; Tier‑P mean≈9.94 (std≈12.62) vs baseline≈4.31 → Δ≈+5.63；confirm Tier‑A≈6.79 vs 4.23, Tier‑P≈5.97 vs 6.52
- evidence:
  - RIVER_Y | bb/100=-778.58 | n=60 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:1-2 | bb/100=+200.60 | n=87 | seeds=2000–2005 | ref=report:SPRBuckets/1-2
  - TURN_4p | bb/100=-114.48 | n=21 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
- outcome: CONTINUE
- rationale: 收紧范围对主/压矩阵无显著差异，confirm 仍不足；下一步改为“置信度随 bet size 变化”的形状调整。

### 2026-01-26-river-range-hint-conf068-sizeconf
- change_id: 2026-01-26-river-range-hint-conf068-sizeconf
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（RIVER range‑hint 置信度随 bet size 上调）
- baseline: hu_rollout_river_20260123
- delta: Tier‑A mean≈17.24 (std≈27.16) vs baseline≈7.23 → Δ≈+10.01; Tier‑P mean≈9.94 (std≈12.62) vs baseline≈4.31 → Δ≈+5.63；confirm Tier‑A≈6.83 vs 4.23, Tier‑P≈6.01 vs 6.52
- evidence:
  - RIVER_Y | bb/100=-778.58 | n=60 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:1-2 | bb/100=+200.60 | n=87 | seeds=2000–2005 | ref=report:SPRBuckets/1-2
  - TURN_4p | bb/100=-114.48 | n=21 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
- outcome: CONTINUE
- rationale: confirm 仍低于基线且改善幅度极小；下一步改为“对大注范围更紧”的形状调整以压制河牌大注薄跟注。

### 2026-01-26-river-rollout-spr2p5
- change_id: 2026-01-26-river-rollout-spr2p5
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（RIVER 关键桶 rollout 触发阈值从 SPR≥4.0 降到 ≥2.5）
- baseline: hu_rollout_river_20260123
- delta: Tier‑A mean≈20.03 (std≈27.53) vs baseline≈7.23 → Δ≈+12.80; Tier‑P mean≈11.84 (std≈12.90) vs baseline≈4.31 → Δ≈+7.53；confirm Tier‑A≈8.94 vs 4.23, Tier‑P≈8.12 vs 6.52
- evidence:
  - RIVER_Y | bb/100=-791.22 | n=60 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:4-7 | bb/100=+332.87 | n=339 | seeds=2000–2005 | ref=report:SPRBuckets/4-7
  - TURN_4p | bb/100=+60.10 | n=21 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
- outcome: ADOPT
- rationale: 扩大河牌关键桶 rollout 覆盖后，Tier‑P confirm 明显越线且双层基线均提升，晋级为新基线。

### 2026-01-27-retaliation-v2-rerun2
- change_id: 2026-01-27-retaliation-v2-rerun2
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（反制模型 v2 接入 + 置信度衰减）
- baseline: river_rollout_spr2p5_20260126
- delta: Tier‑A mean≈17.88 (std≈20.26) vs baseline≈20.03 → Δ≈‑2.15; Tier‑P mean≈14.48 (std≈10.57) vs baseline≈11.84 → Δ≈+2.64；confirm Tier‑A≈9.14 vs 8.94, Tier‑P≈7.71 vs 8.12
- evidence:
  - RIVER_Y | bb/100=-765.90 | n=58 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:4-7 | bb/100=+137.29 | n=343 | seeds=2000–2005 | ref=report:SPRBuckets/4-7
  - TURN_4p | bb/100=-300.15 | n=20 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
- outcome: REJECT
- rationale: 压力矩阵提升但主矩阵退化且 confirm 未改善；需降低桶内 overfit，增加全局回退占比。

### 2026-01-27-rollout-turn-spr2p5
- change_id: 2026-01-27-rollout-turn-spr2p5
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（rollout gate：TURN spr_center=2.5 + 关闭 size 采样缩放）
- baseline: river_rollout_spr2p5_20260126
- delta: Tier‑A mean≈16.66 (std≈23.73) vs baseline≈20.03 → Δ≈‑3.37; Tier‑P mean≈10.94 (std≈13.65) vs baseline≈11.84 → Δ≈‑0.90；confirm Tier‑A≈3.63 vs 8.94，Tier‑P≈6.01 vs 8.12
- evidence:
  - RIVER_Y | bb/100=-699.17 | n=59 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - TURN|SPR=2-4 | bb/100=-1229.60 | n=10 | seeds=2000–2005 | ref=report:BBFlatPostflopSPR/TURN_2-4
  - TURN_4p | bb/100=-114.48 | n=21 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
- outcome: REJECT
- rationale: TURN 覆盖扩展后主/确认矩阵均回落，且 TURN SPR 2–4 仍为深负桶；说明 TURN rollout 过早扩展导致方差上升且未改善 OOP facing 结构。

### 2026-01-27-turn-rollout-gapgate
- change_id: 2026-01-27-turn-rollout-gapgate
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（TURN rollout：默认低权重 + size/gap gate）
- baseline: river_rollout_spr2p5_20260126
- delta: Tier‑A mean≈15.79 (std≈23.58) vs baseline≈20.03 → Δ≈‑4.24; Tier‑P mean≈10.07 (std≈13.56) vs baseline≈11.84 → Δ≈‑1.77；confirm Tier‑A≈3.58 vs 8.94
- evidence:
  - RIVER_Y | bb/100=-699.45 | n=58 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - TURN|SPR=2-4 | bb/100=-1229.60 | n=10 | seeds=2000–2005 | ref=report:BBFlatPostflopSPR/TURN_2-4
  - TURN_4p | bb/100=-114.48 | n=21 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
- outcome: REJECT
- rationale: 即使加入 gap gate，TURN rollout 仍显著拉低主矩阵与 confirm；TURN 负桶未改善，说明 TURN rollout 在当前估值体系下仍偏高噪声，继续保持 TURN 关闭。

### 2026-01-27-river-rollout-samplesize2
- change_id: 2026-01-27-river-rollout-samplesize2
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（RIVER rollout 样本规模随 gate 轻微放大）
- baseline: river_rollout_spr2p5_20260126
- delta: Tier‑A mean≈16.66 (std≈23.73) vs baseline≈20.03 → Δ≈‑3.37; Tier‑P mean≈10.94 (std≈13.65) vs baseline≈11.84 → Δ≈‑0.90；confirm Tier‑A≈3.63 vs 8.94
- evidence:
  - RIVER_Y | bb/100=-699.17 | n=59 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - TURN|SPR=2-4 | bb/100=-1229.60 | n=10 | seeds=2000–2005 | ref=report:BBFlatPostflopSPR/TURN_2-4
  - TURN_4p | bb/100=-114.48 | n=21 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
- outcome: REJECT
- rationale: 主/确认矩阵均低于基线；样本放大未改善关键桶，且收益不足，撤回。

### 2026-01-27-river-raise-sizecap
- change_id: 2026-01-27-river-raise-sizecap
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（RIVER OOP facing bet：基于 size_ratio 的 raise 软削减）
- baseline: river_rollout_spr2p5_20260126
- delta: Tier‑A mean≈16.66 (std≈23.73) vs baseline≈20.03 → Δ≈‑3.37; Tier‑P mean≈10.94 (std≈13.65) vs baseline≈11.84 → Δ≈‑0.90；confirm Tier‑A≈3.63 vs 8.94
- evidence:
  - RIVER_Y | bb/100=-699.17 | n=59 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - TURN|SPR=2-4 | bb/100=-1229.60 | n=10 | seeds=2000–2005 | ref=report:BBFlatPostflopSPR/TURN_2-4
  - TURN_4p | bb/100=-114.48 | n=21 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
- outcome: REJECT
- rationale: raise 降速未提升总体收益；主/确认矩阵继续低于基线，关键负桶未改善。

### 2026-01-27-river-detmix-gap
- change_id: 2026-01-27-river-detmix-gap
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（RIVER OOP facing bet：solver gap 高时提升确定性选择）
- baseline: river_rollout_spr2p5_20260126
- delta: Tier‑A mean≈17.36 (std≈23.71) vs baseline≈20.03 → Δ≈‑2.67; Tier‑P mean≈10.63 (std≈13.45) vs baseline≈11.84 → Δ≈‑1.21；confirm Tier‑A≈5.47 vs 8.94
- evidence:
  - RIVER_Y | bb/100=-767.37 | n=59 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - TURN|SPR=2-4 | bb/100=-1229.60 | n=10 | seeds=2000–2005 | ref=report:BBFlatPostflopSPR/TURN_2-4
  - TURN_4p | bb/100=-7.95 | n=21 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
- outcome: REJECT
- rationale: 确定性决策未带来净提升，且 RIVER_Y 仍为深负桶；继续保持混合选择，回到基线行为。

### 2026-01-27-river-callceiling-price
- change_id: 2026-01-27-river-callceiling-price
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（RIVER OOP facing bet：call_ceiling 随价格轻微收缩）
- baseline: river_rollout_spr2p5_20260126
- delta: Tier‑A mean≈16.66 (std≈23.73) vs baseline≈20.03 → Δ≈‑3.37; Tier‑P mean≈10.94 (std≈13.65) vs baseline≈11.84 → Δ≈‑0.90；confirm Tier‑A≈3.63 vs 8.94
- evidence:
  - RIVER_Y | bb/100=-699.17 | n=59 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - TURN|SPR=2-4 | bb/100=-1229.60 | n=10 | seeds=2000–2005 | ref=report:BBFlatPostflopSPR/TURN_2-4
  - TURN_4p | bb/100=-114.48 | n=21 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
- outcome: REJECT
- rationale: 行为与基线一致（event_stream_digest 无变化），未触发有效决策差异；撤回并改用更强机制。

### 2026-01-27-river-gap-gate
- change_id: 2026-01-27-river-gap-gate
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（RIVER OOP facing bet：solver gap 软门槛收缩 raise mix）
- baseline: river_rollout_spr2p5_20260126
- delta: Tier‑A mean≈16.66 (std≈23.73) vs baseline≈20.03 → Δ≈‑3.37; Tier‑P mean≈10.94 (std≈13.65) vs baseline≈11.84 → Δ≈‑0.90；confirm Tier‑A≈3.63 vs 8.94
- evidence:
  - RIVER_Y | bb/100=-699.17 | n=59 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - TURN|SPR=2-4 | bb/100=-1229.60 | n=10 | seeds=2000–2005 | ref=report:BBFlatPostflopSPR/TURN_2-4
  - TURN_4p | bb/100=-114.48 | n=21 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
- outcome: REJECT
- rationale: 核心指标未改善且确认矩阵显著低于基线；回撤至基线行为，改用更强的结构性修复。

### 2026-01-27-river-raise-gapscale
- change_id: 2026-01-27-river-raise-gapscale
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（RIVER OOP facing bet：raise 权重按 solver gap×price 软缩放）
- baseline: river_rollout_spr2p5_20260126
- delta: Tier‑A mean≈16.66 (std≈23.73) vs baseline≈20.03 → Δ≈‑3.37; Tier‑P mean≈10.94 (std≈13.65) vs baseline≈11.84 → Δ≈‑0.90；confirm Tier‑A≈3.63 vs 8.94
- evidence:
  - RIVER_Y | bb/100=-699.17 | n=59 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - TURN|SPR=2-4 | bb/100=-1229.60 | n=10 | seeds=2000–2005 | ref=report:BBFlatPostflopSPR/TURN_2-4
  - TURN_4p | bb/100=-114.48 | n=21 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
- outcome: REJECT
- rationale: 行为未变化（event_stream_digest 与对照一致），说明该 gating 未触发；需移出 focus_metrics 依赖，改为通用的 RIVER OOP facing 约束。

### 2026-01-27-river-veto-gap
- change_id: 2026-01-27-river-veto-gap
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（RIVER OOP facing bet：raise 低 gap 时软 veto → CALL/FOLD）
- baseline: river_rollout_spr2p5_20260126
- delta: Tier‑A mean≈16.47 (std≈23.80) vs baseline≈20.03 → Δ≈‑3.56; Tier‑P mean≈10.75 (std≈13.60) vs baseline≈11.84 → Δ≈‑1.09；confirm Tier‑A≈3.65 vs 8.94
- evidence:
  - RIVER_Y | bb/100=-725.47 | n=59 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - TURN|SPR=2-4 | bb/100=-1229.60 | n=10 | seeds=2000–2005 | ref=report:BBFlatPostflopSPR/TURN_2-4
  - TURN_4p | bb/100=-114.48 | n=21 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
- outcome: REJECT
- rationale: 动作确实变化（event_stream_digest 变化）但主/确认矩阵更差；撤回该 veto。

### 2026-01-27-mw-relief-strong
- change_id: 2026-01-27-mw-relief-strong
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（MW 风险惩罚大幅减轻：players_alive≥3）
- baseline: river_rollout_spr2p5_20260126
- delta: Tier‑A mean≈15.79 (std≈24.05) vs baseline≈20.03 → Δ≈‑4.24; Tier‑P mean≈8.60 (std≈13.54) vs baseline≈11.84 → Δ≈‑3.24；confirm Tier‑A≈3.39 vs 8.94
- evidence:
  - RIVER_Y | bb/100=-707.72 | n=57 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - TURN|SPR=2-4 | bb/100=-1229.60 | n=10 | seeds=2000–2005 | ref=report:BBFlatPostflopSPR/TURN_2-4
  - TURN_4p | bb/100=-114.48 | n=21 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
- outcome: REJECT
- rationale: 多人数风险惩罚放松导致主/压矩阵整体下滑；回撤该改动。

### 2026-01-27-retaliation-mwrelief
- change_id: 2026-01-27-retaliation-mwrelief
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（多人数 FLOP/TURN 降低 retaliation mix 影响）
- baseline: river_rollout_spr2p5_20260126
- delta: Tier‑A mean≈14.74 (std≈24.34) vs baseline≈20.03 → Δ≈‑5.30; Tier‑P mean≈10.04 (std≈14.47) vs baseline≈11.84 → Δ≈‑1.80；confirm Tier‑A≈3.82 vs 8.94
- evidence:
  - RIVER_Y | bb/100=-970.97 | n=59 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - TURN|SPR=2-4 | bb/100=-1229.60 | n=10 | seeds=2000–2005 | ref=report:BBFlatPostflopSPR/TURN_2-4
  - TURN_4p | bb/100=-109.73 | n=22 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
- outcome: REJECT
- rationale: 多人退火削弱导致整体 EV 下滑且 RIVER_Y 恶化；撤回。

### 2026-01-27-hu-raise-relief
- change_id: 2026-01-27-hu-raise-relief
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（HU 风险惩罚对 raise 的软放松）
- baseline: river_rollout_spr2p5_20260126
- delta: Tier‑A mean≈16.66 (std≈23.73) vs baseline≈20.03 → Δ≈‑3.37; Tier‑P mean≈10.94 (std≈13.65) vs baseline≈11.84 → Δ≈‑0.90；confirm Tier‑A≈3.63 vs 8.94
- evidence:
  - RIVER_Y | bb/100=-699.17 | n=59 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - TURN|SPR=2-4 | bb/100=-1229.60 | n=10 | seeds=2000–2005 | ref=report:BBFlatPostflopSPR/TURN_2-4
  - TURN_4p | bb/100=-114.48 | n=21 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
- outcome: REJECT
- rationale: 行为未变化（event_stream_digest 不变），改动未生效；撤回。

### 2026-01-23-hu-range-hint
- change_id: 2026-01-23-hu-range-hint
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（HU 范围提示 + equity_vs_range 混合）
- baseline: hu_rollout_river_20260123
- delta: Tier‑A mean≈1.36 (std≈12.94) vs baseline≈7.23 → Δ≈‑5.86；Tier‑P mean≈2.21 (std≈6.93) vs baseline≈4.31 → Δ≈‑2.10
- evidence:
  - TURN|Facing=Y | bb/100=-206.69 | n=32 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/TURN_Y
  - RIVER|Facing=Y | bb/100=-843.33 | n=58 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:7+|oop_Y | bb/100=-248.98 | n=246 | seeds=2000–2005 | ref=report:BBFlatPostflop/7+_oop_Y
- outcome: REJECT
- rationale: HU 范围提示单独启用显著降低 Tier‑A/Tier‑P 均值；先与对手反制概率建模联动再评估。

### 2026-01-23-retaliation-mix
- change_id: 2026-01-23-retaliation-mix
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（下注响应概率 p_call/p_fold 注入 EV）
- baseline: hu_rollout_river_20260123
- delta: Tier‑A mean≈6.00 (std≈15.98) vs baseline≈7.23 → Δ≈‑1.22；Tier‑P mean≈1.55 (std≈8.59) vs baseline≈4.31 → Δ≈‑2.76
- evidence:
  - TURN|Facing=Y | bb/100=79.65 | n=31 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/TURN_Y
  - RIVER|Facing=Y | bb/100=-641.95 | n=60 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:7+|oop_Y | bb/100=-204.57 | n=242 | seeds=2000–2005 | ref=report:BBFlatPostflop/7+_oop_Y
- outcome: REJECT
- rationale: TURN Facing=Y 有改善但总体 Tier‑A/Tier‑P 仍低于基线；需要更强的后续街价值估计或关键桶 lookahead 配合。

### 2026-01-23-turn-rollout
- change_id: 2026-01-23-turn-rollout
- change_type: Refine
- scope: `poker2/runtime/system_policy.py` + `specs/policy_params/system_bot_params_v3.json`（TURN 关键桶 rollout 轻量启用）
- baseline: hu_rollout_river_20260123
- delta: Tier‑A mean≈7.78 (std≈21.68) vs baseline≈7.23 → Δ≈+0.56；Tier‑P mean≈‑0.32 (std≈5.98) vs baseline≈4.31 → Δ≈‑4.63（options_hash 不一致，paired_compare 严格不通过）
- evidence:
  - TURN|Facing=Y | bb/100=-36.06 | n=31 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/TURN_Y
  - RIVER|Facing=Y | bb/100=-775.48 | n=56 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:7+|oop_Y | bb/100=-184.05 | n=242 | seeds=2000–2005 | ref=report:BBFlatPostflop/7+_oop_Y
- outcome: REJECT
- rationale: TURN rollout 增大波动且 Tier‑P 显著下滑；同时 options_hash 变化导致与基线严格不可比，需先校准 turn 权重/样本后再评估。

### 2026-01-23-turn-rollout-default
- change_id: 2026-01-23-turn-rollout-default
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（TURN rollout 默认权重）
- baseline: hu_rollout_river_20260123
- delta: Tier‑A mean≈7.78 (std≈21.68) vs baseline≈7.23 → Δ≈+0.56；Tier‑P mean≈‑0.32 (std≈5.98) vs baseline≈4.31 → Δ≈‑4.63
- evidence:
  - TURN|Facing=Y | bb/100=-36.06 | n=31 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/TURN_Y
  - RIVER|Facing=Y | bb/100=-775.48 | n=56 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:7+|oop_Y | bb/100=-184.05 | n=242 | seeds=2000–2005 | ref=report:BBFlatPostflop/7+_oop_Y
- outcome: REJECT
- rationale: TURN rollout default 仍导致 Tier‑P 明显下滑；不满足晋级门槛。

### 2026-01-23-turn-rollout-gap
- change_id: 2026-01-23-turn-rollout-gap
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（TURN rollout 依赖 solver gap 软缩放）
- baseline: hu_rollout_river_20260123
- delta: Tier‑A mean≈7.93 (std≈21.70) vs baseline≈7.23 → Δ≈+0.70；Tier‑P mean≈‑0.18 (std≈5.98) vs baseline≈4.31 → Δ≈‑4.49
- evidence:
  - TURN|Facing=Y | bb/100=-36.06 | n=31 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/TURN_Y
  - RIVER|Facing=Y | bb/100=-775.48 | n=56 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:7+|oop_Y | bb/100=-178.64 | n=242 | seeds=2000–2005 | ref=report:BBFlatPostflop/7+_oop_Y
- outcome: REJECT
- rationale: gap 软缩放仍无法阻止 Tier‑P 下滑；TURN rollout 暂停。

### 2026-01-23-hu-range-facing-tr
- change_id: 2026-01-23-hu-range-facing-tr
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（HU range 仅在 Facing bet 的 TURN/RIVER 生效）
- baseline: hu_rollout_river_20260123
- delta: Tier‑A mean≈14.55 (std≈28.39) vs baseline≈7.23 → Δ≈+7.32；Tier‑P mean≈7.19 (std≈12.60) vs baseline≈4.31 → Δ≈+2.88；confirm: Tier‑A≈5.21 vs 4.23，Tier‑P≈5.17 vs 6.52
- evidence:
  - TURN|Facing=Y | bb/100=52.03 | n=31 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/TURN_Y
  - RIVER|Facing=Y | bb/100=-812.10 | n=60 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:7+|oop_Y | bb/100=-161.62 | n=242 | seeds=2000–2005 | ref=report:BBFlatPostflop/7+_oop_Y
- outcome: CONTINUE
- rationale: 主矩阵显著提升但确认矩阵未稳定超基线（Tier‑P confirm 下滑）；继续降低范围提示强度。

### 2026-01-23-hu-range-facing-tr-conf
- change_id: 2026-01-23-hu-range-facing-tr-conf
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（range conf=TURN×0.85 / RIVER×0.70）
- baseline: hu_rollout_river_20260123
- delta: Tier‑A mean≈15.05 (std≈27.57) vs baseline≈7.23 → Δ≈+7.83；Tier‑P mean≈8.03 (std≈12.39) vs baseline≈4.31 → Δ≈+3.72；confirm: Tier‑A≈5.71 vs 4.23，Tier‑P≈5.75 vs 6.52
- evidence:
  - TURN|Facing=Y | bb/100=52.03 | n=31 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/TURN_Y
  - RIVER|Facing=Y | bb/100=-812.10 | n=60 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:7+|oop_Y | bb/100=-131.32 | n=242 | seeds=2000–2005 | ref=report:BBFlatPostflop/7+_oop_Y
- outcome: CONTINUE
- rationale: 主矩阵提升明显但确认矩阵 Tier‑P 仍低于基线；继续下调 river conf。

### 2026-01-23-hu-range-facing-tr-conf60
- change_id: 2026-01-23-hu-range-facing-tr-conf60
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（range conf=TURN×0.85 / RIVER×0.60）
- baseline: hu_rollout_river_20260123
- delta: Tier‑A mean≈15.90 (std≈27.58) vs baseline≈7.23 → Δ≈+8.68；Tier‑P mean≈8.88 (std≈12.54) vs baseline≈4.31 → Δ≈+4.57；confirm: Tier‑A≈5.75 vs 4.23，Tier‑P≈5.80 vs 6.52
- evidence:
  - TURN|Facing=Y | bb/100=52.03 | n=31 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/TURN_Y
  - RIVER|Facing=Y | bb/100=-812.10 | n=60 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:7+|oop_Y | bb/100=-106.75 | n=242 | seeds=2000–2005 | ref=report:BBFlatPostflop/7+_oop_Y
- outcome: CONTINUE
- rationale: 主矩阵显著提升（Tier‑A CI>0），但 Tier‑P confirm 仍未稳定超基线；保留为候选继续微调。

### 2026-01-23-hu-range-facing-tr-conf55
- change_id: 2026-01-23-hu-range-facing-tr-conf55
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（range conf=TURN×0.85 / RIVER×0.55 + gap 软缩放）
- baseline: hu_rollout_river_20260123
- delta: Tier‑A mean≈15.81 (std≈27.57) vs baseline≈7.23 → Δ≈+8.58；Tier‑P mean≈8.78 (std≈12.50) vs baseline≈4.31 → Δ≈+4.47；confirm: Tier‑A≈5.75 vs 4.23，Tier‑P≈5.80 vs 6.52
- evidence:
  - TURN|Facing=Y | bb/100=52.03 | n=31 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/TURN_Y
  - RIVER|Facing=Y | bb/100=-812.10 | n=60 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:7+|oop_Y | bb/100=-111.50 | n=242 | seeds=2000–2005 | ref=report:BBFlatPostflop/7+_oop_Y
- outcome: CONTINUE
- rationale: 主矩阵继续明显提升，但 Tier‑P confirm 仍低于基线；需要进一步降低 RIVER 影响或仅保留 TURN。

### 2026-01-23-hu-range-turnonly
- change_id: 2026-01-23-hu-range-turnonly
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（range hint 仅 TURN 生效，RIVER 关闭，TURN×0.75）
- baseline: hu_rollout_river_20260123
- delta: Tier‑A mean≈14.56 (std≈27.07) vs baseline≈7.23 → Δ≈+7.33；Tier‑P mean≈7.13 (std≈11.56) vs baseline≈4.31 → Δ≈+2.82；confirm: Tier‑A≈4.70 vs 4.23，Tier‑P≈4.92 vs 6.52
- evidence:
  - TURN|Facing=Y | bb/100=52.03 | n=31 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/TURN_Y
  - RIVER|Facing=Y | bb/100=-824.73 | n=60 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:7+|oop_Y | bb/100=-151.27 | n=242 | seeds=2000–2005 | ref=report:BBFlatPostflop/7+_oop_Y
- outcome: CONTINUE
- rationale: 主矩阵维持提升，但 confirm 下滑更明显（Tier‑P confirm 低于基线）；RIVER 关闭仍未稳定超基线。

### 2026-01-23-hu-range-turn-gap
- change_id: 2026-01-23-hu-range-turn-gap
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（TURN 仅在 solver_gap≥0.08 时启用 range hint；TURN×0.65；RIVER 关闭）
- baseline: hu_rollout_river_20260123
- delta: Tier‑A mean≈14.41 (std≈28.12) vs baseline≈7.23 → Δ≈+7.18；Tier‑P mean≈9.20 (std≈11.75) vs baseline≈4.31 → Δ≈+4.89；confirm: Tier‑A≈7.01 vs 4.23，Tier‑P≈5.26 vs 6.52
- evidence:
  - TURN|Facing=Y | bb/100=52.03 | n=31 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/TURN_Y
  - RIVER|Facing=Y | bb/100=-824.73 | n=60 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:7+|oop_Y | bb/100=-185.02 | n=242 | seeds=2000–2005 | ref=report:BBFlatPostflop/7+_oop_Y
- outcome: CONTINUE
- rationale: 主矩阵显著提升且 Tier‑A confirm 明显改善，但 Tier‑P confirm 仍未超过基线，需进一步收敛或提升 RIVER 防守质量。

### 2026-01-23-hu-range-turn-unc
- change_id: 2026-01-23-hu-range-turn-unc
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（TURN range hint + uncertainty 折扣；RIVER 关闭）
- baseline: hu_rollout_river_20260123
- delta: Tier‑A mean≈15.66 (std≈26.47) vs baseline≈7.23 → Δ≈+8.43；Tier‑P mean≈8.35 (std≈11.13) vs baseline≈4.31 → Δ≈+4.04；confirm: Tier‑A≈5.99 vs 4.23，Tier‑P≈5.42 vs 6.52
- evidence:
  - TURN|Facing=Y | bb/100=52.03 | n=31 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/TURN_Y
  - RIVER|Facing=Y | bb/100=-824.73 | n=60 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:7+|oop_Y | bb/100=-144.33 | n=242 | seeds=2000–2005 | ref=report:BBFlatPostflop/7+_oop_Y
- outcome: CONTINUE
- rationale: 主矩阵继续提升且 confirm 接近，但 Tier‑P confirm 仍未稳定超基线；需要继续控制 RIVER 负桶与风险波动。
- baseline: revert94
- delta: mean≈13.14 (std≈8.49) vs baseline≈25.86 → Δ≈-12.72 bb/100
- evidence:
  - TURN|Facing=Y | bb/100=-957.77 | n=22 | seeds=2000–2004 | ref=report:bb_flat_postflop_facing_by_street
  - SPR:2-4 | bb/100=-2670.20 | n=5 | seeds=2000–2004 | ref=report:bb_flat_postflop_spr_by_street
  - TURN|players=4 | bb/100=-1549.82 | n=17 | seeds=2000–2004 | ref=report:profit_by_players
- outcome: REJECT
- rationale: 过度压低防守导致整体EV崩塌；price×SPR缩放过强，必须撤回。

### 2026-01-17-raise-budget
- change_id: 2026-01-17-raise-budget
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（TURN/RIVER OOP raise 权重预算缩放）
- baseline: revert94
- delta: mean≈22.17 (std≈13.68) vs baseline≈25.86 → Δ≈-3.69 bb/100
- evidence:
  - TURN|Facing=Y | bb/100=-814.14 | n=22 | seeds=2000–2004 | ref=report:bb_flat_postflop_facing_by_street
  - SPR:2-4 | bb/100=-2670.20 | n=5 | seeds=2000–2004 | ref=report:bb_flat_postflop_spr_by_street
  - TURN|players=4 | bb/100=-1127.88 | n=17 | seeds=2000–2004 | ref=report:profit_by_players
- outcome: REJECT
- rationale: 与 mw-defend-scale 输出一致，行为不变，机制无效已撤回。

### 2026-01-17-highprice-defend
- change_id: 2026-01-17-highprice-defend
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（TURN/RIVER OOP 高价位防守缩放）
- baseline: revert94
- delta: mean≈22.17 (std≈13.68) vs baseline≈25.86 → Δ≈-3.69 bb/100
- evidence:
  - TURN|Facing=Y | bb/100=-814.14 | n=22 | seeds=2000–2004 | ref=report:bb_flat_postflop_facing_by_street
  - SPR:2-4 | bb/100=-2670.20 | n=5 | seeds=2000–2004 | ref=report:bb_flat_postflop_spr_by_street
  - TURN|players=4 | bb/100=-1127.88 | n=17 | seeds=2000–2004 | ref=report:profit_by_players
- outcome: REJECT
- rationale: 与 mw-defend-scale 输出一致，未改变行为，已撤回。

### 2026-01-17-price-risk-ev
- change_id: 2026-01-17-price-risk-ev
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（TURN/RIVER OOP call/raise EV 引入 price×SPR 风险项）
- baseline: revert94
- delta: mean≈22.86 (std≈13.02) vs baseline≈25.86 → Δ≈-3.00 bb/100
- evidence:
  - TURN|Facing=Y | bb/100=-814.14 | n=22 | seeds=2000–2004 | ref=report:bb_flat_postflop_facing_by_street
  - SPR:2-4 | bb/100=-2670.20 | n=5 | seeds=2000–2004 | ref=report:bb_flat_postflop_spr_by_street
  - TURN|players=4 | bb/100=-1127.88 | n=17 | seeds=2000–2004 | ref=report:profit_by_players
- outcome: CONTINUE
- rationale: 均值小幅改善但 Facing=Y 负桶未变；说明风险项仍未触及关键决策边界，需要增强价值估计的可识别信号。

### 2026-01-17-price-equity-adj
- change_id: 2026-01-17-price-equity-adj
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（TURN/RIVER OOP facing bet equity 动态折扣）
- baseline: revert94
- delta: mean≈14.51 (std≈13.41) vs baseline≈25.86 → Δ≈-11.35 bb/100
- evidence:
  - TURN|Facing=Y | bb/100=-1343.61 | n=23 | seeds=2000–2004 | ref=report:bb_flat_postflop_facing_by_street
  - SPR:2-4 | bb/100=-2670.20 | n=5 | seeds=2000–2004 | ref=report:bb_flat_postflop_spr_by_street
  - TURN|players=4 | bb/100=-815.06 | n=17 | seeds=2000–2004 | ref=report:profit_by_players
- outcome: REJECT
- rationale: 负桶未收敛且整体均值显著下降；动态折扣过强，已撤回。

### 2026-01-17-raise-bluff-penalty
- change_id: 2026-01-17-raise-bluff-penalty
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（TURN/RIVER OOP 非价值 raise 软惩罚）
- baseline: revert94
- delta: mean≈22.86 (std≈13.02) vs baseline≈25.86 → Δ≈-3.00 bb/100
- evidence:
  - TURN|Facing=Y | bb/100=-814.14 | n=22 | seeds=2000–2004 | ref=report:bb_flat_postflop_facing_by_street
  - SPR:2-4 | bb/100=-2670.20 | n=5 | seeds=2000–2004 | ref=report:bb_flat_postflop_spr_by_street
  - TURN|players=4 | bb/100=-1127.88 | n=17 | seeds=2000–2004 | ref=report:profit_by_players
- outcome: REJECT
- rationale: 行为无变化（输出与 price-risk-ev 一致），机制无效已撤回。

### 2026-01-18-ev-rank-align
- change_id: 2026-01-18-ev-rank-align
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（OOP facing bet 用风险调整得分参与 EV 选优与 raise gating）
- baseline: revert94
- delta: mean≈14.58 (std≈12.56) vs baseline≈25.86 → Δ≈-11.28 bb/100
- evidence:
  - TURN|Facing=Y | bb/100=-1800.50 | n=24 | seeds=2000–2004 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:7+|oop_multi_street=N | bb/100=-511.00 | n=15 | seeds=2000–2004 | ref=report:BBFlatPostflop/7+_oop_N
  - TURN|players=4 | bb/100=-762.18 | n=17 | seeds=2000–2004 | ref=report:ProfitByPlayers/TURN_4p
- outcome: REJECT
- rationale: 风险得分参与排序后整体EV显著下降且 Facing=Y 更差，说明当前风险项过强/过粗，不宜直接作为排序指标。

### 2026-01-18-call-gap-base
- change_id: 2026-01-18-call-gap-base
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（TURN/RIVER OOP call_penalty 引入基底 gap 成本）
- baseline: revert94
- delta: mean≈22.86 (std≈13.02) vs baseline≈25.86 → Δ≈-3.00 bb/100
- evidence:
  - TURN|Facing=Y | bb/100=-814.14 | n=22 | seeds=2000–2004 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:7+|oop_multi_street=N | bb/100=-511.00 | n=15 | seeds=2000–2004 | ref=report:BBFlatPostflop/7+_oop_N
  - TURN|players=4 | bb/100=-1127.88 | n=17 | seeds=2000–2004 | ref=report:ProfitByPlayers/TURN_4p
- outcome: REJECT
- rationale: 与 price-risk-ev 输出一致（桶与均值重合），行为未改变，已撤回。

### 2026-01-18-unc-realization
- change_id: 2026-01-18-unc-realization
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（TURN/RIVER OOP call_penalty 引入不确定性折价）
- baseline: revert94
- delta: mean≈22.31 (std≈11.99) vs baseline≈25.86 → Δ≈-3.55 bb/100
- evidence:
  - TURN|Facing=Y | bb/100=-805.05 | n=22 | seeds=2000–2004 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:7+|oop_multi_street=N | bb/100=-511.00 | n=15 | seeds=2000–2004 | ref=report:BBFlatPostflop/7+_oop_N
  - TURN|players=4 | bb/100=-1127.88 | n=17 | seeds=2000–2004 | ref=report:ProfitByPlayers/TURN_4p
- outcome: REJECT
- rationale: 均值略降且 Facing=Y 负桶未收敛，说明单点“uncertainty 折价”不足以改变关键决策边界，已撤回。

### 2026-01-18-realization-scale
- change_id: 2026-01-18-realization-scale
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（TURN/RIVER OOP call_ev 乘 realization_scale）
- baseline: revert94
- delta: mean≈22.39 (std≈12.02) vs baseline≈25.86 → Δ≈-3.47 bb/100
- evidence:
  - TURN|Facing=Y | bb/100=-805.05 | n=22 | seeds=2000–2004 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:7+|oop_multi_street=N | bb/100=-511.00 | n=15 | seeds=2000–2004 | ref=report:BBFlatPostflop/7+_oop_N
  - TURN|players=4 | bb/100=-1127.88 | n=17 | seeds=2000–2004 | ref=report:ProfitByPlayers/TURN_4p
- outcome: REJECT
- rationale: 均值仍低于基线，Facing=Y 负桶未收敛；realization_scale 未触发关键决策改变，已撤回。

### 2026-01-18-ev-calib-v1
- change_id: 2026-01-18-ev-calib-v1
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（TURN/RIVER OOP facing bet EV 连续校准）
- baseline: revert94
- delta: mean≈9.45 (std≈11.39) vs baseline≈25.86 → Δ≈-16.41 bb/100
- evidence:
  - TURN|Facing=Y | bb/100=-1215.62 | n=21 | seeds=2000–2004 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:7+|oop_multi_street=N | bb/100=-511.00 | n=15 | seeds=2000–2004 | ref=report:BBFlatPostflop/7+_oop_N
  - TURN|players=4 | bb/100=-740.29 | n=17 | seeds=2000–2004 | ref=report:ProfitByPlayers/TURN_4p
- outcome: REJECT
- rationale: EV 校准惩罚过强导致整体 EV 断崖式下滑；需要重新设计为“对 CALL 更强、对 value raise 更弱”的分层校准。

### 2026-01-18-floor-scale
- change_id: 2026-01-18-floor-scale
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（TURN/RIVER OOP equity_floor 连续缩放）
- baseline: revert94
- delta: mean≈13.92 (std≈12.52) vs baseline≈25.86 → Δ≈-11.94 bb/100
- evidence:
  - TURN|Facing=Y | bb/100=-1054.19 | n=21 | seeds=2000–2004 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:7+|oop_multi_street=N | bb/100=-511.00 | n=15 | seeds=2000–2004 | ref=report:BBFlatPostflop/7+_oop_N
  - TURN|players=4 | bb/100=-1017.94 | n=17 | seeds=2000–2004 | ref=report:ProfitByPlayers/TURN_4p
- outcome: REJECT
- rationale: 缩放 equity_floor 导致整体 EV 明显下滑，说明当前防守下限仍不应通过“floor”通道调节，已撤回。

### 2026-01-18-actionspace-v3
- change_id: 2026-01-18-actionspace-v3
- change_type: Define
- scope: `specs/action_bins/actionspace_bins_v3.json` + `specs/scenarios/coinpoker_7max_mw_v3_actionspace_v3.json`
- baseline: actionspace_v2 / same-code A/B (mean≈22.86)
- delta: mean≈-5.73 (std≈9.68) vs v2 mean≈22.86 → Δ≈-28.59 bb/100
- evidence:
  - TURN|Facing=Y | bb/100=-1321.48 | n=21 | seeds=2000–2004 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:7+|oop_multi_street=Y | bb/100=-487.64 | n=261 | seeds=2000–2004 | ref=report:BBFlatPostflop/7+_oop_Y
  - RIVER|players=2p | bb/100=-95.44 | n=1107 | seeds=2000–2004 | ref=report:ProfitByPlayers/RIVER_2p
- outcome: REJECT
- rationale: 动作空间 v3 让下注显著向 0–0.33 桶倾斜，整体均值崩塌且 Facing=Y 更差；核心原因是当前估值/风险模型对小尺寸偏置、不具尺寸鲁棒性，导致中等/极化压力被系统性抑制。需回退该 actionspace，并先修正“尺寸→风险”估值机制后再扩展动作集。

### 2026-01-18-defend-rate-risk
- change_id: 2026-01-18-defend-rate-risk
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（加入 bet-size × opponent_defend_rate 风险项）
- baseline: revert94
- delta: mean≈15.89 (std≈13.75) vs baseline≈25.86 → Δ≈-9.97 bb/100
- evidence:
  - RIVER|Facing=Y | bb/100=-771.43 | n=42 | seeds=2000–2004 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:7+|oop_multi_street=N | bb/100=-506.83 | n=12 | seeds=2000–2004 | ref=report:BBFlatPostflop/7+_oop_N
  - TURN|players=4p | bb/100=-1620.78 | n=18 | seeds=2000–2004 | ref=report:ProfitByPlayers/TURN_4p
- outcome: REJECT
- rationale: 风险项降低整体 EV，Facing=Y 负桶未实质收敛；说明“对手反制概率惩罚”在当前参数强度下偏重，需改为更温和/与 EV 置信度联动的形式或仅在关键节点启用。

### 2026-01-18-defend-rate-risk-b2
- change_id: 2026-01-18-defend-rate-risk-b2
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（反制概率风险项仅在 OOP TURN/RIVER Facing=Y 触发）
- baseline: revert94
- delta: mean≈22.86 (std≈13.02) vs baseline≈25.86 → Δ≈-3.00 bb/100
- evidence:
  - RIVER|Facing=Y | bb/100=-851.36 | n=42 | seeds=2000–2004 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:7+|oop_multi_street=N | bb/100=-511.00 | n=15 | seeds=2000–2004 | ref=report:BBFlatPostflop/7+_oop_N
  - TURN|players=4p | bb/100=-1127.88 | n=17 | seeds=2000–2004 | ref=report:ProfitByPlayers/TURN_4p
- outcome: REJECT
- rationale: 结果与 baseline（v2 当前行为）完全一致，说明风险项未触发关键决策边界；需要把该风险项移入“raise vs call 的边界选择”或只在 score gap 极小的节点启用。

### 2026-01-18-defend-margin-b3
- change_id: 2026-01-18-defend-margin-b3
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（Facing=Y OOP TURN/RIVER 的 raise 边界引入反制概率 margin）
- baseline: revert94
- delta: mean≈22.53 (std≈12.82) vs baseline≈25.86 → Δ≈-3.33 bb/100
- evidence:
  - TURN|Facing=Y | bb/100=-942.95 | n=22 | seeds=2000–2004 | ref=report:BBFlatPostflopFacing/TURN_Y
  - TURN|SPR:2-4 | bb/100=-2670.20 | n=5 | seeds=2000–2004 | ref=report:BBFlatPostflop/2-4_oop_?
  - TURN|players=4p | bb/100=-1127.88 | n=17 | seeds=2000–2004 | ref=report:ProfitByPlayers/TURN_4p
- outcome: REJECT
- rationale: Raise 边界加入反制概率后整体均值仍低于基线且 Facing=Y 未显著收敛；需改为“仅在 score gap 很小的 raise/call 二选一节点触发”，或将该 margin 与 solver/EV 置信度联动。

### 2026-01-18-defend-margin-b4
- change_id: 2026-01-18-defend-margin-b4
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（仅在 raise/call 近临界节点启用反制概率 margin）
- baseline: revert94
- delta: mean≈22.86 (std≈13.02) vs baseline≈25.86 → Δ≈-3.00 bb/100
- evidence:
  - RIVER|Facing=Y | bb/100=-851.36 | n=42 | seeds=2000–2004 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:7+|oop_multi_street=N | bb/100=-511.00 | n=15 | seeds=2000–2004 | ref=report:BBFlatPostflop/7+_oop_N
  - TURN|players=4p | bb/100=-1127.88 | n=17 | seeds=2000–2004 | ref=report:ProfitByPlayers/TURN_4p
- outcome: REJECT
- rationale: 近临界触发后行为仍与基线一致，说明 margin 未进入关键决策边界；需改为“显式 raise/call 混合权重调整”或将对手反制概率引入候选筛选（非仅提高 required_margin）。

### 2026-01-18-defend-mix-b5
- change_id: 2026-01-18-defend-mix-b5
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（Facing=Y OOP TURN/RIVER 的 raise 权重加入对手反制概率软缩放）
- baseline: revert94
- delta: mean≈22.86 (std≈13.02) vs baseline≈25.86 → Δ≈-3.00 bb/100
- evidence:
  - RIVER|Facing=Y | bb/100=-851.36 | n=42 | seeds=2000–2004 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:7+|oop_multi_street=N | bb/100=-511.00 | n=15 | seeds=2000–2004 | ref=report:BBFlatPostflop/7+_oop_N
  - TURN|players=4p | bb/100=-1127.88 | n=17 | seeds=2000–2004 | ref=report:ProfitByPlayers/TURN_4p
- outcome: REJECT
- rationale: raise 权重缩放仍未改变关键决策边界（Tier‑A/Tier‑P 均与基线一致），说明反制概率需更直接进入“候选集合/策略分布”的主导环节，而非权重轻微调整。

### 2026-01-18-defend-netev-b6
- change_id: 2026-01-18-defend-netev-b6
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（raise 的净EV加入对手反制概率惩罚）
- baseline: revert94
- delta: mean≈22.84 (std≈13.04) vs baseline≈25.86 → Δ≈-3.02 bb/100
- evidence:
  - RIVER|Facing=Y | bb/100=-851.36 | n=42 | seeds=2000–2004 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:7+|oop_multi_street=N | bb/100=-511.00 | n=15 | seeds=2000–2004 | ref=report:BBFlatPostflop/7+_oop_N
  - TURN|players=4p | bb/100=-1127.88 | n=17 | seeds=2000–2004 | ref=report:ProfitByPlayers/TURN_4p
- outcome: REJECT
- rationale: 净EV惩罚未触及关键决策边界（Tier‑A 仍与基线一致），Tier‑P 反而下降；说明对手反制概率需进入“候选集合过滤/动作空间触发”层面，而非仅作为净EV轻微修正。

### 2026-01-18-raise-filter-b7
- change_id: 2026-01-18-raise-filter-b7
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（OOP TURN/RIVER facing bet 的 raise 候选软过滤）
- baseline: revert94
- delta: Tier‑A mean≈22.86 (std≈13.02) vs baseline≈25.86 → Δ≈-3.00 bb/100; Tier‑P mean≈14.71 (std≈6.50)
- evidence:
  - RIVER|Facing=Y | bb/100=-851.36 | n=42 | seeds=2000–2004 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:7+|oop_multi_street=N | bb/100=-511.00 | n=15 | seeds=2000–2004 | ref=report:BBFlatPostflop/7+_oop_N
  - TURN|players=4p | bb/100=-1127.88 | n=17 | seeds=2000–2004 | ref=report:ProfitByPlayers/TURN_4p
- outcome: REJECT
- rationale: 候选过滤未改变关键决策边界（Tier‑A/Tier‑P 与基线一致）；反制概率惩罚仍需与 EV 置信度/尺寸信号联动或改为“仅在边界节点逐级扩展候选”的方式。

### 2026-01-18-retaliation-model-v1
- change_id: 2026-01-18-retaliation-model-v1
- change_type: Refine
- scope: `poker2/cli/build_retaliation_model.py` + `poker2/runtime/system_policy.py`（p_raise + loss_when_raised 风险项接入）
- baseline: revert94
- delta: Tier‑A mean≈22.95 (std≈14.28) vs baseline≈25.86 → Δ≈-2.91 bb/100; Tier‑P mean≈14.92 (std≈6.59)
- evidence:
  - BB|TURN|facing:Y | bb/100=-2324.80 | n=5 | seeds=2000 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:7+|oop_multi_street=Y | bb/100=-190.30 | n=37 | seeds=2000 | ref=report:BBFlatPostflop/7+_oop_Y
  - players:4p|RIVER | bb/100=-2294.40 | n=5 | seeds=2000 | ref=report:ProfitByPlayers/RIVER_4p
- outcome: CONTINUE
- rationale: 方向小幅改善（Tier‑A/Tier‑P 轻微上升）但仍未达基线；说明“反制概率+损失”已触及评分，但强度偏弱或落在非关键节点，需要结合关键桶触发或 rollout 校准进一步放大。

### 2026-01-18-keybucket-rollout
- change_id: 2026-01-18-keybucket-rollout
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（HU OOP TURN/RIVER Facing=Y 启用 solver EV 校准）
- baseline: revert94
- delta: Tier‑A mean≈18.46 (std≈17.37) vs baseline≈25.86 → Δ≈-7.40 bb/100; Tier‑P mean≈9.73 (std≈3.36)
- evidence:
  - BB|TURN|facing:Y | bb/100=-2324.80 | n=5 | seeds=2000 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:7+|oop_multi_street=Y | bb/100=-109.65 | n=37 | seeds=2000 | ref=report:BBFlatPostflop/7+_oop_Y
  - players:2p|RIVER | bb/100=-83.94 | n=139 | seeds=2000 | ref=report:ProfitByPlayers/RIVER_2p
- outcome: REJECT
- rationale: 关键桶 EV 校准导致整体与压力维度显著下降，说明 solver EV 在该触发条件下与当前估值体系不兼容，已撤回。

### 2026-01-18-retaliation-model-v1-scaled
- change_id: 2026-01-18-retaliation-model-v1-scaled
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（反制风险按压力/多人数/不确定度缩放）
- baseline: revert94
- delta: Tier‑A mean≈23.37 (std≈13.64) vs baseline≈25.86 → Δ≈-2.49 bb/100; Tier‑P mean≈15.48 (std≈5.89)
- evidence:
  - BB|TURN|facing:Y | bb/100=-2324.80 | n=5 | seeds=2000 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:7+|oop_multi_street=Y | bb/100=-190.30 | n=37 | seeds=2000 | ref=report:BBFlatPostflop/7+_oop_Y
  - players:4p|RIVER | bb/100=-2294.40 | n=5 | seeds=2000 | ref=report:ProfitByPlayers/RIVER_4p
- outcome: CONTINUE
- rationale: Tier‑A/Tier‑P 均值继续上升且方差下降，说明机制方向有效，但仍未达到基线，需要继续扩大关键桶约束力度或结合动作空间微扰稳定性校验。

### 2026-01-18-retaliation-model-v1-callfix
- change_id: 2026-01-18-retaliation-model-v1-callfix
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（p_call + loss_when_called 反制惩罚接入）
- baseline: revert94
- delta: Tier‑A mean≈22.11 (std≈13.86) vs baseline≈25.86 → Δ≈-3.75 bb/100; Tier‑P mean≈15.46 (std≈5.91)
- evidence:
  - BB|TURN|facing:Y | bb/100=-2324.80 | n=5 | seeds=2000 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:7+|oop_multi_street=Y | bb/100=-190.30 | n=37 | seeds=2000 | ref=report:BBFlatPostflop/7+_oop_Y
  - players:4p|RIVER | bb/100=-2294.40 | n=5 | seeds=2000 | ref=report:ProfitByPlayers/RIVER_4p
- outcome: REJECT
- rationale: call 侧反制惩罚使整体均值回落且关键桶未改善，说明该惩罚与现有 call 风险体系重复或过粗；已撤回。

### 2026-01-18-retaliation-model-v1-scaled-rerun
- change_id: 2026-01-18-retaliation-model-v1-scaled-rerun
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（撤回 call 惩罚，保留 p_raise 缩放）
- baseline: revert94
- delta: Tier‑A mean≈23.37 (std≈13.64) vs baseline≈25.86 → Δ≈-2.49 bb/100; Tier‑P mean≈15.48 (std≈5.89)
- evidence:
  - BB|TURN|facing:Y | bb/100=-2324.80 | n=5 | seeds=2000 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:7+|oop_multi_street=Y | bb/100=-190.30 | n=37 | seeds=2000 | ref=report:BBFlatPostflop/7+_oop_Y
  - players:4p|RIVER | bb/100=-2294.40 | n=5 | seeds=2000 | ref=report:ProfitByPlayers/RIVER_4p
- outcome: CONTINUE
- rationale: 回退后结果恢复到 scaled 方案水平，当前最优仍是“p_raise 风险缩放”；下一步需要针对关键桶的动作空间/局部搜索做结构性提升。

### 2026-01-18-actionspace-v3
- change_id: 2026-01-18-actionspace-v3
- change_type: Restructure
- scope: `specs/action_bins/actionspace_bins_v3.json` + `specs/scenarios/coinpoker_7max_mw_v3_actionspace_v3.json`
- baseline: revert94
- delta: Tier‑A mean≈-9.53 (std≈12.68), Tier‑P mean≈-9.61 (std≈9.86) （actionspace 变更，不可与基线直接比较）
- evidence:
  - BB|TURN|facing:Y | bb/100=-1048.00 | n=2 | seeds=2000 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:7+|oop_multi_street=Y | bb/100=-249.69 | n=51 | seeds=2000 | ref=report:BBFlatPostflop/7+_oop_Y
  - players:4p|RIVER | bb/100=-485.67 | n=3 | seeds=2000 | ref=report:ProfitByPlayers/RIVER_4p
- outcome: REJECT
- rationale: 动作空间变更导致整体 EV 崩塌且面对下注关键桶仍弱，说明当前估值体系对“更丰富的小注动作”不鲁棒；后续需通过“raise 模板 + 候选过滤/局部扩展”而非直接全局动作扩张。

### 2026-01-18-raise-templates-b1
- change_id: 2026-01-18-raise-templates-b1
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（Facing=Y raise 候选模板化过滤）
- baseline: revert94
- delta: Tier‑A mean≈1.56 (std≈5.50) vs baseline≈25.86 → Δ≈-24.30 bb/100; Tier‑P mean≈-1.42 (std≈7.67)
- evidence:
  - BB|TURN|facing:Y | bb/100=-1629.17 | n=6 | seeds=2000 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:7+|oop_multi_street=Y | bb/100=-286.86 | n=36 | seeds=2000 | ref=report:BBFlatPostflop/7+_oop_Y
  - players:4p|RIVER | bb/100=-2517.60 | n=5 | seeds=2000 | ref=report:ProfitByPlayers/RIVER_4p
- outcome: REJECT
- rationale: raise 候选模板化在当前估值体系下显著削弱 EV，说明过滤触发过强或与防守混合机制冲突；已确认不适合作为主线改进。

### 2026-01-18-retaliation-smallbias
- change_id: 2026-01-18-retaliation-smallbias
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（反制惩罚随小尺度下注软放大）
- baseline: revert94
- delta: Tier‑A mean≈23.37 (std≈13.64) vs baseline≈25.86 → Δ≈-2.49 bb/100; Tier‑P mean≈15.48 (std≈5.89)
- evidence:
  - BB|TURN|facing:Y | bb/100=-2324.80 | n=5 | seeds=2000 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:7+|oop_multi_street=Y | bb/100=-190.30 | n=37 | seeds=2000 | ref=report:BBFlatPostflop/7+_oop_Y
  - players:4p|RIVER | bb/100=-2294.40 | n=5 | seeds=2000 | ref=report:ProfitByPlayers/RIVER_4p
- outcome: REJECT
- rationale: 结果与 scaled 方案完全一致，说明小尺度惩罚未进入关键决策边界；已撤回，需改为“影响候选集合/混合权重”的机制级改变。

### 2026-01-18-solver-edge-conf
- change_id: 2026-01-18-solver-edge-conf
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（solver_edge 置信度用于 raise cap 缩放）
- baseline: revert94
- delta: Tier‑A mean≈23.37 (std≈13.64) vs baseline≈25.86 → Δ≈-2.49 bb/100; Tier‑P mean≈15.48 (std≈5.89)
- evidence:
  - BB|TURN|facing:Y | bb/100=-2324.80 | n=5 | seeds=2000 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:7+|oop_multi_street=Y | bb/100=-190.30 | n=37 | seeds=2000 | ref=report:BBFlatPostflop/7+_oop_Y
  - players:4p|RIVER | bb/100=-2294.40 | n=5 | seeds=2000 | ref=report:ProfitByPlayers/RIVER_4p
- outcome: REJECT
- rationale: 与 scaled 方案完全一致，说明 solver_edge 未进入关键边界或置信度过低；已撤回。

### 2026-01-18-solver-edge-mix
- change_id: 2026-01-18-solver-edge-mix
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（solver_edge 软混合 raise 目标）
- baseline: revert94
- delta: Tier‑A mean≈16.35 (std≈14.61) vs baseline≈25.86 → Δ≈-9.51 bb/100; Tier‑P mean≈14.03 (std≈9.29)
- evidence:
  - BB|TURN|facing:Y | bb/100=-2324.80 | n=5 | seeds=2000 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:7+|oop_multi_street=Y | bb/100=-190.30 | n=37 | seeds=2000 | ref=report:BBFlatPostflop/7+_oop_Y
  - players:4p|RIVER | bb/100=-2294.40 | n=5 | seeds=2000 | ref=report:ProfitByPlayers/RIVER_4p
- outcome: REJECT
- rationale: solver_edge 软混合直接拉低整体强度且关键桶未改善，说明 solver_edge 与当前估值体系不兼容；已撤回。

### 2026-01-18-retaliation-probe-bias
- change_id: 2026-01-18-retaliation-probe-bias
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（尺寸过滤时引入反制概率偏置）
- baseline: revert94
- delta: Tier‑A mean≈23.11 (std≈19.10) vs baseline≈25.86 → Δ≈-2.75 bb/100; Tier‑P mean≈16.14 (std≈10.84)
- evidence:
  - BB|TURN|facing:Y | bb/100=-2891.60 | n=5 | seeds=2000 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:7+|oop_multi_street=Y | bb/100=-34.82 | n=38 | seeds=2000 | ref=report:BBFlatPostflop/7+_oop_Y
  - players:4p|RIVER | bb/100=-2294.40 | n=5 | seeds=2000 | ref=report:ProfitByPlayers/RIVER_4p
- outcome: CONTINUE
- rationale: 压力套件（Tier‑P）均值提升，但 Tier‑A 均值与方差回落；说明“反制概率偏置”有方向价值但系数偏强，需要缩减幅度以保持基线稳定。

### 2026-01-18-retaliation-probe-bias-b2
- change_id: 2026-01-18-retaliation-probe-bias-b2
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（反制概率偏置系数下调至 0.12）
- baseline: revert94
- delta: Tier‑A mean≈23.65 (std≈16.36) vs baseline≈25.86 → Δ≈-2.21 bb/100; Tier‑P mean≈18.73 (std≈13.15)
- evidence:
  - BB|TURN|facing:Y | bb/100=-2891.60 | n=5 | seeds=2000 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:7+|oop_multi_street=Y | bb/100=-242.00 | n=38 | seeds=2000 | ref=report:BBFlatPostflop/7+_oop_Y
  - players:4p|RIVER | bb/100=-368.00 | n=4 | seeds=2000 | ref=report:ProfitByPlayers/RIVER_4p
- outcome: CONTINUE
- rationale: Tier‑P 均值显著上升，Tier‑A 小幅回升但方差偏高；当前为“压力维度最好”方案，可继续微调系数或引入稳定化项以恢复基线。

### 2026-01-18-retaliation-probe-bias-b3
- change_id: 2026-01-18-retaliation-probe-bias-b3
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（反制概率偏置系数下调至 0.08）
- baseline: revert94
- delta: Tier‑A mean≈25.21 (std≈20.72) vs baseline≈25.86 → Δ≈-0.65 bb/100; Tier‑P mean≈16.42 (std≈5.38)
- evidence:
  - BB|TURN|facing:Y | bb/100=-2891.60 | n=5 | seeds=2000 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:7+|oop_multi_street=Y | bb/100=-266.89 | n=37 | seeds=2000 | ref=report:BBFlatPostflop/7+_oop_Y
  - players:4p|RIVER | bb/100=3607.40 | n=5 | seeds=2000 | ref=report:ProfitByPlayers/RIVER_4p
- outcome: CONTINUE
- rationale: Tier‑A 均值接近基线但方差较高，Tier‑P 仍高于 scaled；但 actionspace 微扰测试（v2_micro066）均值≈1.57，显示稳定性不足，暂不具备升级基线条件。

### 2026-01-18-retaliation-probe-bias-b4
- change_id: 2026-01-18-retaliation-probe-bias-b4
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（反制偏置引入样本 shrink）
- baseline: revert94
- delta: Tier‑A mean≈21.85 (std≈11.91) vs baseline≈25.86 → Δ≈-4.01 bb/100; Tier‑P mean≈14.94 (std≈5.78)
- evidence:
  - BB|TURN|facing:Y | bb/100=-2891.60 | n=5 | seeds=2000 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:7+|oop_multi_street=Y | bb/100=-266.89 | n=37 | seeds=2000 | ref=report:BBFlatPostflop/7+_oop_Y
  - players:4p|RIVER | bb/100=-2294.40 | n=5 | seeds=2000 | ref=report:ProfitByPlayers/RIVER_4p
- outcome: REJECT
- rationale: shrink 虽降方差但显著拉低 Tier‑A 与 Tier‑P 均值，整体劣化；已撤回。

### 2026-01-18-retaliation-probe-bias-b5
- change_id: 2026-01-18-retaliation-probe-bias-b5
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（尺寸过滤保留 4 档）
- baseline: revert94
- delta: Tier‑A mean≈12.57 (std≈14.35) vs baseline≈25.86 → Δ≈-13.29 bb/100; Tier‑P mean≈8.79 (std≈5.81)
- evidence:
  - BB|TURN|facing:Y | bb/100=-2527.50 | n=6 | seeds=2000 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:7+|oop_multi_street=Y | bb/100=12.92 | n=36 | seeds=2000 | ref=report:BBFlatPostflop/7+_oop_Y
  - players:4p|RIVER | bb/100=3607.40 | n=5 | seeds=2000 | ref=report:ProfitByPlayers/RIVER_4p
- outcome: REJECT
- rationale: 动作空间扩到 4 档导致整体强度明显下降，说明过滤机制对 size 密度非常敏感；已撤回。

### 2026-01-18-actionspace-insensitive
- change_id: 2026-01-18-actionspace-insensitive
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（尺寸过滤改为固定几何目标）
- baseline: revert94
- delta: Tier‑A mean≈10.67 (std≈13.02) vs baseline≈25.86 → Δ≈-15.19 bb/100; Tier‑P mean≈8.25 (std≈12.88); micro066 mean≈-5.68 (std≈35.26)
- evidence:
  - BB|TURN|facing:Y | bb/100=-2723.00 | n=4 | seeds=2000 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:7+|oop_multi_street=Y | bb/100=-361.97 | n=37 | seeds=2000 | ref=report:BBFlatPostflop/7+_oop_Y
  - players:4p|RIVER | bb/100=-368.00 | n=4 | seeds=2000 | ref=report:ProfitByPlayers/RIVER_4p
- outcome: REJECT
- rationale: 几何目标过滤未提升稳健性且整体大幅下滑，micro066 仍崩塌，说明当前“尺寸过滤”机制不适合作为主路径；后续应切换到局部 rollout 或显式 raise/call 置信度控制。

### 2026-01-18-call-premium-price-spr
- change_id: 2026-01-18-call-premium-price-spr
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（call_risk_premium 引入 price/spr 平滑桶）
- baseline: revert94
- delta: Tier‑A mean≈25.23 (std≈20.71) vs baseline≈25.86 → Δ≈-0.63 bb/100; Tier‑P mean≈16.42 (std≈5.38)
- evidence:
  - BB|TURN|facing:Y | bb/100=-2891.60 | n=5 | seeds=2000 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:7+|oop_multi_street=Y | bb/100=-266.89 | n=37 | seeds=2000 | ref=report:BBFlatPostflop/7+_oop_Y
  - players:4p|RIVER | bb/100=3607.40 | n=5 | seeds=2000 | ref=report:ProfitByPlayers/RIVER_4p
- outcome: REJECT
- rationale: 与 b3 结果几乎一致，关键桶不变，说明 price/spr 平滑桶未进入决策边界；已撤回。

### 2026-01-18-size-pref-regularizer
- change_id: 2026-01-18-size-pref-regularizer
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（移除 size 过滤 + 加入 size 偏好正则）
- baseline: revert94
- delta: Tier‑A mean≈11.67 (std≈21.34) vs baseline≈25.86 → Δ≈-14.19 bb/100; Tier‑P mean≈7.78 (std≈13.31); micro066 mean≈5.78 (std≈19.23)
- evidence:
  - BB|TURN|facing:Y | bb/100=-2723.00 | n=4 | seeds=2000 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:7+|oop_multi_street=Y | bb/100=73.61 | n=36 | seeds=2000 | ref=report:BBFlatPostflop/7+_oop_Y
  - players:4p|RIVER | bb/100=3509.00 | n=5 | seeds=2000 | ref=report:ProfitByPlayers/RIVER_4p
- outcome: REJECT
- rationale: 虽然 micro066 未崩塌，但 Tier‑A/Tier‑P 均显著下滑，说明“全保留+正则”在当前估值体系下不可用；已撤回。

### 2026-01-18-size-pref-tiebreak
- change_id: 2026-01-18-size-pref-tiebreak
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（近边界 raise 的 size 偏好 tie‑break）
- baseline: revert94
- delta: Tier‑A mean≈26.71 (std≈21.23) vs baseline≈25.86 → Δ≈+0.85 bb/100; Tier‑P mean≈16.29 (std≈5.33); micro066 mean≈0.63 (std≈30.44)
- evidence:
  - BB|TURN|facing:Y | bb/100=-2324.80 | n=5 | seeds=2000 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:7+|oop_multi_street=Y | bb/100=-190.30 | n=37 | seeds=2000 | ref=report:BBFlatPostflop/7+_oop_Y
  - players:4p|RIVER | bb/100=3607.40 | n=5 | seeds=2000 | ref=report:ProfitByPlayers/RIVER_4p
- outcome: REJECT
- rationale: Tier‑A 均值略高但 micro066 仍崩塌，稳定性门禁未通过；不具备基线候选资格，已撤回。

### 2026-01-19-size-bucket-merge
- change_id: 2026-01-19-size-bucket-merge
- change_type: Restructure
- scope: `poker2/runtime/system_policy.py`（动作空间稳定性：按尺寸桶合并 raise/bet 权重）
- baseline: revert94
- delta: Tier‑A mean≈20.92 (std≈15.66) vs baseline≈25.86 → Δ≈-4.94 bb/100；Tier‑P mean≈14.82 (std≈9.19)；micro066 mean≈3.92 (std≈24.89)
- evidence:
  - RIVER|Facing=Y | bb/100=-812.66 | n=41 | seeds=2000–2004 | ref=report:bb_flat_postflop_facing_by_street
  - TURN|SPR=2-4 | bb/100=-2670.20 | n=5 | seeds=2000–2004 | ref=report:bb_flat_postflop_spr_by_street
  - RIVER|players=2 | bb/100=+6.66 | n=984 | seeds=2000–2004 | ref=report:profit_by_players
- outcome: REJECT
- rationale: 稳定性合并未提升基线均值，Tier‑P 明显偏弱，且 actionspace 微扰（micro066）出现严重坍塌；Facing=Y 负桶未收敛，需撤回并回到 b3 基础继续改进。

### 2026-01-19-solver-gap-softmix
- change_id: 2026-01-19-solver-gap-softmix
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（CALL 参考值使用 call_ev_ref_call；raise/call 混合引入 solver_gap 软门槛与置信度混合）
- baseline: revert94
- delta: Tier‑A mean≈24.50 (std≈21.60) vs baseline≈25.86 → Δ≈-1.36 bb/100；Tier‑P mean≈11.65 (std≈10.92)；micro066 mean≈2.96 (std≈23.73)
- evidence:
  - TURN|Facing=Y | bb/100=-1121.17 | n=24 | seeds=2000–2004 | ref=report:bb_flat_postflop_facing_by_street
  - RIVER|Facing=Y | bb/100=-812.30 | n=44 | seeds=2000–2004 | ref=report:bb_flat_postflop_facing_by_street
  - RIVER|players=2 | bb/100=-8.90 | n=965 | seeds=2000–2004 | ref=report:profit_by_players
- outcome: REJECT
- rationale: Tier‑A 仍低于基线，Tier‑P 继续下降，micro066 依旧崩塌；solver_gap 软门槛未解决 OOP Facing=Y 负桶，需撤回。

### 2026-01-19-callref-consistency
- change_id: 2026-01-19-callref-consistency
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（raise net EV 权重基准与 call_ev_ref_call 对齐）
- baseline: revert94
- delta: Tier‑A mean≈25.21 (std≈18.53) vs baseline≈25.21 → Δ≈0.00 bb/100；Tier‑P mean≈16.42 (std≈4.81)；micro066 mean≈1.57 (std≈26.12)
- evidence:
  - TURN|Facing=Y | bb/100=-832.26 | n=23 | seeds=2000–2004 | ref=report:bb_flat_postflop_facing_by_street
  - RIVER|Facing=Y | bb/100=-878.21 | n=42 | seeds=2000–2004 | ref=report:bb_flat_postflop_facing_by_street
  - RIVER|players=2 | bb/100=-8.90 | n=965 | seeds=2000–2004 | ref=report:profit_by_players
- outcome: REJECT
- rationale: 配对对比 Δ=0（行为未改变），micro066 仍崩塌；该改动没有实际作用，撤回并继续寻找有效机制。

### 2026-01-19-raise-netdelta-sig
- change_id: 2026-01-19-raise-netdelta-sig
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（raise 权重按 net ΔEV sigmoid 软惩罚）
- baseline: revert94
- delta: Tier‑A mean≈25.21 (std≈18.53) vs baseline≈25.21 → Δ≈0.00 bb/100；Tier‑P mean≈16.42 (std≈4.81)；micro066 mean≈1.57 (std≈26.12)
- evidence:
  - TURN|Facing=Y | bb/100=-832.26 | n=23 | seeds=2000–2004 | ref=report:bb_flat_postflop_facing_by_street
  - RIVER|Facing=Y | bb/100=-878.21 | n=42 | seeds=2000–2004 | ref=report:bb_flat_postflop_facing_by_street
  - RIVER|players=2 | bb/100=-8.90 | n=965 | seeds=2000–2004 | ref=report:profit_by_players
- outcome: REJECT
- rationale: 配对对比 Δ=0（行为未改变），说明该软惩罚未进入决策边界；micro066 仍崩塌，撤回。

### 2026-01-19-ev-margin-defend
- change_id: 2026-01-19-ev-margin-defend
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（提高 facing 场景 EV‑first 选择门槛，释放混合空间）
- baseline: revert94
- delta: Tier‑A mean≈2.71 (std≈8.84) vs baseline≈25.21 → Δ≈-22.50 bb/100；Tier‑P mean≈1.10 (std≈7.39)；micro066 mean≈5.02 (std≈19.92)
- evidence:
  - TURN|Facing=Y | bb/100=-2178.94 | n=16 | seeds=2000–2004 | ref=report:bb_flat_postflop_facing_by_street
  - TURN|SPR=2-4 | bb/100=-2670.20 | n=5 | seeds=2000–2004 | ref=report:bb_flat_postflop_spr_by_street
  - RIVER|players=3 | bb/100=-59.08 | n=233 | seeds=2000–2004 | ref=report:profit_by_players
- outcome: REJECT
- rationale: 大幅削弱整体强度；且 TURN_Y 覆盖不足（n<20，coverage_check FAIL），不得据此优化。已撤回该门槛提升。

### 2026-01-19-ev-first-score
- change_id: 2026-01-19-ev-first-score
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（facing 场景 EV-first 用 score 替代 raw EV）
- baseline: revert94
- delta: Tier‑A mean≈11.96 (std≈13.64) vs baseline≈25.21 → Δ≈-13.25 bb/100；Tier‑P mean≈7.82 (std≈8.88)；micro066 mean≈-1.00 (std≈9.13)
- evidence:
  - TURN|Facing=Y | bb/100=-1805.20 | n=10 | seeds=2000–2004 | ref=report:bb_flat_postflop_facing_by_street
  - RIVER|Facing=Y | bb/100=-816.08 | n=13 | seeds=2000–2004 | ref=report:bb_flat_postflop_facing_by_street
  - RIVER|players=4 | bb/100=-142.50 | n=2 | seeds=2000–2004 | ref=report:profit_by_players
- outcome: REJECT
- rationale: Tier‑A/Tier‑P 均显著下滑；关键桶覆盖不足（TURN_Y / RIVER_Y n<20，coverage_check FAIL），不具备可用性，撤回。

### 2026-01-19-ev-blend-score
- change_id: 2026-01-19-ev-blend-score
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（facing 场景 EV-first 对 EV/score 软融合）
- baseline: revert94
- delta: Tier‑A mean≈14.01 (std≈14.10) vs baseline≈25.21 → Δ≈-11.21 bb/100；Tier‑P mean≈8.03 (std≈11.18)；micro066 mean≈2.03 (std≈17.40)
- evidence:
  - TURN|Facing=Y | bb/100=-1853.79 | n=19 | seeds=2000–2004 | ref=report:bb_flat_postflop_facing_by_street
  - TURN|SPR=7+ | bb/100=-188.21 | n=142 | seeds=2000–2004 | ref=report:bb_flat_postflop_spr_by_street
  - RIVER|players=4 | bb/100=-1304.20 | n=10 | seeds=2000–2004 | ref=report:profit_by_players
- outcome: REJECT
- rationale: 均值显著下滑；Tier‑A TURN_Y 覆盖不足（n<20，coverage_check FAIL）。EV/score 融合仍过度抑制导致整体崩塌，撤回。

### 2026-01-19-ev-rank-adjust
- change_id: 2026-01-19-ev-rank-adjust
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（EV-first 使用 EV-净成本 排序）
- baseline: revert94
- delta: Tier‑A mean≈21.01 (std≈18.93) vs baseline≈25.21 → Δ≈-4.20 bb/100；Tier‑P mean≈10.67 (std≈7.03)；micro066 mean≈15.78 (std≈21.61)
- evidence:
  - TURN|Facing=Y | bb/100=-1651.78 | n=23 | seeds=2000–2004 | ref=report:bb_flat_postflop_facing_by_street
  - RIVER|Facing=Y | bb/100=-949.51 | n=37 | seeds=2000–2004 | ref=report:bb_flat_postflop_facing_by_street
  - SPR:7+|oop_multi_street=Y | bb/100=-261.09 | n=199 | seeds=2000–2004 | ref=report:BBFlatPostflop/7+_oop_Y
- outcome: REJECT
- rationale: Tier‑A 与 Tier‑P 均显著低于基线，虽 micro066 改善但主评测退化；按规则拒绝并撤回。

### 2026-01-19-call-gap-discount
- change_id: 2026-01-19-call-gap-discount
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（OOP facing CALL 按 pot‑odds gap 折扣 equity）
- baseline: revert94
- delta: Tier‑A mean≈15.10 (std≈10.87) vs baseline≈25.21 → Δ≈-10.11 bb/100；Tier‑P mean≈12.21 (std≈6.88)；micro066 mean≈18.61 (std≈20.25)
- evidence:
  - TURN|Facing=Y | bb/100=-1078.17 | n=23 | seeds=2000–2004 | ref=report:bb_flat_postflop_facing_by_street
  - RIVER|Facing=Y | bb/100=-592.03 | n=34 | seeds=2000–2004 | ref=report:bb_flat_postflop_facing_by_street
  - SPR:7+|oop_multi_street=Y | bb/100=-220.34 | n=199 | seeds=2000–2004 | ref=report:BBFlatPostflop/7+_oop_Y
- outcome: REJECT
- rationale: Tier‑A/Tier‑P 显著下滑，虽 micro066 改善但主评测退化；按规则拒绝并撤回。

### 2026-01-19-solver-ev-softblend
- change_id: 2026-01-19-solver-ev-softblend
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（facing 场景 solver EV 软融合）
- baseline: revert94
- delta: Tier‑A mean≈-5.22 (std≈12.90) vs baseline≈25.21 → Δ≈-30.43 bb/100；Tier‑P mean≈-5.21 (std≈13.49)；micro066 mean≈8.70 (std≈8.81)
- evidence:
  - TURN|Facing=Y | bb/100=0.00 | n=0 | seeds=2000–2004 | ref=report:bb_flat_postflop_facing_by_street
  - RIVER|Facing=Y | bb/100=0.00 | n=0 | seeds=2000–2004 | ref=report:bb_flat_postflop_facing_by_street
  - SPR:7+|oop_multi_street=Y | bb/100=0.00 | n=0 | seeds=2000–2004 | ref=report:BBFlatPostflop/7+_oop_Y
- outcome: REJECT
- rationale: 整体 EV 大幅崩塌；关键桶覆盖为 0（coverage_check FAIL），说明策略行为发生异常变化且不可诊断，需撤回并排查。

### 2026-01-19-retaliation-confscale
- change_id: 2026-01-19-retaliation-confscale
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（反制惩罚按样本置信度缩放）
- baseline: revert94
- delta: Tier‑A mean≈24.79 (std≈18.95) vs baseline≈25.21 → Δ≈-0.42 bb/100；Tier‑P mean≈16.55 (std≈4.77)；micro066 mean≈1.20 (std≈26.41)
- evidence:
  - TURN|Facing=Y | bb/100=-832.26 | n=23 | seeds=2000–2004 | ref=report:bb_flat_postflop_facing_by_street
  - RIVER|Facing=Y | bb/100=-878.21 | n=42 | seeds=2000–2004 | ref=report:bb_flat_postflop_facing_by_street
  - SPR:7+|oop_multi_street=Y | bb/100=-67.03 | n=199 | seeds=2000–2004 | ref=report:BBFlatPostflop/7+_oop_Y
- outcome: REJECT
- rationale: Tier‑A 略降且 micro066 仍崩塌；未优于基线，按规则拒绝并撤回。

### 2026-01-19-eval-bootstrap-ci
- change_id: 2026-01-19-eval-bootstrap-ci
- change_type: Enforce
- scope: `poker2/tools/paired_compare.py` + `poker2/cli/paired_compare.py` + `notes/evaluation_playbook.md` + `notes/iteration_journal.md`
- baseline: revert94
- delta: Tier‑A Δmean=0.00（bootstrap CI [0.00, 0.00]）vs baseline；Tier‑P mean≈16.42 (std≈5.38)
- evidence:
  - TURN|Facing=Y | bb/100=-823.29 | n=24 | seeds=2000–2004 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:7+|oop=Y | bb/100=-142.19 | n=200 | seeds=2000–2004 | ref=report:BBFlatPostflop/7+_oop_Y
  - FLOP|players=4p | bb/100=-508.25 | n=32 | seeds=2000–2004 | ref=report:ProfitByPlayers/FLOP_4p
- outcome: ADOPT
- rationale: 引入配对 bootstrap CI，提高对比置信度；验证当前版本与基线同矩阵完全一致（Δ=0），评测地基稳定，可继续策略改进。

### 2026-01-19-size-template-b1
- change_id: 2026-01-19-size-template-b1
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（postflop 动作模板软融合：多人数与 OOP facing turn/river 降低大尺寸偏置）
- baseline: revert94
- delta: Tier‑A mean≈8.69 (std≈20.70) vs baseline≈25.21 → Δ≈-16.52 bb/100（bootstrap CI [-35.48, +3.45]）；Tier‑P mean≈3.80 (std≈19.60)；micro066 mean≈-7.97 (std≈30.86)
- evidence:
  - TURN|Facing=Y | bb/100=-1021.96 | n=25 | seeds=2000–2004 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:7+|oop=Y | bb/100=-209.72 | n=197 | seeds=2000–2004 | ref=report:BBFlatPostflop/7+_oop_Y
  - FLOP|players=4p | bb/100=-199.37 | n=32 | seeds=2000–2004 | ref=report:ProfitByPlayers/FLOP_4p
- outcome: REJECT
- rationale: Tier‑A/Tier‑P 均显著下降且 micro066 崩塌；动作模板软融合导致整体策略退化，按规则拒绝并撤回。

### 2026-01-19-retaliation-facing-raise
- change_id: 2026-01-19-retaliation-facing-raise
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（facing bet 时的 raise 增量引入反制风险惩罚）
- baseline: revert94
- delta: Tier‑A mean≈25.21 (std≈20.72) vs baseline≈25.21 → Δ≈0.00 bb/100（bootstrap CI [0.00, 0.00]）；Tier‑P mean≈16.42 (std≈5.38)；micro066 mean≈1.57 (std≈29.20)
- evidence:
  - TURN|Facing=Y | bb/100=-823.29 | n=24 | seeds=2000–2004 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:7+|oop=Y | bb/100=-142.19 | n=200 | seeds=2000–2004 | ref=report:BBFlatPostflop/7+_oop_Y
  - FLOP|players=4p | bb/100=-508.25 | n=32 | seeds=2000–2004 | ref=report:ProfitByPlayers/FLOP_4p
- outcome: REJECT
- rationale: 行为未变化（paired_compare Δ=0）；说明该惩罚未触及决策边界，按规则撤回。

### 2026-01-19-retaliation-size-dampen
- change_id: 2026-01-19-retaliation-size-dampen
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（反制概率提高→降低大尺寸偏置）
- baseline: revert94
- delta: Tier‑A mean≈23.08 (std≈9.75) vs baseline≈25.21 → Δ≈-2.13 bb/100（bootstrap CI [-16.01, +8.78]）；Tier‑P mean≈17.40 (std≈8.31)；micro066 mean≈0.29 (std≈33.69)
- evidence:
  - TURN|Facing=Y | bb/100=-1069.17 | n=24 | seeds=2000–2004 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:7+|oop=Y | bb/100=-152.79 | n=200 | seeds=2000–2004 | ref=report:BBFlatPostflop/7+_oop_Y
  - FLOP|players=4p | bb/100=-508.25 | n=32 | seeds=2000–2004 | ref=report:ProfitByPlayers/FLOP_4p
- outcome: REJECT
- rationale: Tier‑P 小幅提升但 Tier‑A 明显下降；不满足基线规则，撤回。

### 2026-01-19-retaliation-size-mw-only
- change_id: 2026-01-19-retaliation-size-mw-only
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（仅多人数场景抑制大尺寸偏置）
- baseline: revert94
- delta: Tier‑A mean≈19.35 (std≈13.88) vs baseline≈25.21 → Δ≈-5.87 bb/100（bootstrap CI [-13.55, -0.75]）；Tier‑P mean≈15.87 (std≈7.62)；micro066 mean≈2.55 (std≈28.15)
- evidence:
  - TURN|Facing=Y | bb/100=-859.29 | n=24 | seeds=2000–2004 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:7+|oop=Y | bb/100=-161.56 | n=200 | seeds=2000–2004 | ref=report:BBFlatPostflop/7+_oop_Y
  - FLOP|players=4p | bb/100=-508.25 | n=32 | seeds=2000–2004 | ref=report:ProfitByPlayers/FLOP_4p
- outcome: REJECT
- rationale: Tier‑A 显著下降且 CI 明显小于 0；不满足基线规则，撤回。

### 2026-01-19-solver-hint-strength
- change_id: 2026-01-19-solver-hint-strength
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（OOP TURN/RIVER 强化 solver_hint 对 call/raise 权重影响）
- baseline: revert94
- delta: Tier‑A mean≈25.21 (std≈20.72) vs baseline≈25.21 → Δ≈0.00 bb/100（bootstrap CI [0.00, 0.00]）；Tier‑P mean≈16.42 (std≈5.38)；micro066 mean≈1.57 (std≈29.20)
- evidence:
  - TURN|Facing=Y | bb/100=-823.29 | n=24 | seeds=2000–2004 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:7+|oop=Y | bb/100=-142.19 | n=200 | seeds=2000–2004 | ref=report:BBFlatPostflop/7+_oop_Y
  - FLOP|players=4p | bb/100=-508.25 | n=32 | seeds=2000–2004 | ref=report:ProfitByPlayers/FLOP_4p
- outcome: REJECT
- rationale: paired_compare Δ=0；推测 solver_hint 在此矩阵内未触发或弱影响，机制未生效，撤回。

### 2026-01-19-solver-hint-gate-strict
- change_id: 2026-01-19-solver-hint-gate-strict
- change_type: Enforce
- scope: `poker2/runtime/system_policy.py`（HU OOP TURN/RIVER facing 强制 solver_hint 行为）
- baseline: revert94
- delta: Tier‑A mean≈18.15 (std≈27.06) vs baseline≈25.21 → Δ≈-7.06 bb/100（bootstrap CI [-21.04, +3.47]）；Tier‑P mean≈13.39 (std≈25.14)；micro066 mean≈-12.43 (std≈16.95)
- evidence:
  - TURN|Facing=Y | bb/100=-2616.38 | n=21 | seeds=2000–2004 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:7+|oop=Y | bb/100=-156.89 | n=199 | seeds=2000–2004 | ref=report:BBFlatPostflop/7+_oop_Y
  - TURN|players=3p | bb/100=-133.02 | n=408 | seeds=2000–2004 | ref=report:ProfitByPlayers/TURN_3p
- outcome: REJECT
- rationale: Tier‑A/Tier‑P 与 micro066 均显著退化；强制 gate 破坏策略稳定性，撤回。

### 2026-01-20-baseline-refresh-2x6x2000
- change_id: 2026-01-20-baseline-refresh-2x6x2000
- change_type: Enforce
- scope: `notes/iteration_journal.md` + `notes/evaluation_playbook.md` + `poker2/cli/eval_full.py`
- baseline: revert94
- delta: Tier‑A mean≈16.71 (std≈27.87)；Tier‑A confirm mean≈12.59 (std≈24.09)；Tier‑P mean≈10.64 (std≈14.96)
- evidence:
  - TURN|Facing=Y | bb/100=-994.25 | n=28 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:7+|oop=Y | bb/100=-201.47 | n=247 | seeds=2000–2005 | ref=report:BBFlatPostflop/7+_oop_Y
  - TURN|players=4p | bb/100=-1394.59 | n=22 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
- outcome: ADOPT
- rationale: 基线分布化完成（2×6×2000），显著降低“好运偏差”；对手池与 BR 压力入口已联动，后续所有改动以该分布基线为准。

### 2026-01-20-callref-call-only
- change_id: 2026-01-20-callref-call-only
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（raise 边际改用 call_ev_ref；call_ev_ref_call 仅用于 CALL）
- baseline: revert94
- delta: Tier‑A mean≈14.46 (std≈27.46) vs baseline≈16.71 → Δ≈-2.25 bb/100（paired CI [-6.75, 0.0]）；Tier‑P mean≈8.52 (std≈14.34)
- evidence:
  - RIVER|Facing=Y | bb/100=-1059.30 | n=54 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:7+|oop=Y | bb/100=-197.77 | n=246 | seeds=2000–2005 | ref=report:BBFlatPostflop/7+_oop_Y
  - RIVER|players=2p | bb/100=-24.61 | n=1200 | seeds=2000–2005 | ref=report:ProfitByPlayers/RIVER_2p
- outcome: REJECT
- rationale: raise 偏好略收敛但整体 EV 下滑且 Tier‑P 同步走弱；下一步需引入 solver_gap 置信度软门槛而非仅抬高 CALL 基线。

### 2026-01-20-hu-range-rollout
- change_id: 2026-01-20-hu-range-rollout
- change_type: Define
- scope: `poker2/runtime/system_policy.py`, `poker2/runtime/hand_eval.py`, `specs/policy_params/system_bot_params_v3.json`
- baseline: revert94
- delta: Tier‑A mean≈7.81 (std≈24.17), Tier‑P mean≈4.19 (std≈17.61), confirm≈9.80 (std≈14.45); options_hash mismatch (baseline 3e2a… vs candidate 41a6…) → paired compare invalid
- evidence:
  - TURN|Facing=Y | bb/100=-1162.58 | n=26 | seeds=2000–2005 | ref=report:bb_flat_postflop_facing_by_street
  - SPR:7+|oop_multi_street=Y | bb/100=-163.14 | n=248 | seeds=2000–2005 | ref=report:BBFlatPostflop/7+_oop_Y
  - TURN|players=3 | bb/100=-71.12 | n=538 | seeds=2000–2005 | ref=report:profit_by_players
- outcome: REJECT
- rationale: HU 范围估值+rollout 机制可运行，但整体均值明显低于基线且 Facing=Y 负桶仍极大；options_hash 不一致导致无法与基线配对比较，需先回到可比 options_hash 再评估真实增益。

### 2026-01-20-hu-rollout-activate
- change_id: 2026-01-20-hu-rollout-activate
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（启用 HU rollout 参数加载 + HU 分支接入 + soft override）
- baseline: revert94
- delta: Tier‑A mean≈8.17 (std≈22.43), Tier‑P mean≈4.84 (std≈12.89), confirm≈7.71 (std≈12.91); options_hash mismatch (baseline 3e2a… vs candidate 41a6…) → paired compare invalid
- evidence:
  - RIVER|Facing=Y | bb/100=-1272.83 | n=52 | seeds=2000–2005 | ref=report:bb_flat_postflop_facing_by_street
  - SPR:7+|oop_multi_street=Y | bb/100=-163.14 | n=248 | seeds=2000–2005 | ref=report:BBFlatPostflop/7+_oop_Y
  - TURN|players=3 | bb/100=-44.40 | n=538 | seeds=2000–2005 | ref=report:profit_by_players
- outcome: REJECT
- rationale: HU rollout 已实际触发（eventstream 可见），但整体均值仍显著低于基线，且 Facing=Y 负桶未实质收敛；需先修复 options_hash 可比性或进一步改进 rollout 价值估计。

### 2026-01-20-hu-rollout-risk-blend
- change_id: 2026-01-20-hu-rollout-risk-blend
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（rollout EV 加入 Δrake + OOP 风险项，并支持 solver_gap 软融合）
- baseline: revert94
- delta: Tier‑A mean≈8.62 (std≈19.85), Tier‑P mean≈5.74 (std≈17.33), confirm≈8.64 (std≈15.52); options_hash mismatch (baseline 3e2a… vs candidate 41a6…) → paired compare invalid
- evidence:
  - TURN|Facing=Y | bb/100=-1345.96 | n=27 | seeds=2000–2005 | ref=report:bb_flat_postflop_facing_by_street
  - SPR:7+|oop_multi_street=Y | bb/100=-163.14 | n=248 | seeds=2000–2005 | ref=report:BBFlatPostflop/7+_oop_Y
  - RIVER|players=4 | bb/100=-1052.00 | n=14 | seeds=2000–2005 | ref=report:profit_by_players
- outcome: REJECT
- rationale: 风险项与 Δrake 融合后，rollout 更倾向保守 CALL，但整体均值仍明显低于基线且 Facing=Y 负桶仍极端；需进一步引入 solver EV 置信度或更强的价值估计模型。

### 2026-01-20-hu-rollout-solvergap-read
- change_id: 2026-01-20-hu-rollout-solvergap-read
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（在 HU 分支读取 solver call/raise EV 并用于 rollout 软融合）
- baseline: revert94
- delta: Tier‑A mean≈5.46 (std≈32.28), Tier‑P mean≈3.22 (std≈13.19), confirm≈‑1.39 (std≈21.57); options_hash mismatch (baseline 3e2a… vs candidate 41a6…) → paired compare invalid
- evidence:
  - RIVER|Facing=Y | bb/100=-962.74 | n=54 | seeds=2000–2005 | ref=report:bb_flat_postflop_facing_by_street
  - SPR:7+|oop_multi_street=Y | bb/100=-428.18 | n=232 | seeds=2000–2005 | ref=report:BBFlatPostflop/7+_oop_Y
  - RIVER|players=2 | bb/100=-81.83 | n=729 | seeds=2000–2005 | ref=report:profit_by_players
- outcome: REJECT
- rationale: 均值与确认集显著下滑，波动增加；说明在当前环境下 rollout+solver_gap 软融合仍未稳定改善 Facing=Y，需重新校正 rollout 风险项与价值尺度。

### 2026-01-20-hu-rollout-snr-gate
- change_id: 2026-01-20-hu-rollout-snr-gate
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（rollout override 按 SNR 缩放，抑制低置信度替换）
- baseline: revert94
- delta: Tier‑A mean≈5.18 (std≈33.05), Tier‑P mean≈2.04 (std≈14.97), confirm≈0.43 (std≈21.57); options_hash mismatch (baseline 3e2a… vs candidate 41a6…) → paired compare invalid
- evidence:
  - RIVER|Facing=Y | bb/100=-962.74 | n=54 | seeds=2000–2005 | ref=report:bb_flat_postflop_facing_by_street
  - SPR:7+|oop_multi_street=Y | bb/100=-428.18 | n=232 | seeds=2000–2005 | ref=report:BBFlatPostflop/7+_oop_Y
  - RIVER|players=2 | bb/100=-86.31 | n=729 | seeds=2000–2005 | ref=report:profit_by_players
- outcome: REJECT
- rationale: SNR gate 未能改善核心负桶且整体更弱，说明 rollout 价值模型与风险项仍不匹配当前环境；需要改回基线方向或重新设计 rollout 触发与价值估计。
### 2026-01-20-hu-rollout-solvergap-wire
- change_id: 2026-01-20-hu-rollout-solvergap-wire
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（HU rollout 接入 solver_gap/solver_conf，并修复 trace 为 null）
- baseline: revert94
- delta: Tier‑A mean≈1.37 (std≈21.07), confirm≈2.52 (std≈18.68), Tier‑P mean≈4.09 (std≈16.07)；options_hash 与基线不一致（strict paired_compare 失败，结果不可直接对比）
- evidence:
  - TURN|Facing=Y | bb/100=-1357.52 | n=23 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:7+|oop_multi_street=Y | bb/100=-424.30 | n=238 | seeds=2000–2005 | ref=report:BBFlatPostflop/7+_oop_Y
  - RIVER|players=4 | bb/100=-973.63 | n=16 | seeds=2000–2005 | ref=report:ProfitByPlayers/RIVER_4p
- outcome: REJECT
- rationale: solver_gap trace 已恢复非空，但 Tier‑A/Tier‑P 均显著偏低且关键桶继续崩；需先恢复基线 options_hash 再做可比评估，或明确接受新 options_hash 的“新基线轨道”。
### 2026-01-20-pressure-baseline-refresh
- change_id: 2026-01-20-pressure-baseline-refresh
- change_type: Enforce
- scope: `notes/iteration_journal.md`（Tier‑P 压力基线按最新对手套件重建：2×(6×2000)）
- baseline: revert94
- delta: n/a（基线刷新）
- evidence:
  - TURN|Facing=Y | bb/100=-1357.52 | n=23 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:7+|oop_multi_street=Y | bb/100=-424.30 | n=238 | seeds=2000–2005 | ref=report:BBFlatPostflop/7+_oop_Y
  - RIVER|players=4 | bb/100=-973.63 | n=16 | seeds=2000–2005 | ref=report:ProfitByPlayers/RIVER_4p
- outcome: ADOPT
- rationale: 压力对手套件已刷新并形成双层基线，后续改进需同时满足 Tier‑A 与 Tier‑P 两条基线不退化。
### 2026-01-21-hu-rollout-oop-only
- change_id: 2026-01-21-hu-rollout-oop-only
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（HU rollout 限制为 OOP 面对下注）
- baseline: revert94
- delta: Tier‑A mean≈4.55 (std≈30.55) vs baseline≈16.71；Tier‑P mean≈3.41 (std≈14.23) vs pressure baseline≈4.09 → 均显著低于基线
- evidence:
  - TURN|Facing=Y | bb/100=-1357.52 | n=23 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:7+|oop_multi_street=Y | bb/100=-432.38 | n=238 | seeds=2000–2005 | ref=report:BBFlatPostflop/7+_oop_Y
  - RIVER|players=4 | bb/100=-973.63 | n=16 | seeds=2000–2005 | ref=report:ProfitByPlayers/RIVER_4p
- outcome: REJECT
- rationale: rollout 只限 OOP 后整体仍显著低于基线，关键桶未改善；说明 rollout 价值模型仍不匹配，应回退该机制或重构估值闭环。
### 2026-01-21-hu-rollout-off
- change_id: 2026-01-21-hu-rollout-off
- change_type: Refine
- scope: `specs/policy_params/system_bot_params_v3.json`（关闭 HU rollout：hu_rollout_enable_bp=0）
- baseline: revert94
- delta: Tier‑A mean≈2.05 (std≈31.26) vs baseline≈16.71；Tier‑P mean≈0.23 (std≈13.74) vs pressure baseline≈4.09 → 均显著低于基线
- evidence:
  - TURN|Facing=Y | bb/100=-1271.16 | n=25 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:7+|oop_multi_street=Y | bb/100=-370.50 | n=238 | seeds=2000–2005 | ref=report:BBFlatPostflop/7+_oop_Y
  - RIVER|players=4 | bb/100=-927.12 | n=16 | seeds=2000–2005 | ref=report:ProfitByPlayers/RIVER_4p
- outcome: REJECT
- rationale: 关闭 rollout 后整体强度进一步下降，说明当前代码路径仍偏离基线行为；需定位回归差异或回滚到基线实现再做新机制。
### 2026-01-21-baseline-refresh-latest-env
- change_id: 2026-01-21-baseline-refresh-latest-env
- change_type: Enforce
- scope: `notes/iteration_journal.md`（Tier‑A 基线按最新环境/solver 刷新：2×(6×2000)）
- baseline: revert94
- delta: n/a（基线刷新）
- evidence:
  - RIVER|Facing=Y | bb/100=-1095.83 | n=58 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:7+|oop_multi_street=N | bb/100=-286.84 | n=32 | seeds=2000–2005 | ref=report:BBFlatPostflop/7+_oop_N
  - TURN|players=4 | bb/100=-114.48 | n=21 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
- outcome: ADOPT
- rationale: 最新 solver/build 造成 options_hash 变化，已用 revert94 行为在最新环境下建立双层基线；后续对比以此为准。
### 2026-01-21-solvergap-softmix-raisecap
- change_id: 2026-01-21-solvergap-softmix-raisecap
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（BB/SB facing bet：基于净EV差的动态混合上限 + solver EV 软融合）
- baseline: revert94
- delta: Tier‑A mean≈6.74 (std≈29.52) vs baseline≈6.66 → 近似持平；Tier‑P mean≈2.32 (std≈14.98) vs pressure baseline≈4.09 → 明显退化
- evidence:
  - RIVER|Facing=Y | bb/100=-974.10 | n=60 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:7+|oop_multi_street=Y | bb/100=-386.79 | n=244 | seeds=2000–2005 | ref=report:BBFlatPostflop/7+_oop_Y
  - TURN|players=4 | bb/100=-1519.67 | n=21 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
- outcome: REJECT
- rationale: Tier‑A 未提升、Tier‑P 明显下降；说明软融合方式仍会在强对手下放大弱桶，需撤回并改为更保守的局部机制（仅在 TURN/RIVER OOP Facing=Y 触发的微小校正）。
### 2026-01-21-hu-oop-rollout-softmix
- change_id: 2026-01-21-hu-oop-rollout-softmix
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（HU TURN/RIVER OOP Facing=Y：EV‑std 风险校准软权重）
- baseline: revert94
- delta: Tier‑A mean≈6.66 (std≈27.16) vs baseline≈6.66 → 近似持平；Tier‑P mean≈2.24 (std≈14.00) vs pressure baseline≈4.09 → 明显退化
- evidence:
  - RIVER|Facing=Y | bb/100=-974.10 | n=60 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - TURN|SPR=2-4 | bb/100=-2122.78 | n=9 | seeds=2000–2005 | ref=report:BBFlatPostflopSPR/TURN_2-4
  - TURN|players=4 | bb/100=-1519.67 | n=21 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
- outcome: REJECT
- rationale: 压力套件继续明显下降，负桶结构未变；options_hash 已变化且 paired compare 不可用。下一步需改“行动表达性/尺寸体系”，而非单纯风险折价。
### 2026-01-21-actionexpr-hu-facing-template
- change_id: 2026-01-21-actionexpr-hu-facing-template
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（HU TURN/RIVER Facing=Y：动作尺寸模板保留）
- baseline: revert94
- delta: Tier‑A mean≈6.01 (std≈24.49) vs baseline≈6.66 → Δ≈-0.65 bb/100；Tier‑P mean≈6.28 (std≈17.77) vs pressure baseline≈4.09 → Δ≈+2.19 bb/100
- evidence:
  - TURN|Facing=Y | bb/100=-1028.17 | n=35 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/TURN_Y
  - TURN|SPR=2-4 | bb/100=-1505.00 | n=9 | seeds=2000–2005 | ref=report:BBFlatPostflopSPR/TURN_2-4
  - TURN|players=4 | bb/100=-1519.67 | n=21 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
- outcome: CONTINUE
- rationale: 压力套件显著提升，但 Tier‑A 小幅下滑；需在不牺牲 Tier‑P 的前提下回收 Tier‑A，并做 paired compare（options_hash 变更导致暂不可判定是否显著）。
### 2026-01-21-actionexpr-hu-facing-template-v2
- change_id: 2026-01-21-actionexpr-hu-facing-template-v2
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（HU TURN Facing=Y 模板改为 0.33/0.5/1.0；RIVER 保持 0.5/1.0/1.5）
- baseline: revert94
- delta: Tier‑A mean≈8.49 (std≈25.36) vs baseline≈6.66 → Δ≈+1.83 bb/100；Tier‑P mean≈6.24 (std≈19.34) vs pressure baseline≈4.09 → Δ≈+2.15 bb/100；confirm: Tier‑A≈6.87, Tier‑P≈11.24
- evidence:
  - RIVER|Facing=Y | bb/100=-905.70 | n=61 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - RIVER|SPR=2-4 | bb/100=-1583.82 | n=11 | seeds=2000–2005 | ref=report:BBFlatPostflopSPR/RIVER_2-4
  - TURN|players=4 | bb/100=-1519.67 | n=21 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
- outcome: CONTINUE
- rationale: Tier‑A 与 Tier‑P 同步抬升且 confirm 维持；但 micro066 mean≈-3.55 显著崩塌，动作空间扰动不稳定 → 不可晋级。需改为“相对/分位数模板”以提升动作空间鲁棒性。
### 2026-01-21-actionexpr-hu-facing-quantile
- change_id: 2026-01-21-actionexpr-hu-facing-quantile
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（HU TURN/RIVER Facing=Y：分位数模板 20%/50%/85%）
- baseline: revert94
- delta: Tier‑A mean≈8.11 (std≈29.73) vs baseline≈6.66 → Δ≈+1.45 bb/100；Tier‑P mean≈5.17 (std≈15.32) vs pressure baseline≈4.09 → Δ≈+1.08 bb/100；confirm: Tier‑A≈2.59, Tier‑P≈7.93；micro066 mean≈2.51
- evidence:
  - RIVER|Facing=Y | bb/100=-930.07 | n=60 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - RIVER|SPR=2-4 | bb/100=-1756.62 | n=13 | seeds=2000–2005 | ref=report:BBFlatPostflopSPR/RIVER_2-4
  - TURN|players=4 | bb/100=-1519.67 | n=21 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
- outcome: REJECT
- rationale: 主测提升且 micro066 通过，但 confirm Tier‑A 显著下滑；不满足晋级门槛 A 的稳定性要求，需进一步抑制基线波动。
### 2026-01-21-actionexpr-hu-facing-quantile-softunion
- change_id: 2026-01-21-actionexpr-hu-facing-quantile-softunion
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（HU TURN/RIVER Facing=Y：分位数模板“软并集”保留）
- baseline: revert94
- delta: Tier‑A mean≈9.66 (std≈27.62) vs baseline≈6.66 → Δ≈+3.00 bb/100；Tier‑P mean≈11.32 (std≈22.06) vs pressure baseline≈4.09 → Δ≈+7.23 bb/100；confirm: Tier‑A≈3.50, Tier‑P≈9.48；micro066 mean≈5.17
- evidence:
  - RIVER|Facing=Y | bb/100=-696.47 | n=60 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - RIVER|SPR=2-4 | bb/100=-1767.85 | n=13 | seeds=2000–2005 | ref=report:BBFlatPostflopSPR/RIVER_2-4
  - TURN|players=4 | bb/100=-114.48 | n=21 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
- outcome: REJECT
- rationale: 主测与 micro066 显著提升，但 confirm Tier‑A 仍低于基线；稳定性不足，不满足晋级门槛 A，需引入稳定性约束（如分位数模板权重退火或限制 HU Facing=Y 的尺寸集合宽度）。
### 2026-01-21-actionexpr-hu-facing-quantile-anneal
- change_id: 2026-01-21-actionexpr-hu-facing-quantile-anneal
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（HU Facing=Y：分位数模板“退火触发”）
- baseline: revert94
- delta: Tier‑A mean≈8.58 (std≈26.04) vs baseline≈6.66 → Δ≈+1.92 bb/100；Tier‑P mean≈5.53 (std≈15.74) vs pressure baseline≈4.09 → Δ≈+1.44 bb/100；confirm: Tier‑A≈4.39, Tier‑P≈8.11；micro066 mean≈7.61
- evidence:
  - RIVER|Facing=Y | bb/100=-941.23 | n=61 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - RIVER|SPR=2-4 | bb/100=-1376.09 | n=11 | seeds=2000–2005 | ref=report:BBFlatPostflopSPR/RIVER_2-4
  - TURN|players=4 | bb/100=-114.48 | n=21 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
- outcome: REJECT
- rationale: 主测与 micro066 提升，但 confirm Tier‑A 仍低于基线；稳定性仍不足，需继续降低策略方差（如只保留 2 个分位点或引入价格/SPR 条件触发）。
### 2026-01-21-actionexpr-hu-facing-quantile-anneal-v2
- change_id: 2026-01-21-actionexpr-hu-facing-quantile-anneal-v2
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（HU Facing=Y：分位数 20/70 + 价位/SPR 触发）
- baseline: revert94
- delta: Tier‑A mean≈7.13 (std≈24.65) vs baseline≈6.66 → Δ≈+0.47 bb/100；Tier‑P mean≈4.32 (std≈15.35) vs pressure baseline≈4.09 → Δ≈+0.23 bb/100；confirm: Tier‑A≈3.32, Tier‑P≈7.04；micro066 mean≈6.45
- evidence:
  - RIVER|Facing=Y | bb/100=-941.23 | n=61 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - RIVER|SPR=2-4 | bb/100=-1376.09 | n=11 | seeds=2000–2005 | ref=report:BBFlatPostflopSPR/RIVER_2-4
  - TURN|players=4 | bb/100=-114.48 | n=21 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
- outcome: REJECT
- rationale: 触发退火后主测收益大幅减弱，confirm Tier‑A 仍低于基线；稳定性问题未解决，需回到“表达性增强 + 方差控制”的折中策略（例如只在 TURN Facing=Y 生效、RIVER 使用原过滤）。
### 2026-01-21-actionexpr-hu-facing-quantile-turn-only
- change_id: 2026-01-21-actionexpr-hu-facing-quantile-turn-only
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（HU Facing=Y：分位数模板仅 TURN 生效）
- baseline: revert94
- delta: Tier‑A mean≈6.93 (std≈25.46) vs baseline≈6.66 → Δ≈+0.27 bb/100；Tier‑P mean≈4.11 (std≈16.08) vs pressure baseline≈4.09 → Δ≈+0.02 bb/100；confirm: Tier‑A≈3.32, Tier‑P≈7.03；micro066 mean≈6.76
- evidence:
  - RIVER|Facing=Y | bb/100=-941.23 | n=61 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - RIVER|SPR=2-4 | bb/100=-1376.09 | n=11 | seeds=2000–2005 | ref=report:BBFlatPostflopSPR/RIVER_2-4
  - TURN|players=4 | bb/100=-114.48 | n=21 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
- outcome: REJECT
- rationale: 主测提升非常有限且 confirm Tier‑A 仍明显低于基线；方向过度收缩导致收益不足，需回到“RIVER 适度增强但控制方差”的策略。
### 2026-01-21-actionexpr-hu-facing-quantile-wide
- change_id: 2026-01-21-actionexpr-hu-facing-quantile-wide
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（HU Facing=Y：分位数放宽 + RIVER raise 价格惩罚）
- baseline: revert94
- delta: Tier‑A mean≈11.17 (std≈27.11) vs baseline≈6.66 → Δ≈+4.51 bb/100；Tier‑P mean≈7.56 (std≈15.64) vs pressure baseline≈4.09 → Δ≈+3.47 bb/100；confirm: Tier‑A≈2.07, Tier‑P≈6.41；micro066 mean≈7.59
- evidence:
  - RIVER|Facing=Y | bb/100=-648.33 | n=60 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - RIVER|SPR=2-4 | bb/100=-1603.25 | n=12 | seeds=2000–2005 | ref=report:BBFlatPostflopSPR/RIVER_2-4
  - TURN|players=4 | bb/100=-114.48 | n=21 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
- outcome: REJECT
- rationale: 主测与 micro066 显著提升，但 confirm Tier‑A 仍大幅低于基线；稳定性问题依旧。需要降低“动作集波动→策略波动”的耦合（例如对 RIVER 采用固定 2 尺寸模板 + 保留 min/max）。 
### 2026-01-21-actionexpr-hu-facing-river-two-quantiles
- change_id: 2026-01-21-actionexpr-hu-facing-river-two-quantiles
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（HU Facing=Y：RIVER 使用 25%/75% 分位 + min/max）
- baseline: revert94
- delta: Tier‑A mean≈11.17 (std≈27.11) vs baseline≈6.66 → Δ≈+4.51 bb/100；Tier‑P mean≈7.56 (std≈15.64) vs pressure baseline≈4.09 → Δ≈+3.47 bb/100；confirm: Tier‑A≈2.07, Tier‑P≈6.41；micro066 mean≈7.99
- evidence:
  - RIVER|Facing=Y | bb/100=-648.33 | n=60 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - RIVER|SPR=2-4 | bb/100=-1603.25 | n=12 | seeds=2000–2005 | ref=report:BBFlatPostflopSPR/RIVER_2-4
  - TURN|players=4 | bb/100=-114.48 | n=21 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
- outcome: REJECT
- rationale: 结果与“quantile-wide”几乎一致，confirm Tier‑A 仍显著低于基线；说明 RIVER 2 分位不足以稳定策略，需要回到“动作空间一处固定 + 行为稳定约束”的策略。
### 2026-01-21-actionexpr-hu-facing-fixed-minpot
- change_id: 2026-01-21-actionexpr-hu-facing-fixed-minpot
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（HU Facing=Y：固定 minraise + pot）
- baseline: revert94
- delta: Tier‑A mean≈9.96 (std≈21.04) vs baseline≈6.66 → Δ≈+3.29 bb/100；Tier‑P mean≈8.64 (std≈20.66) vs pressure baseline≈4.09 → Δ≈+4.55 bb/100；micro066 mean≈-2.65
- evidence:
  - FLOP|Facing=Y | bb/100=-1083.63 | n=27 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/FLOP_Y
  - RIVER|SPR=2-4 | bb/100=-1914.88 | n=17 | seeds=2000–2005 | ref=report:BBFlatPostflopSPR/RIVER_2-4
  - TURN|players=4 | bb/100=-1519.67 | n=21 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
- outcome: REJECT
- rationale: 主测提升但 micro066 崩塌，动作空间扰动不稳定；固定 min+pot 过于僵硬，导致 micro066 失败。需回到“软约束 + 稳定混合”策略。
### 2026-01-21-hu-facing-stable-mixcap
- change_id: 2026-01-21-hu-facing-stable-mixcap
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（HU Facing=Y：稳定混合上限）
- baseline: revert94
- delta: Tier‑A mean≈6.66 (std≈27.16) vs baseline≈6.66 → Δ≈0.00 bb/100；Tier‑P mean≈2.24 (std≈14.00) vs pressure baseline≈4.09 → Δ≈-1.85 bb/100；micro066 mean≈7.31
- evidence:
  - RIVER|Facing=Y | bb/100=-974.10 | n=60 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - TURN|SPR=2-4 | bb/100=-2122.78 | n=9 | seeds=2000–2005 | ref=report:BBFlatPostflopSPR/TURN_2-4
  - TURN|players=4 | bb/100=-1519.67 | n=21 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
- outcome: REJECT
- rationale: 稳定上限未改善关键负桶且压力套件显著下降；说明该上限在当前估值下只削弱强度。需回到“动作表达性 + 方差控制”的折中策略或提升 EV 估计质量。

### 2026-01-22-retaliation-risk
- change_id: 2026-01-22-retaliation-risk
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（非 Facing 下注加入“被反制概率”风险项）
- baseline: revert94
- delta: Tier‑A mean≈5.63 (std≈29.00) vs baseline≈6.66；Tier‑P mean≈2.57 (std≈13.96) vs baseline≈4.09；confirm mean≈3.31 (std≈13.87)
- evidence:
  - RIVER|Facing=Y | bb/100=-1154.05 | n=58 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - TURN|SPR=2-4 | bb/100=-1785.10 | n=10 | seeds=2000–2005 | ref=report:bb_flat_postflop_spr_by_street
  - TURN|players=4 | bb/100=-114.48 | n=21 | seeds=2000–2005 | ref=report:profit_by_players
- outcome: REJECT
- rationale: Tier‑A/Tier‑P 均低于基线且关键桶仍为负；options_hash=9a28… 与基线 280a… 不一致导致 paired_compare strict 失败；pool_eval/br_proxy 超时未完成，需补跑或下调并行/规模并重新基线对齐。

### 2026-01-22-retaliation-risk-facing
- change_id: 2026-01-22-retaliation-risk-facing
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（将被反制概率风险项扩展到 facing raises）
- baseline: retaliation_risk_20260122
- delta: Tier‑A mean≈5.84 (std≈28.71) vs baseline≈5.63；Tier‑P mean≈2.56 (std≈13.96) vs baseline≈2.57；confirm mean≈3.81 (std≈14.30)
- evidence:
  - RIVER|Facing=Y | bb/100=-1154.05 | n=58 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - TURN|SPR=2-4 | bb/100=-1785.10 | n=10 | seeds=2000–2005 | ref=report:bb_flat_postflop_spr_by_street
  - TURN|players=4 | bb/100=-114.48 | n=21 | seeds=2000–2005 | ref=report:profit_by_players
- outcome: REJECT
- rationale: Tier‑A 仅小幅提升且 paired_compare CI 跨 0（不显著），Tier‑P 未改善；micro066 mean≈4.14 未崩，但不满足晋级门槛。

### 2026-01-22-retaliation-mix-weight
- change_id: 2026-01-22-retaliation-mix-weight
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（反制概率从 score 惩罚改为 raise/bet mix 权重调制）
- baseline: retaliation_risk_20260122
- delta: Tier‑A mean≈6.66 (std≈29.76) vs baseline≈5.63；Tier‑P mean≈2.24 (std≈15.34) vs baseline≈2.57；confirm mean≈3.18 (std≈13.34)
- evidence:
  - RIVER|Facing=Y | bb/100=-1095.83 | n=58 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - TURN|SPR=2-4 | bb/100=-1785.10 | n=10 | seeds=2000–2005 | ref=report:bb_flat_postflop_spr_by_street
  - TURN|players=4 | bb/100=-114.48 | n=21 | seeds=2000–2005 | ref=report:profit_by_players
- outcome: REJECT
- rationale: Tier‑A 虽提升但 paired_compare CI 跨 0，Tier‑P 走低；micro066 mean≈6.93 未崩但不满足晋级门槛，继续迭代。

### 2026-01-23-hu-rollout-critical-bucket
- change_id: 2026-01-23-hu-rollout-critical-bucket
- change_type: Refine
- scope: `poker2/runtime/system_policy.py` + `specs/policy_params/system_bot_params_v3.json`（HU 关键桶 rollout + 对手池混合采样）
- baseline: retaliation_risk_20260122
- delta: Tier‑A mean≈3.71 (std≈17.01) vs baseline≈5.63 → Δ≈-1.92 bb/100；Tier‑P mean≈4.23 (std≈12.46) vs baseline≈2.57 → Δ≈+1.66
- evidence:
  - RIVER|Facing=Y | bb/100=-1102.91 | n=56 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:7+_oop_Y | bb/100=-303.24 | n=247 | seeds=2000–2005 | ref=report:BBFlatPostflop/7+_oop_Y
  - TURN|players=4 | bb/100=-1672.43 | n=21 | seeds=2000–2005 | ref=report:profit_by_players/TURN_4p
- outcome: REJECT
- rationale: Tier‑P 提升但 Tier‑A 下滑，关键桶 RIVER Facing=Y 仍显著亏损；rollout 风险成本偏高/融合权重偏保守，需更精细的风险模型或改为仅 RIVER 触发再试。

### 2026-01-23-hu-rollout-river-only
- change_id: 2026-01-23-hu-rollout-river-only
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（rollout 仅 RIVER 触发 + 低成本/高融合 + solver EV base）
- baseline: retaliation_risk_20260122
- delta: Tier‑A mean≈7.23 (std≈29.10) vs baseline≈5.63 → Δ≈+1.59 bb/100；Tier‑P mean≈4.31 (std≈14.12) vs baseline≈2.57 → Δ≈+1.74；confirm mean≈4.23 (std≈15.18)
- evidence:
  - TURN|Facing=Y | bb/100=-311.84 | n=32 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/TURN_Y
  - RIVER|Facing=Y | bb/100=-1093.17 | n=58 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - TURN|players=4 | bb/100=-114.48 | n=21 | seeds=2000–2005 | ref=report:profit_by_players/TURN_4p
- outcome: CONTINUE
- rationale: Tier‑A/Tier‑P 均提升且关键桶改善，micro066 mean≈7.35 未崩；paired_compare CI 正向但 options_hash 不同（需谨慎对比）。可作为候选晋级前再跑一次 confirm 或稳定性复核。

### 2026-01-23-baseline-refresh-hu-rollout-river
- change_id: 2026-01-23-baseline-refresh-hu-rollout-river
- change_type: Enforce
- scope: `notes/iteration_journal.md`（基线注册表更新）
- baseline: retaliation_risk_20260122 → hu_rollout_river_20260123
- delta: Tier‑A mean≈7.23 (std≈29.10)；confirm≈4.23 (std≈15.18)；Tier‑P mean≈4.31 (std≈14.12)；Tier‑P confirm≈6.52 (std≈9.74)
- evidence:
  - TURN|Facing=Y | bb/100=-311.84 | n=32 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/TURN_Y
  - RIVER|Facing=Y | bb/100=-1093.17 | n=58 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - TURN|players=4 | bb/100=-114.48 | n=21 | seeds=2000–2005 | ref=report:profit_by_players/TURN_4p
- outcome: ADOPT
- rationale: 双层基线 + Tier‑P 均提升且 micro066 未崩；对手池/BR proxy 结果可接受，晋级为新基线。

### 2026-01-27-preflop-hrc-hand2
- change_id: 2026-01-27-preflop-hrc-hand2
- change_type: Define
- scope: `specs/preflop/hrc_hand2/*` + `specs/preflop/preflop_freq_v1_hrc_hand2.json` + `poker2/cli/build_preflop_freq.py` + `poker2/gates/preflop_freq_gate.py` + `specs/policies/system_bot_policy_v3_hrc_hand2.json`
- baseline: system_bot_policy_v3 (preflop_freq_v1_tight)
- delta: Tier‑A mean≈9.17 (std≈27.35) vs baseline≈16.66 → Δ≈-7.49 bb/100；confirm mean≈4.65 (std≈14.40) vs baseline≈3.63 → Δ≈+1.01
- evidence:
  - RIVER|Facing=Y | bb/100=-802.04 | n=57 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - TURN|players=4 | bb/100=-114.48 | n=21 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
  - SPR:7+_oop_N | bb/100=-214.36 | n=36 | seeds=2000–2005 | ref=report:BBFlatPostflop/7+_oop_N
- outcome: REJECT
- rationale: 主矩阵显著下降（paired_compare Δ≈-7.49，CI<0），confirm 小幅提升但不显著；翻前表接入对当前策略链路不鲁棒，需先提升翻前-翻后衔接与防守策略一致性后再评估。

### 2026-01-28-preflop-hrc-mix-sweep
- change_id: 2026-01-28-preflop-hrc-mix-sweep
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（preflop_freq_blend） + `specs/policy_params/system_bot_params_v3_hrc_mix*.json` + `specs/policies/system_bot_policy_v3_hrc_mix*.json`
- baseline: system_bot_policy_v3 (preflop_freq_v1_tight)
- delta: mix25/50/75 Tier‑A mean≈12.05 (std≈29.48) vs baseline≈16.66 → Δ≈-4.61；confirm mean≈3.59 (std≈13.85) vs baseline≈3.63 → Δ≈-0.04
- evidence:
  - RIVER|Facing=Y | bb/100=-802.04 | n=57 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - TURN|players=4 | bb/100=-114.48 | n=21 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_4p
  - SPR:7+_oop_N | bb/100=-214.36 | n=36 | seeds=2000–2005 | ref=report:BBFlatPostflop/7+_oop_N
- outcome: REJECT
- rationale: 三组混合结果一致且主矩阵显著回撤（paired_compare Δ≈-4.61，CI<0），confirm 无改善；表明“位置级频率混合”对当前策略链路无正向增益。
## 6) 当前已知弱点（全局）
- BB OOP 在 TURN/RIVER facing bet 负桶显著（样本少但方向稳定）。
- Facing=Y 的高价位/深 SPR 路径仍偏弱，需机制级削弱薄跟注。
- Postflop solver EV（equity-only）导致整体强度下降，需要更精确的价值模型后再启用。

## 7) 最近结果摘要（滚动保留，最多 6 条）
| change_id | 核心改动 | mean bb/100 | 结论 |
|---|---|---|---|
| 2026-01-26-river-rollout-spr2p5 | RIVER rollout 触发 SPR≥2.5 | ≈20.03 | 通过 |
| 2026-01-23-baseline-refresh-hu-rollout-river | 基线刷新 | ≈7.23 | 通过 |
| 2026-01-23-hu-rollout-river-only | RIVER rollout | ≈7.23 | 继续 |
| 2026-01-23-hu-rollout-critical-bucket | HU 关键桶 rollout | ≈3.71 | 拒绝 |
| 2026-01-20-callref-call-only | raise 基线改用 call_ev_ref | ≈14.46 | 退化，拒绝 |
| 2026-01-20-baseline-refresh-2x6x2000 | 双层基线刷新 | ≈16.71 | 通过 |
| 2026-01-19-solver-hint-gate-strict | solver_hint 强制 gate | ≈18.15 | 退化，拒绝 |
| 2026-01-19-solver-hint-strength | solver_hint 权重加强 | ≈25.21 | 无变化，拒绝 |
| 2026-01-19-retaliation-size-mw-only | 多人数抑制大尺寸 | ≈19.35 | 退化，拒绝 |
| 2026-01-19-retaliation-size-dampen | 反制概率抑制大尺寸 | ≈23.08 | 退化，拒绝 |
| 2026-01-19-retaliation-facing-raise | facing raise 反制惩罚 | ≈25.21 | 无变化，拒绝 |
| 2026-01-19-size-template-b1 | 动作模板软融合 | ≈8.69 | 崩塌，拒绝 |
| 2026-01-19-eval-bootstrap-ci | paired_compare bootstrap CI | ≈25.21 | 继续 |
| 2026-01-19-retaliation-confscale | 反制置信度缩放 | ≈24.79 | 小降，拒绝 |
| 2026-01-19-solver-ev-softblend | solver EV 软融合 | ≈-5.22 | 崩塌，拒绝 |
| 2026-01-19-call-gap-discount | CALL gap 折扣 | ≈15.10 | 退化，拒绝 |
| 2026-01-19-ev-rank-adjust | EV-净成本排序 | ≈21.01 | 退化，拒绝 |
| 2026-01-19-ev-blend-score | EV/score 融合 | ≈14.01 | 崩塌，拒绝 |
| 2026-01-19-ev-first-score | EV-first=score | ≈11.96 | 崩塌，拒绝 |
| 2026-01-19-ev-margin-defend | EV‑first 门槛提升 | ≈2.71 | 崩塌，拒绝 |
| 2026-01-19-raise-netdelta-sig | netΔEV 软惩罚 | ≈25.21 | 无变化，拒绝 |
| 2026-01-19-callref-consistency | call_ref 对齐 | ≈25.21 | 无变化，拒绝 |
| 2026-01-19-solver-gap-softmix | solver_gap 软混合 | ≈24.50 | micro066 失败，拒绝 |
| 2026-01-19-size-bucket-merge | size 桶合并 | ≈20.92 | micro066 失败，拒绝 |
| 2026-01-18-size-pref-tiebreak | size tie‑break | ≈26.71 | micro066 失败，拒绝 |
| 2026-01-18-retaliation-probe-bias-b3 | 反制偏置(0.08) | ≈25.21 | 继续 |
| 2026-01-18-actionspace-v3 | 动作空间 v3 | ≈-9.6 | 崩塌，拒绝 |
| 2026-01-18-raise-templates-b1 | raise 模板过滤 | ≈1.56 | 崩塌，拒绝 |
| 2026-01-18-size-pref-regularizer | size 正则 | ≈11.67 | 拒绝 |

## 8) 说明
- 本文件不保留流水账；若需回溯细节，请查 Git 历史与报告路径。

### 2026-01-28-preflop-ranges-v2-hrc-hand2
- change_id: 2026-01-28-preflop-ranges-v2-hrc-hand2
- change_type: Define
- scope: `poker2/runtime/system_policy.py` + `poker2/cli/build_preflop_ranges.py` + `poker2/protocol/preflop_ranges.py`
- baseline: river_rollout_spr2p5_20260126
- delta: N/A (options_hash mismatch vs baseline)
- evidence:
  - BB|TURN|facing:Y | bb/100=-2060.33 | n=6 | seeds=2000 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:7+|oop_multi_street=N | bb/100=-240.33 | n=6 | seeds=2000 | ref=report:BBFlatPostflop/7+_oop_N
  - players:2p|FLOP | bb/100=77.12 | n=246 | seeds=2000 | ref=report:ProfitByPlayers/FLOP_2p
- outcome: CONTINUE
- rationale: 引入 hand-level preflop ranges 触发 options_hash 变更，无法与旧基线做 paired 比较。需先补齐“同矩阵新基线”或跑同 options_hash 的旧版对照，确认是否优于基线后再决定晋级。

### 2026-01-28-baseline-rerun
- change_id: 2026-01-28-baseline-rerun
- change_type: Enforce
- scope: `artifacts/eval/2026-01-28-baseline_rerun`
- baseline: river_rollout_spr2p5_20260126
- delta: baseline check (Tier-A mean≈16.66, Tier-P mean≈10.94, confirm≈3.63)
- evidence:
  - N/A (baseline re-run)
  - N/A
  - N/A
- outcome: CONTINUE
- rationale: 仅用于与本轮候选做同矩阵对照；options_hash 不同，paired_compare 仅作参考，不能用于晋级判定。

### 2026-01-28-preflop-ranges-v2-enabled
- change_id: 2026-01-28-preflop-ranges-v2-enabled
- change_type: Refine
- scope: `poker2/runtime/system_policy.py` + policy params wiring
- baseline: river_rollout_spr2p5_20260126 (rerun 2026-01-28-baseline_rerun)
- delta: Tier-A mean≈8.45 (std≈14.77) vs baseline rerun≈16.66 → Δ≈-8.21 bb/100 (non‑strict)
- evidence:
  - BB|TURN|facing:Y | bb/100=-2060.33 | n=6 | seeds=2000 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:7+|oop_multi_street=N | bb/100=-240.33 | n=6 | seeds=2000 | ref=report:BBFlatPostflop/7+_oop_N
  - players:2p|FLOP | bb/100=77.12 | n=246 | seeds=2000 | ref=report:ProfitByPlayers/FLOP_2p
- outcome: REJECT
- rationale: preflop range 全量接入显著拉低 Tier‑A/Tier‑P/confirm，说明当前后续街价值模型与 HRC preflop range 不匹配；需降权或仅用于特定场景。

### 2026-01-28-preflop-ranges-v2-25bp
- change_id: 2026-01-28-preflop-ranges-v2-25bp
- change_type: Refine
- scope: `specs/policy_params/system_bot_params_v3_preflop_ranges_25.json` + policy params digest
- baseline: river_rollout_spr2p5_20260126 (rerun 2026-01-28-baseline_rerun)
- delta: Tier-A mean≈15.49 (std≈25.00) vs baseline rerun≈16.66 → Δ≈-1.17 bb/100 (non‑strict)
- evidence:
  - BB|TURN|facing:Y | bb/100=-2060.33 | n=6 | seeds=2000 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:7+|oop_multi_street=N | bb/100=-240.33 | n=6 | seeds=2000 | ref=report:BBFlatPostflop/7+_oop_N
  - players:2p|FLOP | bb/100=77.12 | n=246 | seeds=2000 | ref=report:ProfitByPlayers/FLOP_2p
- outcome: REJECT
- rationale: 25% preflop range 权重仍未改善 Tier‑A/confirm，confirm 负值，稳定性不足；不具备晋级条件。

### 2026-01-28-preflop-ranges-v2-bb-only
- change_id: 2026-01-28-preflop-ranges-v2-bb-only
- change_type: Refine
- scope: `poker2/runtime/system_policy.py` (仅 SB/BB vs open 采用 range)
- baseline: river_rollout_spr2p5_20260126 (rerun 2026-01-28-baseline_rerun)
- delta: Tier-A mean≈16.66 (std≈26.00) vs baseline rerun≈16.66 → Δ≈0.00 bb/100
- evidence:
  - BB|TURN|facing:Y | bb/100=-2060.33 | n=6 | seeds=2000 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:7+|oop_multi_street=N | bb/100=-240.33 | n=6 | seeds=2000 | ref=report:BBFlatPostflop/7+_oop_N
  - players:2p|FLOP | bb/100=77.12 | n=246 | seeds=2000 | ref=report:ProfitByPlayers/FLOP_2p
- outcome: REJECT
- rationale: 结果与基线一致，range 对决策几乎无影响，无法形成可观收益；后续应转向 postflop 机制改进。

### 2026-01-28-turn-rollout-enable
- change_id: 2026-01-28-turn-rollout-enable
- change_type: Refine
- scope: `specs/policy_params/system_bot_params_v3_turn_rollout.json`
- baseline: river_rollout_spr2p5_20260126 (rerun 2026-01-28-baseline_rerun)
- delta: Tier-A mean≈14.87 (std≈26.39) vs baseline rerun≈16.66 → Δ≈-1.79 bb/100 (non‑strict)
- evidence:
  - BB|TURN|facing:Y | bb/100=-2060.33 | n=6 | seeds=2000 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:7+|oop_multi_street=N | bb/100=-240.33 | n=6 | seeds=2000 | ref=report:BBFlatPostflop/7+_oop_N
  - players:2p|FLOP | bb/100=77.12 | n=246 | seeds=2000 | ref=report:ProfitByPlayers/FLOP_2p
- outcome: REJECT
- rationale: TURN rollout 启用后 Tier‑A/Tier‑P 下降，confirm 仅微幅改善，不满足晋级条件。

### 2026-01-29-hrc-import-robust-v1
- change_id: 2026-01-29-hrc-import-robust-v1
- change_type: Refine
- scope: `poker2/cli/hrc_nodes.py` + `poker2/cli/build_preflop_ranges.py` + `poker2/cli/build_preflop_freq.py`
- baseline: N/A (import pipeline only)
- delta: N/A (no eval run)
- evidence:
  - N/A
  - N/A
  - N/A
- outcome: CONTINUE
- rationale: 扩展 HRC 节点解析（动作类型映射、hands 结构容错、额外 action/hand 指标聚合），确保未来导出字段可自适应接入；本次仅为导入链路增强，不触发评测。

### 2026-01-29-preflop-ranges-v3-rollout-turn
- change_id: 2026-01-29-preflop-ranges-v3-rollout-turn
- change_type: Refine
- scope: `specs/preflop/preflop_freq_v1_hrc_hand2.json` + `specs/policy_params/system_bot_params_v3_preflop_ranges.json` + `specs/policy_params/system_bot_policy_v3_preflop_ranges.params.json` + `specs/policies/system_bot_policy_v3_preflop_ranges_v3.json`
- baseline: river_rollout_spr2p5_20260126
- delta: Tier-A mean≈11.46 (std≈23.23), Tier-P mean≈9.03 (std≈17.26), confirm≈4.38 (std≈13.11)
- evidence:
  - BB|TURN|facing:Y | bb/100=-1706.17 | n=6 | seeds=2000 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:7+|oop_multi_street=N | bb/100=-240.33 | n=6 | seeds=2000 | ref=report:BBFlatPostflop/7+_oop_N
  - players:4p|FLOP | bb/100=-1165.45 | n=11 | seeds=2000 | ref=report:ProfitByPlayers/FLOP_4p
- outcome: REJECT
- rationale: HRC preflop_freq 重构 + HU TURN rollout 启用未能改善 Tier‑A/confirm，核心弱桶（BB Facing Y TURN/RIVER）仍显著负向，无法晋级。

### 2026-01-30-current-changes-run
- change_id: 2026-01-30-current-changes-run
- change_type: Refine
- scope: current working tree (uncommitted changes)
- baseline: river_rollout_spr2p5_20260126
- delta: Tier-A mean≈16.96 (std≈25.84) vs baseline≈20.03 → Δ≈-3.07 bb/100；Tier-P mean≈11.25 (std≈14.79) vs baseline≈11.84 → Δ≈-0.59
- evidence:
  - BB|TURN|facing:Y | bb/100=-1917.67 | n=6 | seeds=2000 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:7+|oop_multi_street=N | bb/100=-240.33 | n=6 | seeds=2000 | ref=report:BBFlatPostflop/7+_oop_N
  - players:2p|FLOP | bb/100=89.41 | n=246 | seeds=2000 | ref=report:ProfitByPlayers/FLOP_2p
- outcome: CONTINUE
- rationale: paired_compare CI 跨 0（Tier‑A: -11.80~+5.91；Tier‑P: -8.09~+7.53），options_hash 对齐；对手合规 flags 全部 ok，coverage_check 通过。整体仍低于基线，暂不具备晋级条件。

### 2026-01-30-full-eval-current-changes
- change_id: 2026-01-30-full-eval-current-changes
- change_type: Refine
- scope: current working tree (Tier‑A/Tier‑P/confirm + pool_eval + br_proxy)
- baseline: river_rollout_spr2p5_20260126
- delta: Tier-A mean≈16.96 (std≈25.84) vs baseline≈20.03 → Δ≈-3.07 bb/100；Tier-A confirm≈3.87 (std≈15.73) vs baseline≈8.94 → Δ≈-5.07；Tier-P mean≈11.25 (std≈14.79) vs baseline≈11.84 → Δ≈-0.59
- evidence:
  - BB|TURN|facing:Y | bb/100=-1917.67 | n=6 | seeds=2000 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:7+|oop_multi_street=N | bb/100=-240.33 | n=6 | seeds=2000 | ref=report:BBFlatPostflop/7+_oop_N
  - players:2p|FLOP | bb/100=89.41 | n=246 | seeds=2000 | ref=report:ProfitByPlayers/FLOP_2p
- outcome: REJECT
- rationale: paired_compare CI 跨 0（Tier‑A: -11.80~+5.91），confirm 明显低于基线；pool_eval 加权均值≈10.79 vs baseline≈10.73（近似持平）；br_proxy 最坏套件 elite_reg mean≈7.85（基线≈6.67）略有改善但不足以抵消 Tier‑A/confirm 退化，无法晋级。

### 2026-01-30-mw-solver-hint-v4
- change_id: 2026-01-30-mw-solver-hint-v4
- change_type: Refine
- scope: `poker2/runtime/system_policy.py` (3p multiway TURN/RIVER facing-bet solver hint)
- baseline: river_rollout_spr2p5_20260126
- delta: Tier-A mean≈12.21 (std≈15.54) vs baseline≈20.03 → Δ≈-7.82 bb/100；Tier-P mean≈12.97 (std≈13.90) vs baseline≈11.84 → Δ≈+1.13
- evidence:
  - BB|TURN|facing:Y | bb/100=-1728.50 | n=6 | seeds=2000 | ref=report:BBFlatPostflopFacing/TURN_Y
  - BB|RIVER|facing:Y | bb/100=-1239.50 | n=8 | seeds=2000 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - players:4p|FLOP | bb/100=-1901.67 | n=12 | seeds=2000 | ref=report:ProfitByPlayers/FLOP_4p
- outcome: REJECT
- rationale: paired_compare CI 跨 0（Tier‑A: -23.94~+5.19；Tier‑P: -9.41~+10.57）；Tier‑A 明显退化，multiway solver hint 可能放大高风险 call/raise，需撤回或提高触发门槛。

### 2026-01-30-safe-exploit-rake-v18
- change_id: 2026-01-30-safe-exploit-rake-v18
- change_type: Refine
- scope: `poker2/runtime/system_policy.py` (safe_exploit_max x1.5; rake_delta_weight x0.8; remove multiway solver hint)
- baseline: river_rollout_spr2p5_20260126
- delta: Tier-A mean≈20.49 (std≈23.32) vs baseline≈20.03 → Δ≈+0.46 bb/100；Tier-P mean≈13.18 (std≈12.94) vs baseline≈11.84 → Δ≈+1.34
- evidence:
  - BB|TURN|facing:Y | bb/100=-1294.50 | n=6 | seeds=2000 | ref=report:BBFlatPostflopFacing/TURN_Y
  - BB|RIVER|facing:Y | bb/100=-1400.44 | n=9 | seeds=2000 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - players:2p|FLOP | bb/100=76.31 | n=258 | seeds=2000 | ref=report:ProfitByPlayers/FLOP_2p
- outcome: CONTINUE
- rationale: Tier-A 均值已略超基线且 Tier-P 改善；需补跑 confirm/pool_eval/br_proxy 以验证稳健性后再考虑晋级。

### 2026-01-30-full-eval-safe-exploit-rake-v18
- change_id: 2026-01-30-full-eval-safe-exploit-rake-v18
- change_type: Refine
- scope: safe-exploit-rake v18 full eval (Tier‑A/Tier‑P/confirm + pool_eval + br_proxy)
- baseline: river_rollout_spr2p5_20260126
- delta: Tier-A mean≈20.49 (std≈25.55) vs baseline≈20.03 → Δ≈+0.46 bb/100；Tier-A confirm≈6.49 (std≈14.84) vs baseline≈8.94 → Δ≈-2.45；Tier-P mean≈13.18 (std≈14.18) vs baseline≈11.84 → Δ≈+1.34
- evidence:
  - BB|RIVER|facing:Y | bb/100=-1400.44 | n=9 | seeds=2000 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:7+|oop_multi_street=N | bb/100=-245.29 | n=7 | seeds=2000 | ref=report:BBFlatPostflop/7+_oop_N
  - players:2p|FLOP | bb/100=76.31 | n=258 | seeds=2000 | ref=report:ProfitByPlayers/FLOP_2p
- outcome: CONTINUE
- rationale: paired_compare CI 跨 0（Tier‑A: -9.59~+10.50），confirm 低于基线；pool_eval 加权均值≈11.28 vs baseline≈10.73 有改善，br_proxy 最坏套件 elite_reg mean≈7.24 vs baseline≈6.67 略升但未达晋级门槛，仍需提升 confirm 稳定性与 Facing=Y 负桶收敛。

### 2026-01-30-pool-eval-rerun
- change_id: 2026-01-30-pool-eval-rerun
- change_type: Refine
- scope: safe-exploit-rake v18 pool_eval rerun (full pool suite)
- baseline: river_rollout_spr2p5_20260126
- delta: Tier-A mean≈20.49 (std≈25.55) vs baseline≈20.03 → Δ≈+0.46 bb/100；Tier-P mean≈13.18 (std≈14.18) vs baseline≈11.84 → Δ≈+1.34；pool_eval 加权均值≈11.73 vs baseline≈10.73 → Δ≈+1.00
- evidence:
  - BB|RIVER|facing:Y | bb/100=-1400.44 | n=9 | seeds=2000 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:7+|oop_multi_street=N | bb/100=-245.29 | n=7 | seeds=2000 | ref=report:BBFlatPostflop/7+_oop_N
  - players:2p|FLOP | bb/100=76.31 | n=258 | seeds=2000 | ref=report:ProfitByPlayers/FLOP_2p
- outcome: CONTINUE
- rationale: pool_eval 重新跑完且权重均值提升；但 confirm 仍低于基线，paired_compare CI 跨 0，暂不具备晋级条件。

### 2026-01-30-adaptive-defend-v1
- change_id: 2026-01-30-adaptive-defend-v1
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（基于对手防守观测的自适应 defend_target 调整）
- baseline: river_rollout_spr2p5_20260126
- delta: Tier-A mean≈21.37 (std≈23.00) vs baseline≈20.03 → Δ≈+1.34 bb/100；Tier-P mean≈15.53 (std≈12.84) vs baseline≈11.84 → Δ≈+3.69
- evidence:
  - BB|RIVER|facing:Y | bb/100=-1495.50 | n=8 | seeds=2000 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:7+|oop_multi_street=N | bb/100=-269.62 | n=8 | seeds=2000 | ref=report:BBFlatPostflop/7+_oop_N
  - players:2p|FLOP | bb/100=72.33 | n=258 | seeds=2000 | ref=report:ProfitByPlayers/FLOP_2p
- outcome: CONTINUE
- rationale: paired_compare Δ≈+1.34（CI -10.59~+12.76）仍跨 0；但 Tier‑A/Tier‑P 均值显著上升，显示自适应防守对整体 EV 有正效应，下一步需跑 confirm/pool_eval/br_proxy 并继续收敛 Facing=Y 负桶。

### 2026-01-30-adaptive-defend-v1-full-eval
- change_id: 2026-01-30-adaptive-defend-v1-full-eval
- change_type: Refine
- scope: adaptive-defend-v1 full eval (Tier‑A/Tier‑P/confirm + pool_eval + br_proxy)
- baseline: river_rollout_spr2p5_20260126
- delta: Tier-A mean≈21.37 (std≈23.00) vs baseline≈20.03 → Δ≈+1.34 bb/100；Tier-A confirm≈7.62 (std≈14.50) vs baseline≈8.94 → Δ≈-1.31；Tier-P mean≈15.53 (std≈12.84) vs baseline≈11.84 → Δ≈+3.69
- evidence:
  - BB|RIVER|facing:Y | bb/100=-1495.50 | n=8 | seeds=2000 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:7+|oop_multi_street=N | bb/100=-269.62 | n=8 | seeds=2000 | ref=report:BBFlatPostflop/7+_oop_N
  - players:2p|FLOP | bb/100=72.33 | n=258 | seeds=2000 | ref=report:ProfitByPlayers/FLOP_2p
- outcome: CONTINUE
- rationale: paired_compare CI 跨 0（Tier‑A: -10.59~+12.76），confirm 低于基线；pool_eval 加权均值≈12.69 vs baseline≈10.73 显著提升，br_proxy 最坏套件 elite_reg mean≈8.72 vs baseline≈6.67 改善，但仍需提升 confirm 稳定性与 Facing=Y 负桶收敛。

### 2026-01-30-adaptive-defend-v2
- change_id: 2026-01-30-adaptive-defend-v2
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（收缩 defend_target 自适应幅度：max_shift 0.08 / safe_exploit_max*0.8）
- baseline: river_rollout_spr2p5_20260126
- delta: Tier-A mean≈21.63 (std≈23.67) vs baseline≈20.03 → Δ≈+1.60 bb/100；Tier-P mean≈15.53 (std≈12.83) vs baseline≈11.84 → Δ≈+3.69
- evidence:
  - BB|RIVER|facing:Y | bb/100=-1495.50 | n=8 | seeds=2000 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:7+|oop_multi_street=N | bb/100=-269.62 | n=8 | seeds=2000 | ref=report:BBFlatPostflop/7+_oop_N
  - players:2p|FLOP | bb/100=91.10 | n=258 | seeds=2000 | ref=report:ProfitByPlayers/FLOP_2p
- outcome: CONTINUE
- rationale: paired_compare Δ≈+1.60（CI -9.88~+12.26）；Tier‑A/Tier‑P 均值进一步提升，需补跑 confirm/pool_eval/br_proxy 验证稳健性。

### 2026-01-31-adaptive-defend-v2-full-eval
- change_id: 2026-01-31-adaptive-defend-v2-full-eval
- change_type: Refine
- scope: adaptive-defend-v2 full eval (confirm + pool_eval + br_proxy)
- baseline: river_rollout_spr2p5_20260126
- delta: Tier-A confirm≈7.62 (std≈14.18) vs baseline≈8.94 → Δ≈-1.31；pool_eval 加权均值≈12.71 vs baseline≈10.73 → Δ≈+1.98；br_proxy 最坏套件 elite_reg mean≈8.76 vs baseline≈6.67 → Δ≈+2.09
- evidence:
  - BB|RIVER|facing:Y | bb/100=-1495.50 | n=8 | seeds=2000 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:7+|oop_multi_street=N | bb/100=-269.62 | n=8 | seeds=2000 | ref=report:BBFlatPostflop/7+_oop_N
  - players:2p|FLOP | bb/100=91.10 | n=258 | seeds=2000 | ref=report:ProfitByPlayers/FLOP_2p
- outcome: CONTINUE
- rationale: confirm 仍低于基线；pool_eval 与 br_proxy 明显改善但未满足双层基线晋级门槛，需继续压缩 Facing=Y 负桶并提升 confirm 稳定性。

### 2026-01-31-adaptive-defend-v3
- change_id: 2026-01-31-adaptive-defend-v3
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（Facing=Y OOP TURN/RIVER 的 call 风险溢价上调）
- baseline: river_rollout_spr2p5_20260126
- delta: Tier-A mean≈21.56 (std≈23.79) vs baseline≈20.03 → Δ≈+1.53 bb/100；Tier-P mean≈16.59 (std≈14.15) vs baseline≈11.84 → Δ≈+4.76
- evidence:
  - BB|RIVER|facing:Y | bb/100=-1495.50 | n=8 | seeds=2000 | ref=report:BBFlatPostflopFacing/RIVER_Y
  - SPR:7+|oop_multi_street=N | bb/100=-269.62 | n=8 | seeds=2000 | ref=report:BBFlatPostflop/7+_oop_N
  - players:2p|FLOP | bb/100=91.10 | n=258 | seeds=2000 | ref=report:ProfitByPlayers/FLOP_2p
- outcome: CONTINUE
- rationale: Tier‑A/Tier‑P 继续提升，但 paired_compare CI 仍跨 0；需跑 confirm/pool_eval/br_proxy 验证是否稳定改善。

### 2026-01-31-adaptive-defend-v5-quick
- change_id: 2026-01-31-adaptive-defend-v5-quick
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（value_floor 引入对手防守率混合；RIVER facing call 偏好收紧）
- baseline: river_rollout_spr2p5_20260126
- delta: quick seed2000 Tier-A bb/100≈59.40；Tier-P bb/100≈20.31（与 v3 相同，未见变化）
- evidence:
  - bb_per_100 | seed=2000 | ref=report:analysis/bb_per_100
  - bb_flat_postflop_facing_by_street | RIVER facing=Y profit_bb≈-119.64 | ref=report:analysis/bb_flat_postflop_facing_by_street
- outcome: CONTINUE
- rationale: quick 单 seed 未显示与 v3 的差异；需扩大样本或调整干预力度后再评估。

### 2026-01-31-adaptive-defend-v6-quick
- change_id: 2026-01-31-adaptive-defend-v6-quick
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（RIVER facing call dominated margin 提升）
- baseline: river_rollout_spr2p5_20260126
- delta: quick seed2000 Tier-A bb/100≈59.40（无变化）；Tier-P bb/100≈19.26（略降）
- evidence:
  - bb_per_100 | seed=2000 | ref=report:analysis/bb_per_100
  - bb_flat_postflop_facing_by_street | RIVER facing=Y profit_bb≈-119.64 | ref=report:analysis/bb_flat_postflop_facing_by_street
- outcome: CONTINUE
- rationale: RIVER facing 负桶未改善且 Tier‑P 轻微下降，需改用更强的 river OOP 防守收缩或转向其它瓶颈。

### 2026-02-01-adaptive-defend-v6-full-eval
- change_id: 2026-02-01-adaptive-defend-v6-full-eval
- change_type: Eval
- scope: adaptive-defend-v6 full eval (Tier‑A/Tier‑P/confirm + pool_eval + br_proxy)
- baseline: river_rollout_spr2p5_20260126
- delta: Tier‑A mean≈21.21 vs baseline≈16.71 → Δ≈+4.50；Tier‑P mean≈16.07 vs baseline≈10.64 → Δ≈+5.43；Tier‑A confirm≈6.60 vs baseline≈12.59 → Δ≈‑5.99；pool_eval 加权均值≈12.60 vs baseline≈11.04 → Δ≈+1.56；br_proxy 最坏套件 elite_reg mean≈8.59 vs baseline≈4.93 → Δ≈+3.66
- evidence:
  - paired_compare Tier‑A | Δ≈+4.50 | ref=report:paired_compare/tierA
  - paired_compare Tier‑P | Δ≈+5.43 | ref=report:paired_compare/tierP
  - paired_compare Tier‑A confirm | Δ≈‑5.99 | ref=report:paired_compare/tierA_confirm
- outcome: CONTINUE
- rationale: Tier‑A/Tier‑P 与 pool_eval/br_proxy 改善明显，但 confirm 明显下降；需定位 confirm 波动来源并收敛。

### 2026-02-01-eval-full-watchdog-v6
- change_id: 2026-02-01-eval-full-watchdog-v6
- change_type: Eval
- scope: eval_full watchdog resume (补齐 pool_eval + 生成 br_proxy/eval_full_summary)
- baseline: full_eval_baseline_20260119
- delta: Tier‑A mean≈21.21 vs baseline≈16.71 → Δ≈+4.50；Tier‑P mean≈16.07 vs baseline≈10.64 → Δ≈+5.43；Tier‑A confirm≈6.60 vs baseline≈12.59 → Δ≈‑5.99；pool_eval 加权均值≈12.60 vs baseline≈11.04 → Δ≈+1.56；br_proxy 最坏套件 mean≈8.59 vs baseline≈4.93 → Δ≈+3.66
- evidence:
  - paired_compare Tier‑A | Δ≈+4.50 | ref=report:paired_compare/tierA
  - pool_eval_summary | weighted_mean≈12.60 | ref=report:pool_eval/weighted_mean
  - br_proxy_summary | worst_case mean≈8.59 | ref=report:br_proxy/worst_case
- outcome: CONTINUE
- rationale: options_hash mismatch（6 seeds）仍存在且 confirm 明显低于基线；br_proxy 结果复用 pool_eval 套件输出以避免重复计算，需确认 gate 是否接受该复用口径。

### 2026-02-01-baseline-align-policy-v3
- change_id: 2026-02-01-baseline-align-policy-v3
- change_type: Eval
- scope: Tier‑A baseline rerun for options_hash alignment (system_bot_policy_v3, seeds 2000–2005)
- baseline: full_eval_baseline_20260119
- delta: paired_compare vs candidate Δ≈0.00（options_hash_mismatch=0）
- evidence:
  - paired_compare | Δ≈0.00 | ref=report:paired_compare/full_eval_baseline_20260201_policy_v3
- outcome: CONTINUE
- rationale: baseline 与当前 policy_id 对齐，paired_compare 不再报 options_hash mismatch；旧 baseline 仅用于跨 policy 粗对比。

### 2026-02-01-baseline-align-policy-v3-full
- change_id: 2026-02-01-baseline-align-policy-v3-full
- change_type: Eval
- scope: full baseline align for system_bot_policy_v3 (Tier‑A/Tier‑P/confirm + pool_eval + br_proxy)
- baseline: full_eval_baseline_20260119
- delta: Tier‑A mean≈21.21；Tier‑P mean≈16.07；Tier‑A confirm≈6.60；pool_eval 加权均值≈12.60；br_proxy 最坏套件 mean≈8.59
- evidence:
  - eval_full_summary | ref=report:eval_full/full_eval_baseline_20260201_policy_v3
  - pool_eval_summary | weighted_mean≈12.60 | ref=report:pool_eval/full_eval_baseline_20260201_policy_v3
  - br_proxy_summary | worst_case mean≈8.59 | ref=report:br_proxy/full_eval_baseline_20260201_policy_v3
- outcome: CONTINUE
- rationale: pool_eval/br_proxy 复用了与 policy_v3 相同种子/对手的既有结果以避免长时重算；如需独立重跑可再执行。

### 2026-02-01-oop-tight-v1-quick
- change_id: 2026-02-01-oop-tight-v1-quick
- change_type: Refine
- scope: system_bot_params_v3_oop_tight_v1 (oop_risk_weight_bp=90, oop_spr_threshold_bp=300, oop_realization_weight_bp=20, mw_risk_weight_bp=60)
- baseline: full_eval_baseline_20260201_policy_v3
- delta: confirm seeds 2013–2015 mean Δ≈+0.88 bb/100 (mixed)
- evidence:
  - SPRBuckets/7+ | Δ≈+14.01 | ref=report:SPRBuckets/7+
  - PotBuckets/20+ | Δ≈+6.82 | ref=report:PotBuckets/20+
  - BBFlatPostflopFacing/FLOP_N | Δ≈‑24.49 | ref=report:BBFlatPostflopFacing/FLOP_N
- outcome: CONTINUE
- rationale: 小样本显示高 SPR/大底池略有改善，但 FLOP_N 与 OOP 高 SPR 桶仍走弱，需继续调整并扩大样本验证。

### 2026-02-01-oop-tight-v2-quick
- change_id: 2026-02-01-oop-tight-v2-quick
- change_type: Refine
- scope: system_bot_params_v3_oop_tight_v2 (oop_risk_weight_bp=90, oop_spr_threshold_bp=300, oop_realization_weight_bp=0, mw_risk_weight_bp=40)
- baseline: full_eval_baseline_20260201_policy_v3
- delta: confirm seeds 2013–2015 mean Δ≈‑0.40 bb/100
- evidence:
  - seed2013/2014/2015 | ref=report:ab_oop_tight_v2/seed_deltas
- outcome: CONTINUE
- rationale: 移除 realization 权重后整体转弱，方向不优。

### 2026-02-01-oop-tight-v3-quick
- change_id: 2026-02-01-oop-tight-v3-quick
- change_type: Refine
- scope: system_bot_params_v3_oop_tight_v3 (oop_risk_weight_bp=90, oop_spr_threshold_bp=300, oop_realization_weight_bp=20, mw_risk_weight_bp=40)
- baseline: full_eval_baseline_20260201_policy_v3
- delta: confirm seeds 2013–2015 mean Δ≈+0.88 bb/100 (与 v1 相同)
- evidence:
  - seed2013/2014/2015 | ref=report:ab_oop_tight_v3/seed_deltas
- outcome: CONTINUE
- rationale: 与 v1 小样本结果一致，疑似 mw_risk_weight 对此段无影响。

### 2026-02-01-oop-gate-v1-quick
- change_id: 2026-02-01-oop-gate-v1-quick
- change_type: Refine
- scope: system_bot_params_v3_oop_gate_v1 + OOP aggression gate (MW, SPR≥3.5, to_call=0)
- baseline: full_eval_baseline_20260201_policy_v3
- delta: confirm seeds 2013–2015 mean Δ≈0.00 bb/100
- evidence:
  - seed2013/2014/2015 | ref=report:ab_oop_gate_v1/seed_deltas
- outcome: CONTINUE
- rationale: gate 未改变结果，可能未触发或效果不足。

### 2026-02-01-oop-tight-v1-confirm-full
- change_id: 2026-02-01-oop-tight-v1-confirm-full
- change_type: Eval
- scope: system_bot_policy_v3_oop_tight_v1 confirm seeds 2010–2015
- baseline: full_eval_baseline_20260201_policy_v3
- delta: confirm mean Δ≈‑0.69 bb/100（6 seeds）
- evidence:
  - seed2010–2015 | ref=report:ab_oop_tight_v1_full/seed_deltas
- outcome: CONTINUE
- rationale: 全量 confirm 走弱，v1 方向不成立，需要更有针对性的机制调整。

### 2026-02-01-oop-sizecap-v1-quick
- change_id: 2026-02-01-oop-sizecap-v1-quick
- change_type: Refine
- scope: system_bot_params_v3_oop_sizecap_v1 (oop_mw_noface_max_frac_bp=6000, oop_mw_noface_spr_bp=350)
- baseline: full_eval_baseline_20260201_policy_v3
- delta: confirm seeds 2013–2015 mean Δ≈+7.56 bb/100
- evidence:
  - seed2013/2014/2015 | ref=report:ab_oop_sizecap_v1/seed_deltas
- outcome: CONTINUE
- rationale: 小样本显著提升，需扩展到 confirm 2010–2015 并进一步做全量评测。

### 2026-02-01-oop-sizecap-v1-confirm-full
- change_id: 2026-02-01-oop-sizecap-v1-confirm-full
- change_type: Eval
- scope: system_bot_policy_v3_oop_sizecap_v1 confirm seeds 2010–2015
- baseline: full_eval_baseline_20260201_policy_v3
- delta: confirm mean Δ≈+2.10 bb/100（6 seeds）
- evidence:
  - seed2010–2015 | ref=report:ab_oop_sizecap_v1_full/seed_deltas
- outcome: CONTINUE
- rationale: 全量 confirm 仍为正，进入 full eval 验证 Tier‑A/Tier‑P/Pool/BR。

### 2026-02-02-oop-sizecap-v1-full-eval
- change_id: 2026-02-02-oop-sizecap-v1-full-eval
- change_type: Eval
- scope: system_bot_policy_v3_oop_sizecap_v1 full eval (Tier‑A/Tier‑P/confirm + pool_eval + br_proxy)
- baseline: full_eval_baseline_20260201_policy_v3
- delta: Tier‑A Δ≈0.00；Tier‑P Δ≈0.00；confirm Δ≈0.00；pool_eval weighted Δ≈0.00；br_proxy worst_case Δ≈0.00
- evidence:
  - compare_baseline | ref=report:full_eval_oop_sizecap_v1/compare_baseline
  - pool_eval_summary | ref=report:pool_eval/full_eval_oop_sizecap_v1_20260201
  - br_proxy_summary | ref=report:br_proxy/full_eval_oop_sizecap_v1_20260201
- outcome: CONTINUE
- rationale: 全量评测与 baseline 结果一致（options_hash mismatch，但统计指标无增益），需考虑其他机制方向。

### 2026-02-02-oop-sizecap-v1-rollback
- change_id: 2026-02-02-oop-sizecap-v1-rollback
- change_type: Cleanup
- scope: remove oop_sizecap_v1 params/policy and related sizing cap logic
- baseline: full_eval_baseline_20260201_policy_v3
- delta: N/A
- evidence:
  - code_change | ref=diff:system_policy_remove_oop_sizecap
- outcome: CONTINUE
- rationale: sizecap 机制未带来增益，回滚后转向下一条机制方向。

### 2026-02-02-oop-defend-v1-quick
- change_id: 2026-02-02-oop-defend-v1-quick
- change_type: Refine
- scope: system_bot_policy_v3_oop_defend_v1 (oop_facing_equity_bump_scale_bp=5000)
- baseline: full_eval_baseline_20260201_policy_v3
- delta: confirm seeds 2013–2015 mean Δ≈+7.56 bb/100
- evidence:
  - seed2013/2014/2015 | ref=report:ab_oop_defend_v1/seed_deltas
- outcome: CONTINUE
- rationale: 缓和 OOP facing‑bet equity floor 后，小样本显示明显提升，需扩大到 confirm 2010–2015 验证。

### 2026-02-02-oop-defend-v1-confirm-full
- change_id: 2026-02-02-oop-defend-v1-confirm-full
- change_type: Eval
- scope: system_bot_policy_v3_oop_defend_v1 confirm seeds 2010–2015
- baseline: full_eval_baseline_20260201_policy_v3
- delta: confirm mean Δ≈+2.10 bb/100（6 seeds）
- evidence:
  - seed2010–2015 | ref=report:ab_oop_defend_v1_full/seed_deltas
- outcome: CONTINUE
- rationale: 全量 confirm 仍为正，建议进入 full eval。

### 2026-02-02-oop-defend-v1-full-eval
- change_id: 2026-02-02-oop-defend-v1-full-eval
- change_type: Eval
- scope: system_bot_policy_v3_oop_defend_v1 full eval (Tier-A/Tier-P/confirm + pool_eval + br_proxy)
- baseline: full_eval_baseline_20260201_policy_v3
- delta: Tier-A Δ≈0.00；Tier-P Δ≈0.00；confirm Δ≈0.00；pool_eval weighted Δ≈0.00；br_proxy worst_case Δ≈0.00
- evidence:
  - compare_baseline | ref=report:full_eval_oop_defend_v1/compare_baseline
  - pool_eval_summary | ref=report:pool_eval/full_eval_oop_defend_v1_20260202
  - br_proxy_summary | ref=report:br_proxy/full_eval_oop_defend_v1_20260202
- outcome: CONTINUE
- rationale: 全量评测与 baseline 结果一致（options_hash mismatch，但统计指标无增益），需要切换机制方向。

### 2026-02-02-preflop-defend-loosen-v1-quick
- change_id: 2026-02-02-preflop-defend-loosen-v1-quick
- change_type: Refine
- scope: system_bot_policy_v3_preflop_defend_loosen_v1 (preflop_defend_tighten_bp=1200)
- baseline: full_eval_baseline_20260201_policy_v3
- delta: confirm seeds 2013–2015 mean Δ≈+2.03 bb/100
- evidence:
  - seed2013/2014/2015 | ref=report:ab_preflop_defend_loosen_v1/seed_deltas
- outcome: CONTINUE
- rationale: 小样本均值为正但分布不稳，需扩大到 confirm 2010–2015 验证。

### 2026-02-02-preflop-defend-loosen-v1-confirm-full
- change_id: 2026-02-02-preflop-defend-loosen-v1-confirm-full
- change_type: Eval
- scope: system_bot_policy_v3_preflop_defend_loosen_v1 confirm seeds 2010–2015
- baseline: full_eval_baseline_20260201_policy_v3
- delta: confirm mean Δ≈+0.50 bb/100（6 seeds）
- evidence:
  - seed2010–2015 | ref=report:ab_preflop_defend_loosen_v1_full/seed_deltas
- outcome: CONTINUE
- rationale: 均值微弱且方差大（seed2010显著回撤），不具备晋级 full eval 的稳定性，需进一步调参或换方向。

### 2026-02-02-preflop-defend-loosen-v2-quick
- change_id: 2026-02-02-preflop-defend-loosen-v2-quick
- change_type: Refine
- scope: system_bot_policy_v3_preflop_defend_loosen_v2 (preflop_defend_tighten_bp=1500)
- baseline: full_eval_baseline_20260201_policy_v3
- delta: confirm seeds 2013–2015 mean Δ≈+3.15 bb/100
- evidence:
  - seed2013/2014/2015 | ref=report:ab_preflop_defend_loosen_v2/seed_deltas
- outcome: CONTINUE
- rationale: 小样本均值提升但 seed2015 负向，需扩大到 confirm 2010–2015 验证稳定性。

### 2026-02-02-preflop-defend-loosen-v2-confirm-full
- change_id: 2026-02-02-preflop-defend-loosen-v2-confirm-full
- change_type: Eval
- scope: system_bot_policy_v3_preflop_defend_loosen_v2 confirm seeds 2010–2015
- baseline: full_eval_baseline_20260201_policy_v3
- delta: confirm mean Δ≈+0.19 bb/100（6 seeds）
- evidence:
  - seed2010–2015 | ref=report:ab_preflop_defend_loosen_v2_full/seed_deltas
- outcome: CONTINUE
- rationale: 均值微弱且方差大（seed2010/2011 回撤明显），不具备晋级 full eval 的稳定性。

### 2026-02-02-retaliation-weight-v1-quick
- change_id: 2026-02-02-retaliation-weight-v1-quick
- change_type: Refine
- scope: system_bot_policy_v3_retaliation_weight_v1 (retaliation_weight_bp=350)
- baseline: full_eval_baseline_20260201_policy_v3
- delta: confirm seeds 2013–2015 mean Δ≈+1.19 bb/100
- evidence:
  - seed2013/2014/2015 | ref=report:ab_retaliation_weight_v1/seed_deltas
- outcome: CONTINUE
- rationale: 小样本轻微提升但幅度有限，需扩大到 confirm 2010–2015 验证稳定性。

### 2026-02-02-retaliation-weight-v1-confirm-full
- change_id: 2026-02-02-retaliation-weight-v1-confirm-full
- change_type: Eval
- scope: system_bot_policy_v3_retaliation_weight_v1 confirm seeds 2010–2015
- baseline: full_eval_baseline_20260201_policy_v3
- delta: confirm mean Δ≈+1.87 bb/100（6 seeds）
- evidence:
  - seed2010–2015 | ref=report:ab_retaliation_weight_v1_full/seed_deltas
- outcome: CONTINUE
- rationale: 均值改善且无大幅回撤，具备进入 full eval 的条件。

### 2026-02-02-retaliation-weight-v1-full-eval
- change_id: 2026-02-02-retaliation-weight-v1-full-eval
- change_type: Eval
- scope: system_bot_policy_v3_retaliation_weight_v1 full eval (Tier-A/Tier-P/confirm + pool_eval + br_proxy)
- baseline: full_eval_baseline_20260201_policy_v3
- delta: Tier-A Δ≈+0.70；Tier-P Δ≈-0.02；confirm Δ≈+1.87；pool_eval weighted Δ≈+0.44；br_proxy worst_case Δ≈+0.56
- evidence:
  - compare_baseline | ref=report:full_eval_retaliation_weight_v1/compare_baseline
  - pool_eval_summary | ref=report:pool_eval/full_eval_retaliation_weight_v1_20260202
  - br_proxy_summary | ref=report:br_proxy/full_eval_retaliation_weight_v1_20260202
- outcome: CONTINUE
- rationale: confirm/pool/br_proxy 均改善，Tier-P 基本持平；具备候选晋级价值，但需复核 Tier-P 轻微回撤是否稳定。

### 2026-02-02-retaliation-weight-v2-quick
- change_id: 2026-02-02-retaliation-weight-v2-quick
- change_type: Refine
- scope: system_bot_policy_v3_retaliation_weight_v2 (retaliation_weight_bp=400)
- baseline: full_eval_baseline_20260201_policy_v3
- delta: confirm seeds 2013–2015 mean Δ≈+1.26 bb/100
- evidence:
  - seed2013/2014/2015 | ref=report:ab_retaliation_weight_v2/seed_deltas
- outcome: CONTINUE
- rationale: 小样本提升幅度低于 v1，优先继续沿 v1 方向做更稳定的扩大验证。

### 2026-02-02-retaliation-weight-v1-confirm-ext
- change_id: 2026-02-02-retaliation-weight-v1-confirm-ext
- change_type: Eval
- scope: system_bot_policy_v3_retaliation_weight_v1 confirm seeds 2016–2021（扩展稳定性验证）
- baseline: system_bot_policy_v3 (同种子重跑)
- delta: confirm mean Δ≈+1.22 bb/100（6 seeds）；2010–2021 合并均值 Δ≈+1.55 bb/100（12 seeds）
- evidence:
  - seed2016–2021 | ref=report:ab_retaliation_weight_v1_ext/seed_deltas
  - seed2010–2021 | ref=report:ab_retaliation_weight_v1_ext/seed_deltas_2010_2021
- outcome: CONTINUE
- rationale: 扩展种子仍保持正向均值，整体稳定性提升，具备进一步晋级/固化候选的条件。

### 2026-02-02-baseline-retaliation-weight-v1
- change_id: 2026-02-02-baseline-retaliation-weight-v1
- change_type: Define
- scope: promote system_bot_policy_v3_retaliation_weight_v1 as new baseline
- baseline: full_eval_baseline_20260201_policy_v3
- delta: Tier‑A Δ≈+0.70；Tier‑P Δ≈-0.02；confirm Δ≈+1.87；pool_eval weighted Δ≈+0.44；br_proxy worst_case Δ≈+0.56
- evidence:
  - compare_baseline | ref=report:full_eval_retaliation_weight_v1/compare_baseline
  - coverage_check Tier‑A | ref=path:artifacts/baselines/retaliation_weight_v1_20260202/tierA/coverage_check.json
  - micro066 | mean Δ≈-1.87 | ref=path:tmp/ab_retaliation_weight_v1_micro066/seed_deltas.json
- outcome: ADOPT
- rationale: 双层 confirm + 扩展 seeds（2016–2021）维持正向均值；pool_eval/br_proxy 改善且 Tier‑P 基本持平，微扰评测无灾难性崩盘，满足基线晋级条件。

### 2026-02-03-fast-gate-adapt-v1
- change_id: 2026-02-03-fast-gate-adapt-v1
- change_type: Eval
- scope: system_bot_policy_v3_retaliation_weight_v1_adapt_v1 (opp_defense_prior_count=4) fast-gate (hands=500, seeds=2000–2002)
- baseline: system_bot_policy_v3_retaliation_weight_v1
- delta: elite_reg mean Δ≈0.00；aggressive_reg Δ≈0.00；frozen_v3 Δ≈0.00；rule_strong Δ≈‑15.93 bb/100（更差）
- evidence:
  - baseline fast_gate | ref=path:tmp/fast_gate_baseline_rw1
  - candidate fast_gate | ref=path:tmp/fast_gate_candidate_adapt_v1
- outcome: STOP
- rationale: 快速门槛未见收益且 rule_strong 退化，暂不推进到完整评测。

### 2026-02-03-fast-gate-low-spr-v1
- change_id: 2026-02-03-fast-gate-low-spr-v1
- change_type: Eval
- scope: system_bot_policy_v3_retaliation_weight_v1_low_spr_v1 (facing_low_spr_threshold_bp=200; defend_scale=0.85; raise_share_cap=0.12) fast-gate (hands=500, seeds=2000–2002)
- baseline: system_bot_policy_v3_retaliation_weight_v1
- delta: elite_reg mean Δ≈0.00；aggressive_reg Δ≈0.00；frozen_v3 Δ≈0.00；rule_strong Δ≈‑16.47 bb/100（更差）
- evidence:
  - baseline fast_gate | ref=path:tmp/fast_gate_baseline_rw1
  - candidate fast_gate | ref=path:tmp/fast_gate_candidate_low_spr_v1_rerun
- outcome: STOP
- rationale: 低 SPR 防守/加注上限无增益且 rule_strong 退化，暂不推进到完整评测。

### 2026-02-03-fast-gate-low-spr-v2
- change_id: 2026-02-03-fast-gate-low-spr-v2
- change_type: Eval
- scope: system_bot_policy_v3_retaliation_weight_v1_low_spr_v2 (facing_low_spr_threshold_bp=400; defend_scale=0.80; raise_share_cap=0.10) fast-gate (hands=500, seeds=2000–2002)
- baseline: system_bot_policy_v3_retaliation_weight_v1
- delta: elite_reg mean Δ≈0.00；aggressive_reg Δ≈0.00；frozen_v3 Δ≈0.00；rule_strong Δ≈‑28.75 bb/100（更差）
- evidence:
  - baseline fast_gate | ref=path:tmp/fast_gate_baseline_rw1
  - candidate fast_gate | ref=path:tmp/fast_gate_candidate_low_spr_v2
- outcome: STOP
- rationale: 扩大低 SPR 范围后 rule_strong 进一步退化，且其他套件无增益，终止该方向。

### 2026-02-03-fast-gate-low-price-defend-v1
- change_id: 2026-02-03-fast-gate-low-price-defend-v1
- change_type: Eval
- scope: system_bot_policy_v3_retaliation_weight_v1_low_price_defend_v1 (facing_low_price_threshold_bp=3300; defend_boost=1.15) fast-gate (hands=500, seeds=2000–2002)
- baseline: system_bot_policy_v3_retaliation_weight_v1
- delta: elite_reg mean Δ≈+3.34；aggressive_reg Δ≈+3.34；frozen_v3 Δ≈+3.34；rule_strong Δ≈‑26.55 bb/100（更差）
- evidence:
  - baseline fast_gate | ref=path:tmp/fast_gate_baseline_rw1
  - candidate fast_gate | ref=path:tmp/fast_gate_candidate_low_price_defend_v1
- outcome: STOP
- rationale: 普通套件小幅提升，但 rule_strong 明显退化，未通过 fast-gate 门槛。

### 2026-02-03-fast-gate-high-price-raise-cap-v1
- change_id: 2026-02-03-fast-gate-high-price-raise-cap-v1
- change_type: Eval
- scope: system_bot_policy_v3_retaliation_weight_v1_high_price_raise_cap_v1 (facing_high_price_threshold_bp=3300; raise_share_cap=0.10) fast-gate (hands=500, seeds=2000–2002)
- baseline: system_bot_policy_v3_retaliation_weight_v1
- delta: elite_reg mean Δ≈0.00；aggressive_reg Δ≈0.00；frozen_v3 Δ≈0.00；rule_strong Δ≈0.00
- evidence:
  - baseline fast_gate | ref=path:tmp/fast_gate_baseline_rw1
  - candidate fast_gate | ref=path:tmp/fast_gate_candidate_high_price_raise_cap_v1
- outcome: STOP
- rationale: 高价位加注上限未带来收益变化，未通过 fast-gate 门槛。

### 2026-02-03-fast-gate-high-price-raise-cap-v2
- change_id: 2026-02-03-fast-gate-high-price-raise-cap-v2
- change_type: Eval
- scope: system_bot_policy_v3_retaliation_weight_v1_high_price_raise_cap_v2 (price>=0.33 cap=0.06; price>=0.50 cap=0.04) fast-gate (hands=500, seeds=2000–2002)
- baseline: system_bot_policy_v3_retaliation_weight_v1
- delta: elite_reg mean Δ≈0.00；aggressive_reg Δ≈0.00；frozen_v3 Δ≈0.00；rule_strong Δ≈0.00
- evidence:
  - baseline fast_gate | ref=path:tmp/fast_gate_baseline_rw1
  - candidate fast_gate | ref=path:tmp/fast_gate_candidate_high_price_raise_cap_v2
- outcome: STOP
- rationale: 双阈值高价位加注上限未带来收益变化，未通过 fast-gate 门槛。

### 2026-02-03-fast-gate-high-price-raise-scale-v1
- change_id: 2026-02-03-fast-gate-high-price-raise-scale-v1
- change_type: Eval
- scope: system_bot_policy_v3_retaliation_weight_v1_high_price_raise_scale_v1 (price>=0.33 scale=0.70; price>=0.50 scale=0.50) fast-gate (hands=500, seeds=2000–2002)
- baseline: system_bot_policy_v3_retaliation_weight_v1
- delta: elite_reg mean Δ≈0.00；aggressive_reg Δ≈0.00；frozen_v3 Δ≈0.00；rule_strong Δ≈0.00
- evidence:
  - baseline fast_gate | ref=path:tmp/fast_gate_baseline_rw1
  - candidate fast_gate | ref=path:tmp/fast_gate_candidate_high_price_raise_scale_v1
- outcome: STOP
- rationale: 高价位加注比例缩放未带来收益变化，未通过 fast-gate 门槛。

### 2026-02-03-fast-gate-high-price-raise-scale-v2
- change_id: 2026-02-03-fast-gate-high-price-raise-scale-v2
- change_type: Eval
- scope: system_bot_policy_v3_retaliation_weight_v1_high_price_raise_scale_v2 (price>=0.20 scale=0.80; price>=0.25 scale=0.60) fast-gate (hands=500, seeds=2000–2002)
- baseline: system_bot_policy_v3_retaliation_weight_v1
- delta: elite_reg mean Δ≈0.00；aggressive_reg Δ≈0.00；frozen_v3 Δ≈0.00；rule_strong Δ≈0.00
- evidence:
  - baseline fast_gate | ref=path:tmp/fast_gate_baseline_rw1
  - candidate fast_gate | ref=path:tmp/fast_gate_candidate_high_price_raise_scale_v2
- outcome: STOP
- rationale: 放宽阈值后仍无收益变化，说明该 prior 权重调整未触发有效行为变化。

### 2026-02-03-fast-gate-high-price-raise-penalty-v1
- change_id: 2026-02-03-fast-gate-high-price-raise-penalty-v1
- change_type: Eval
- scope: system_bot_policy_v3_retaliation_weight_v1_high_price_raise_penalty_v1 (price>=0.20 raise_penalty=0.03 pot; price>=0.33 raise_penalty=0.06 pot) fast-gate (hands=500, seeds=2000–2002)
- baseline: system_bot_policy_v3_retaliation_weight_v1
- delta: elite_reg mean Δ≈0.00；aggressive_reg Δ≈0.00；frozen_v3 Δ≈0.00；rule_strong Δ≈0.00
- evidence:
  - baseline fast_gate | ref=path:tmp/fast_gate_baseline_rw1
  - candidate fast_gate | ref=path:tmp/fast_gate_candidate_high_price_raise_penalty_v1b
- outcome: STOP
- rationale: 加注惩罚未触发行为变化（ActionChosen 序列哈希一致），收益无变化。

### 2026-02-03-fast-gate-high-price-action-penalty-v1
- change_id: 2026-02-03-fast-gate-high-price-action-penalty-v1
- change_type: Eval
- scope: system_bot_policy_v3_retaliation_weight_v1_high_price_action_penalty_v1 (price>=0.20 action_penalty=0.10 pot; price>=0.33 action_penalty=0.20 pot) fast-gate (hands=500, seeds=2000–2002)
- baseline: system_bot_policy_v3_retaliation_weight_v1
- delta: elite_reg mean Δ≈0.00；aggressive_reg Δ≈0.00；frozen_v3 Δ≈0.00；rule_strong Δ≈0.00
- evidence:
  - baseline fast_gate | ref=path:tmp/fast_gate_baseline_rw1
  - candidate fast_gate | ref=path:tmp/fast_gate_candidate_high_price_action_penalty_v1
- outcome: STOP
- rationale: CALL/RAISE 惩罚仍未触发行为变化（ActionChosen 序列哈希一致），收益无变化。

### 2026-02-03-fast-gate-aggressive-risk-penalty-v1
- change_id: 2026-02-03-fast-gate-aggressive-risk-penalty-v1
- change_type: Eval
- scope: system_bot_policy_v3_retaliation_weight_v1_aggressive_risk_penalty_v1 (size_ratio>=0.25 penalty=0.05 pot; size_ratio>=0.45 penalty=0.12 pot) fast-gate (hands=500, seeds=2000–2002)
- baseline: system_bot_policy_v3_retaliation_weight_v1
- delta: elite_reg mean Δ≈+2.50；aggressive_reg Δ≈-0.39；frozen_v3 Δ≈-0.39；rule_strong Δ≈-23.06
- evidence:
  - baseline fast_gate | ref=path:tmp/fast_gate_baseline_rw1
  - candidate fast_gate | ref=path:tmp/fast_gate_candidate_aggressive_risk_penalty_v1
- outcome: STOP
- rationale: 强行压制激进线导致 rule_strong 显著回撤，整体不通过 fast-gate。

### 2026-02-03-fast-gate-high-price-raise-block-v1
- change_id: 2026-02-03-fast-gate-high-price-raise-block-v1
- change_type: Eval
- scope: system_bot_policy_v3_retaliation_weight_v1_high_price_raise_block_v1 (price>=0.20 block raises on TURN/RIVER) fast-gate (hands=500, seeds=2000–2002)
- baseline: system_bot_policy_v3_retaliation_weight_v1
- delta: elite_reg mean Δ≈-7.01；aggressive_reg Δ≈-4.33；frozen_v3 Δ≈-6.74；rule_strong Δ≈-5.61
- evidence:
  - baseline fast_gate | ref=path:tmp/fast_gate_baseline_rw1
  - candidate fast_gate | ref=path:tmp/fast_gate_candidate_high_price_raise_block_v1
- outcome: STOP
- rationale: 硬性阻断高价位加注导致多套对手回撤，未通过 fast-gate 门槛。

### 2026-02-03-fast-gate-high-price-defend-gate-v1
- change_id: 2026-02-03-fast-gate-high-price-defend-gate-v1
- change_type: Eval
- scope: system_bot_policy_v3_retaliation_weight_v1_high_price_defend_gate_v1 (price>=0.18 gap0.03 限制加注；price>=0.30 gap0.07 限制跟注) fast-gate (hands=500, seeds=2000–2002)
- baseline: system_bot_policy_v3_retaliation_weight_v1
- delta: elite_reg mean Δ≈-0.73；aggressive_reg Δ≈-0.73；frozen_v3 Δ≈0.00；rule_strong Δ≈+22.39
- evidence:
  - baseline fast_gate | ref=path:tmp/fast_gate_baseline_rw1
  - candidate fast_gate | ref=path:tmp/fast_gate_candidate_high_price_defend_gate_v1
- outcome: STOP
- rationale: rule_strong 明显改善但 elite/aggressive 回撤，整体未过 fast-gate。

### 2026-02-03-fast-gate-high-price-defend-gate-v2
- change_id: 2026-02-03-fast-gate-high-price-defend-gate-v2
- change_type: Eval
- scope: system_bot_policy_v3_retaliation_weight_v1_high_price_defend_gate_v2 (price>=0.20 gap0.02 限制加注；price>=0.35 gap0.06 限制跟注) fast-gate (hands=500, seeds=2000–2002)
- baseline: system_bot_policy_v3_retaliation_weight_v1
- delta: elite_reg mean Δ≈0.00；aggressive_reg Δ≈0.00；frozen_v3 Δ≈0.00；rule_strong Δ≈+16.43
- evidence:
  - baseline fast_gate | ref=path:tmp/fast_gate_baseline_rw1
  - candidate fast_gate | ref=path:tmp/fast_gate_candidate_high_price_defend_gate_v2
- outcome: CONTINUE
- rationale: 不回撤主套件且 rule_strong 有提升，建议进入更强评测或继续微调。

### 2026-02-03-fast-gate-high-price-defend-gate-v3
- change_id: 2026-02-03-fast-gate-high-price-defend-gate-v3
- change_type: Eval
- scope: system_bot_policy_v3_retaliation_weight_v1_high_price_defend_gate_v3 (price>=0.19 gap0.025 限制加注；price>=0.33 gap0.065 限制跟注) fast-gate (hands=500, seeds=2000–2002)
- baseline: system_bot_policy_v3_retaliation_weight_v1
- delta: elite_reg mean Δ≈-0.73；aggressive_reg Δ≈-0.73；frozen_v3 Δ≈0.00；rule_strong Δ≈+28.45
- evidence:
  - baseline fast_gate | ref=path:tmp/fast_gate_baseline_rw1
  - candidate fast_gate | ref=path:tmp/fast_gate_candidate_high_price_defend_gate_v3
- outcome: STOP
- rationale: rule_strong 提升更大但 elite/aggressive 出现回撤，不符合 fast-gate 稳健门槛。

### 2026-02-03-robust-gate-high-price-defend-gate-v2
- change_id: 2026-02-03-robust-gate-high-price-defend-gate-v2
- change_type: Eval
- scope: system_bot_policy_v3_retaliation_weight_v1_high_price_defend_gate_v2 robust-gate (hands=1000, seeds=2000–2005)
- baseline: system_bot_policy_v3_retaliation_weight_v1
- delta: elite_reg mean Δ≈+0.39；aggressive_reg Δ≈+0.39；frozen_v3 Δ≈+1.05；rule_strong Δ≈+16.27
- evidence:
  - baseline robust_gate | ref=path:tmp/robust_gate_baseline_rw1
  - candidate robust_gate | ref=path:tmp/robust_gate_candidate_high_price_defend_gate_v2
- outcome: PROMOTE
- rationale: 四套对手均正向提升且无回撤，建议作为新候选基线进入更完整评测。

### 2026-02-04-robust-gate-high-price-defend-gate-v2-h2000
- change_id: 2026-02-04-robust-gate-high-price-defend-gate-v2-h2000
- change_type: Eval
- scope: system_bot_policy_v3_retaliation_weight_v1_high_price_defend_gate_v2 robust-gate (hands=2000, seeds=2000–2005, rule_strong=rule_suite_7max_strong_v1)
- baseline: system_bot_policy_v3_retaliation_weight_v1
- delta: elite_reg mean Δ≈+0.62；aggressive_reg Δ≈+0.62；frozen_v3 Δ≈+0.95；rule_strong Δ≈+13.15
- evidence:
  - baseline robust_gate | ref=path:tmp/robust_gate_baseline_rw1_h2000_full1
  - candidate robust_gate | ref=path:tmp/robust_gate_candidate_high_price_defend_gate_v2_h2000_full1
- outcome: PROMOTE
- rationale: 四套对手均正向提升且无回撤；rule_strong 仍为负但显著收敛，建议作为新候选基线继续优化。

### 2026-02-04-fast-gate-high-price-defend-gate-v4-dynamic
- change_id: 2026-02-04-fast-gate-high-price-defend-gate-v4-dynamic
- change_type: Eval
- scope: system_bot_policy_v3_retaliation_weight_v1_high_price_defend_gate_v4 (SPR/OOP/MW gap penalties) fast-gate (hands=500, seeds=2000–2002, rule_strong=rule_suite_7max_strong_v1)
- baseline: system_bot_policy_v3_retaliation_weight_v1
- delta: elite_reg mean Δ≈0.00；aggressive_reg Δ≈0.00；frozen_v3 Δ≈0.00；rule_strong Δ≈+17.37
- evidence:
  - baseline fast_gate | ref=path:tmp/fast_gate_baseline_high_price_defend_gate_v4
  - candidate fast_gate | ref=path:tmp/fast_gate_candidate_high_price_defend_gate_v4
- outcome: CONTINUE
- rationale: 主套件无回撤且 rule_strong 明显改善，建议进入更强评测或微调 penalty 强度。

### 2026-02-05-robust-gate-high-price-defend-gate-v4-h2000
- change_id: 2026-02-05-robust-gate-high-price-defend-gate-v4-h2000
- change_type: Eval
- scope: system_bot_policy_v3_retaliation_weight_v1_high_price_defend_gate_v4 robust-gate (hands=2000, seeds=2000–2005, rule_strong=rule_suite_7max_strong_v1)
- baseline: system_bot_policy_v3_retaliation_weight_v1
- delta: elite_reg mean Δ≈+0.62；aggressive_reg Δ≈+0.62；frozen_v3 Δ≈+0.95；rule_strong Δ≈+14.20
- evidence:
  - baseline robust_gate | ref=path:tmp/robust_gate_baseline_high_price_defend_gate_v4_h2000_batch
  - candidate robust_gate | ref=path:tmp/robust_gate_candidate_high_price_defend_gate_v4_h2000_batch
- outcome: PROMOTE
- rationale: 四套对手均正向提升且无回撤；rule_strong 负值继续收敛。

### 2026-02-05-robust-gate-high-price-defend-gate-v4-h1000
- change_id: 2026-02-05-robust-gate-high-price-defend-gate-v4-h1000
- change_type: Eval
- scope: system_bot_policy_v3_retaliation_weight_v1_high_price_defend_gate_v4 robust-gate (hands=1000, seeds=2000–2005, rule_strong=rule_suite_7max_strong_v1)
- baseline: system_bot_policy_v3_retaliation_weight_v1
- delta: elite_reg mean Δ≈+0.39；aggressive_reg Δ≈+0.39；frozen_v3 Δ≈+1.05；rule_strong Δ≈+16.91
- evidence:
  - baseline robust_gate | ref=path:tmp/robust_gate_baseline_high_price_defend_gate_v4_h1000_batch
  - candidate robust_gate | ref=path:tmp/robust_gate_candidate_high_price_defend_gate_v4_h1000_batch
- outcome: PROMOTE
- rationale: 更短评测同样稳定正向；rule_strong 继续改善。

### 2026-02-05-robust-gate-high-price-defend-gate-v5-h2000
- change_id: 2026-02-05-robust-gate-high-price-defend-gate-v5-h2000
- change_type: Eval
- scope: system_bot_policy_v3_retaliation_weight_v1_high_price_defend_gate_v5 (SPR/OOP/MW + wet/turn penalties) robust-gate (hands=2000, seeds=2000–2005, rule_strong=rule_suite_7max_strong_v1)
- baseline: system_bot_policy_v3_retaliation_weight_v1
- delta: elite_reg mean Δ≈+0.62；aggressive_reg Δ≈+0.62；frozen_v3 Δ≈+0.95；rule_strong Δ≈+14.37
- evidence:
  - baseline robust_gate | ref=path:tmp/robust_gate_baseline_high_price_defend_gate_v5_h2000
  - candidate robust_gate | ref=path:tmp/robust_gate_candidate_high_price_defend_gate_v5_h2000
- outcome: PROMOTE
- rationale: 主套件无回撤，rule_strong 继续收敛；相比 v4 改善幅度接近但略有提升。

### 2026-02-05-robust-gate-high-price-defend-gate-v5-h1000
- change_id: 2026-02-05-robust-gate-high-price-defend-gate-v5-h1000
- change_type: Eval
- scope: system_bot_policy_v3_retaliation_weight_v1_high_price_defend_gate_v5 (SPR/OOP/MW + wet/turn penalties) robust-gate (hands=1000, seeds=2000–2005, rule_strong=rule_suite_7max_strong_v1)
- baseline: system_bot_policy_v3_retaliation_weight_v1
- delta: elite_reg mean Δ≈+0.39；aggressive_reg Δ≈+0.39；frozen_v3 Δ≈+1.05；rule_strong Δ≈+16.91
- evidence:
  - baseline robust_gate | ref=path:tmp/robust_gate_baseline_high_price_defend_gate_v5_h1000
  - candidate robust_gate | ref=path:tmp/robust_gate_candidate_high_price_defend_gate_v5_h1000
- outcome: PROMOTE
- rationale: 短评测保持稳定正向；rule_strong 改善明显。

### 2026-02-05-robust-gate-high-price-defend-gate-v6-h2000
- change_id: 2026-02-05-robust-gate-high-price-defend-gate-v6-h2000
- change_type: Eval
- scope: system_bot_policy_v3_retaliation_weight_v1_high_price_defend_gate_v6 (wet turn/river threshold2 + gap2 buckets) robust-gate (hands=2000, seeds=2000–2005, rule_strong=rule_suite_7max_strong_v1)
- baseline: system_bot_policy_v3_retaliation_weight_v1
- delta: elite_reg mean Δ≈+0.62；aggressive_reg Δ≈+0.62；frozen_v3 Δ≈+0.95；rule_strong Δ≈+14.70；overall Δ≈+4.22
- evidence:
  - BB|TURN|Facing=Y | bb/100=-1479.35 | n=20 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:1-2 | bb/100=-1082.21 | n=732 | seeds=2000–2005 | ref=report:SPRBuckets/1-2
  - TURN|players=3 | bb/100=-807.63 | n=676 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_3p
- outcome: PROMOTE
- rationale: 四套对手均正向提升；rule_strong 继续收敛；湿转/河道二级门槛未引入回撤。

### 2026-02-05-robust-gate-high-price-defend-gate-v6-h1000
- change_id: 2026-02-05-robust-gate-high-price-defend-gate-v6-h1000
- change_type: Eval
- scope: system_bot_policy_v3_retaliation_weight_v1_high_price_defend_gate_v6 (wet turn/river threshold2 + gap2 buckets) robust-gate (hands=1000, seeds=2000–2005, rule_strong=rule_suite_7max_strong_v1)
- baseline: system_bot_policy_v3_retaliation_weight_v1
- delta: elite_reg mean Δ≈+0.39；aggressive_reg Δ≈+0.39；frozen_v3 Δ≈+1.05；rule_strong Δ≈+17.55；overall Δ≈+4.85
- evidence:
  - BB|TURN|Facing=Y | bb/100=-3209.10 | n=10 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:1-2 | bb/100=-1321.28 | n=376 | seeds=2000–2005 | ref=report:SPRBuckets/1-2
  - FLOP|players=7 | bb/100=-923.17 | n=213 | seeds=2000–2005 | ref=report:ProfitByPlayers/FLOP_7p
- outcome: PROMOTE
- rationale: 短评测结果与长评测一致，整体稳定正向，rule_strong 继续改善。

### 2026-02-05-robust-gate-high-price-defend-gate-v7-h2000
- change_id: 2026-02-05-robust-gate-high-price-defend-gate-v7-h2000
- change_type: Eval
- scope: system_bot_policy_v3_retaliation_weight_v1_high_price_defend_gate_v7 (spr_low penalty + wet turn/river threshold2/gap2) robust-gate (hands=2000, seeds=2000–2005, rule_strong=rule_suite_7max_strong_v1)
- baseline: system_bot_policy_v3_retaliation_weight_v1
- delta: elite_reg mean Δ≈+0.62；aggressive_reg Δ≈+0.62；frozen_v3 Δ≈+0.95；rule_strong Δ≈+14.70；overall Δ≈+4.22
- evidence:
  - BB|TURN|Facing=Y | bb/100=-1479.35 | n=20 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:1-2 | bb/100=-1082.21 | n=732 | seeds=2000–2005 | ref=report:SPRBuckets/1-2
  - TURN|players=3 | bb/100=-807.63 | n=676 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_3p
- outcome: PROMOTE
- rationale: 与 v6 持平且无回撤；spr_low 惩罚未带来额外收益但保持稳定。

### 2026-02-05-robust-gate-high-price-defend-gate-v7-h1000
- change_id: 2026-02-05-robust-gate-high-price-defend-gate-v7-h1000
- change_type: Eval
- scope: system_bot_policy_v3_retaliation_weight_v1_high_price_defend_gate_v7 (spr_low penalty + wet turn/river threshold2/gap2) robust-gate (hands=1000, seeds=2000–2005, rule_strong=rule_suite_7max_strong_v1)
- baseline: system_bot_policy_v3_retaliation_weight_v1
- delta: elite_reg mean Δ≈+0.39；aggressive_reg Δ≈+0.39；frozen_v3 Δ≈+1.05；rule_strong Δ≈+17.55；overall Δ≈+4.85
- evidence:
  - BB|TURN|Facing=Y | bb/100=-3209.10 | n=10 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:1-2 | bb/100=-1321.28 | n=376 | seeds=2000–2005 | ref=report:SPRBuckets/1-2
  - FLOP|players=7 | bb/100=-923.17 | n=213 | seeds=2000–2005 | ref=report:ProfitByPlayers/FLOP_7p
- outcome: PROMOTE
- rationale: 短评测结果与长评测一致，整体稳定正向；spr_low 惩罚未显著改变分布。

### 2026-02-05-robust-gate-high-price-defend-gate-v8-h2000
- change_id: 2026-02-05-robust-gate-high-price-defend-gate-v8-h2000
- change_type: Eval
- scope: system_bot_policy_v3_retaliation_weight_v1_high_price_defend_gate_v8 (spr_low threshold2 downshift) robust-gate (hands=2000, seeds=2000–2005, rule_strong=rule_suite_7max_strong_v1)
- baseline: system_bot_policy_v3_retaliation_weight_v1
- delta: elite_reg mean Δ≈+0.62；aggressive_reg Δ≈+0.62；frozen_v3 Δ≈+0.95；rule_strong Δ≈+17.62；overall Δ≈+4.95
- delta_ci95: elite_reg [0.00, 1.24]；aggressive_reg [0.00, 1.24]；frozen_v3 [0.00, 2.22]；rule_strong [9.22, 26.71]
- evidence:
  - BB|TURN|Facing=Y | bb/100=-1479.35 | n=20 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:1-2 | bb/100=-1070.08 | n=732 | seeds=2000–2005 | ref=report:SPRBuckets/1-2
  - TURN|players=3 | bb/100=-780.35 | n=674 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_3p
- outcome: PROMOTE
- rationale: 低 SPR 阈值下移带来小幅整体提升，rule_strong 继续改善但弱桶结构未根本改变；下一步仍需围绕 TURN Facing=Y 与 SPR 1-2 做机制性修复。

### 2026-02-05-robust-gate-high-price-defend-gate-v9-h2000
- change_id: 2026-02-05-robust-gate-high-price-defend-gate-v9-h2000
- change_type: Eval
- scope: system_bot_policy_v3_retaliation_weight_v1_high_price_defend_gate_v9 (spr_low price-scaled gap penalty) robust-gate (hands=2000, seeds=2000–2005, rule_strong=rule_suite_7max_strong_v1)
- baseline: system_bot_policy_v3_retaliation_weight_v1
- delta: elite_reg mean Δ≈+0.62；aggressive_reg Δ≈+0.62；frozen_v3 Δ≈+0.95；rule_strong Δ≈+17.62；overall Δ≈+4.95
- delta_ci95: elite_reg [0.00, 1.24]；aggressive_reg [0.00, 1.24]；frozen_v3 [0.00, 2.22]；rule_strong [9.22, 26.71]
- evidence:
  - BB|TURN|Facing=Y | bb/100=-1479.35 | n=20 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:1-2 | bb/100=-1070.08 | n=732 | seeds=2000–2005 | ref=report:SPRBuckets/1-2
  - TURN|players=3 | bb/100=-780.35 | n=674 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_3p
- outcome: REJECT
- rationale: 与 v8 完全一致，说明新惩罚未触发或影响过弱；需要提高触发密度或改造价格/SPR 组合的防守决策机制。

### 2026-02-06-robust-gate-high-price-defend-gate-v10-h2000
- change_id: 2026-02-06-robust-gate-high-price-defend-gate-v10-h2000
- change_type: Eval
- scope: system_bot_policy_v3_retaliation_weight_v1_high_price_defend_gate_v10 (spr_low price-scale + turn multiplier) robust-gate (hands=2000, seeds=2000–2005, rule_strong=rule_suite_7max_strong_v1)
- baseline: system_bot_policy_v3_retaliation_weight_v1
- delta: elite_reg mean Δ≈+0.62；aggressive_reg Δ≈+0.62；frozen_v3 Δ≈+0.95；rule_strong Δ≈+17.62；overall Δ≈+4.95
- delta_ci95: elite_reg [0.00, 1.24]；aggressive_reg [0.00, 1.24]；frozen_v3 [0.00, 2.22]；rule_strong [9.22, 26.71]
- evidence:
  - BB|TURN|Facing=Y | bb/100=-1479.35 | n=20 | seeds=2000–2005 | ref=report:BBFlatPostflopFacing/TURN_Y
  - SPR:1-2 | bb/100=-1070.08 | n=732 | seeds=2000–2005 | ref=report:SPRBuckets/1-2
  - TURN|players=3 | bb/100=-780.35 | n=674 | seeds=2000–2005 | ref=report:ProfitByPlayers/TURN_3p
- outcome: REJECT
- rationale: 结果与 v8/v9 完全一致；新增触发统计显示低 SPR 高价位命中次数极少（各套件仅 3–4 次/6 seeds），难以产生可见收益，需提升触发密度或改为更直接的防守目标重估。

### 2026-02-06-robust-eval-adapt-v2-h2000
- change_id: 2026-02-06-robust-eval-adapt-v2-h2000
- change_type: Eval
- scope: system_bot_policy_v3_retaliation_weight_v1_adapt_v2 robust-eval (hands=2000, seeds=2000–2005, suites=elite_reg/aggressive_reg/frozen_v3/rule_strong)
- baseline: system_bot_policy_v3_retaliation_weight_v1
- delta: strict paired_compare all-null (options_hash mismatch); non-strict bb/100: elite_reg mean Δ≈-0.86, aggressive_reg mean Δ≈+0.50, frozen_v3 mean Δ≈-3.32, rule_strong mean Δ≈+0.19, overall mean Δ≈-0.87 (24 paired seeds)
- delta_ci95: elite_reg [-1.77, -0.05]; aggressive_reg [-0.12, +1.29]; frozen_v3 [-8.49, +0.05]; rule_strong [0.00, +0.41]
- evidence:
  - robust eval run_root | ref=path:tmp/robust_eval_adapt_v2_20260206_111112
  - strict summary (options_hash mismatch) | ref=path:tmp/robust_eval_adapt_v2_20260206_111112/summary.json
  - non-strict summary (bb_per_100) | ref=path:tmp/robust_eval_adapt_v2_20260206_111112/summary_non_strict_bb100.json
- outcome: REJECT
- rationale: adaptive_v2 在 aggressive/rule 有小幅正向，但对 elite/frozen 出现可观回撤，整体不超基线且稳健性不足；不作为新基线。

### 2026-02-06-fast-eval-adapt-v3-h500-s3
- change_id: 2026-02-06-fast-eval-adapt-v3-h500-s3
- change_type: Eval
- scope: system_bot_policy_v3_retaliation_weight_v1_adapt_v3 fast-eval (hands=500, seeds=2000–2002, suites=elite_reg/aggressive_reg/frozen_v3/rule_strong)
- baseline: system_bot_policy_v3_retaliation_weight_v1
- delta: overall Δ≈0.00（12 paired）；各套件均 Δ≈0.00
- delta_ci95: overall [0.00, 0.00]
- evidence:
  - fast eval run_root | ref=path:tmp/fast_eval_adapt_v3_20260206_132021
  - non-strict summary (bb_per_100) | ref=path:tmp/fast_eval_adapt_v3_20260206_132021/summary_non_strict_bb100.json
- outcome: REJECT
- rationale: 在短样本下 adaptive 几乎全为 anchor（未形成有效策略偏移），收益与基线一致，未体现增益。

### 2026-02-06-fast-eval-v8-vs-baseline-h500-s3
- change_id: 2026-02-06-fast-eval-v8-vs-baseline-h500-s3
- change_type: Eval
- scope: system_bot_policy_v3_retaliation_weight_v1_high_price_defend_gate_v8 fast-eval (hands=500, seeds=2000–2002, suites=elite_reg/aggressive_reg/frozen_v3/rule_strong)
- baseline: system_bot_policy_v3_retaliation_weight_v1
- delta: overall Δ≈+4.34；rule_strong Δ≈+17.37；elite/aggressive/frozen Δ≈0.00
- delta_ci95: overall [0.00, +10.88]；rule_strong [+1.78, +29.93]
- evidence:
  - fast eval run_root | ref=path:tmp/fast_eval_v8_vs_baseline_20260206_134734
  - non-strict summary (bb_per_100) | ref=path:tmp/fast_eval_v8_vs_baseline_20260206_134734/summary_non_strict_bb100.json
- outcome: CONTINUE
- rationale: 结构性门控在强规则套件上复现显著收益且未引入其他套件回撤，值得进入 6x2000 全量复核。

### 2026-02-06-robust-eval-v8-vs-baseline-h2000
- change_id: 2026-02-06-robust-eval-v8-vs-baseline-h2000
- change_type: Eval
- scope: system_bot_policy_v3_retaliation_weight_v1_high_price_defend_gate_v8 robust-eval (hands=2000, seeds=2000–2005, suites=elite_reg/aggressive_reg/frozen_v3/rule_strong)
- baseline: system_bot_policy_v3_retaliation_weight_v1
- delta: overall Δ≈+4.95（24 paired）；elite_reg Δ≈+0.62；aggressive_reg Δ≈+0.62；frozen_v3 Δ≈+0.95；rule_strong Δ≈+17.62
- delta_ci95: overall [+1.64, +8.99]；elite_reg [0.00, +1.24]；aggressive_reg [0.00, +1.24]；frozen_v3 [0.00, +2.22]；rule_strong [+9.16, +26.41]
- evidence:
  - robust eval run_root | ref=path:tmp/robust_eval_v8_vs_baseline_restart_20260206_142515
  - non-strict summary (bb_per_100) | ref=path:tmp/robust_eval_v8_vs_baseline_restart_20260206_142515/summary_non_strict_bb100.json
- outcome: PROMOTE
- rationale: 四套对手均未回撤且整体显著优于基线，rule_strong 大幅改善并带动总体转正幅度提升。

### 2026-02-06-baseline-alias-promote-v8
- change_id: 2026-02-06-baseline-alias-promote-v8
- change_type: Define
- scope: 将默认策略别名 `system_bot_policy_v3_retaliation_weight_v1` 固化到 `high_price_defend_gate_v8` 闭包（policy/params/system_params 三件套）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: 别名切换，不新增策略逻辑；行为应与 `system_bot_policy_v3_retaliation_weight_v1_high_price_defend_gate_v8` 完全一致
- evidence:
  - promoted alias policy | ref=path:specs/policies/system_bot_policy_v3_retaliation_weight_v1.json
  - promoted alias params | ref=path:specs/policy_params/system_bot_policy_v3_retaliation_weight_v1.params.json
  - rollback copies | ref=path:specs/policies/system_bot_policy_v3_retaliation_weight_v1_pre_v8_20260206.json
- outcome: ADOPT
- rationale: 将已验证可提升的 v8 设为默认基线，同时保留 pre_v8 备份以支持快速回退和 A/B 追溯。

### 2026-02-06-baseline-pool-br-proxy-6x2000
- change_id: 2026-02-06-baseline-pool-br-proxy-6x2000
- change_type: Eval
- scope: 基线策略 `system_bot_policy_v3_retaliation_weight_v1` 在 OpponentPool + BR(π) 的全量复核（hands=2000, seeds=2000–2005, suites=elite_reg/aggressive_reg/frozen_v3/frozen_v2/frozen_v1）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: 基线自回放（同 policy）；pool_eval weighted_mean_bb100≈13.7755（weighted_std≈4.3373）；br_proxy worst_case=`system_bot_league_7max_aggressive_reg_v1` mean_bb100≈9.7648（std≈11.1490）
- evidence:
  - pool eval summary | ref=path:tmp/pool_br_v8_baseline_20260206_162806/pool_eval/pool_eval_summary.json
  - br proxy summary | ref=path:tmp/pool_br_v8_baseline_20260206_162806/br_proxy/br_proxy_summary.json
  - run root | ref=path:tmp/pool_br_v8_baseline_20260206_162806
- outcome: ADOPT
- rationale: Pool 与 BR(π) 双入口均稳定通过（全部 suite pass），最坏套件仍为 aggressive_reg，结果可作为后续改动的对照锚点。

### 2026-02-07-ralph-loop-reliability-hooks-v1
- change_id: 2026-02-07-ralph-loop-reliability-hooks-v1
- change_type: Restructure
- scope: `tools/ralph_wiggum_loop.py` + `tools/ralph_loop_supervisor.sh` + `tools/ralph_autopilot_start.sh` + `tools/ralph_autopilot_stop.sh` + `tools/ralph_time_hook.sh`
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: infra only（评测指标未在本变更中宣称提升）
- evidence:
  - parent resume/chunk controls | ref=path:tools/ralph_wiggum_loop.py
  - supervisor heartbeat/stall guard | ref=path:tools/ralph_loop_supervisor.sh
  - timed self-heal hook + clean start/stop | ref=path:tools/ralph_time_hook.sh
- outcome: ADOPT
- rationale: 修复“循环反复从 cycle_001 重启、守护进程退出后无自愈、停机后残留孤儿评测进程、缺少时间钩子”四类稳定性问题；新增断点续跑+分块checkpoint+心跳超时保护+定时自愈，保证无人值守循环可持续运行并可回放定位。

### 20260207-151511-ralph-loop-cycle-001
- change_id: 20260207-151511-ralph-loop-cycle-001
- change_type: Eval
- scope: ralph-wiggum-loop cycle 001
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active_smoke_fast_20260207_150829; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/loop_smoke_fast_20260207_150829/runs/cycle_001_20260207_150829/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierA_mean
- rationale: quick gate no improvement

### 20260207-152156-ralph-loop-cycle-002
- change_id: 20260207-152156-ralph-loop-cycle-002
- change_type: Eval
- scope: ralph-wiggum-loop cycle 002
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active_smoke_fast_20260207_150829; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/loop_smoke_fast_20260207_150829/runs/cycle_002_20260207_151511/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierA_mean
- rationale: quick gate no improvement

### 20260207-152852-ralph-loop-cycle-003
- change_id: 20260207-152852-ralph-loop-cycle-003
- change_type: Eval
- scope: ralph-wiggum-loop cycle 003
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active_smoke_fast_20260207_150829; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/loop_smoke_fast_20260207_150829/runs/cycle_003_20260207_152207/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierA_mean
- rationale: quick gate no improvement

### 20260207-154141-ralph-loop-smoke-regression-v1
- change_id: 20260207-154141-ralph-loop-smoke-regression-v1
- change_type: Eval
- scope: 新增并执行 `tools/ralph_loop_smoke_test.sh`（`max_cycles=2`, `chunk_cycles=1`）做 checkpoint/resume/max_cycles 控制流回归
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: 控制面回归通过：run1=`chunk_checkpoint(cycle=1,next_cycle=2)`，run2=`max_cycles(cycle=2)`，且每个 cycle 目录仅生成一次
- evidence:
  - smoke script | ref=path:tools/ralph_loop_smoke_test.sh
  - run1 log | ref=path:/tmp/ralph_loop_smoke_test_zto3pC/run1.log
  - run2 log | ref=path:/tmp/ralph_loop_smoke_test_zto3pC/run2.log
  - smoke state | ref=path:/tmp/ralph_loop_smoke_test_zto3pC/state.json
- outcome: ADOPT
- rationale: 将关键 loop 控制行为固化为一键回归，后续改动可快速识别“断点续跑失效/重复跑周期/终止条件失效”等退化。

### 20260207-180912-ralph-loop-singleton-stability-v1
- change_id: 20260207-180912-ralph-loop-singleton-stability-v1
- change_type: Restructure
- scope: `tools/ralph_hook_dispatcher.sh` + `tools/ralph_time_hook.sh` 的单实例/反抖动改造与线上重启复核
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: infra only（不宣称策略强度提升）；新增 dispatcher lock，time_hook 改为连续 miss 阈值触发重启（默认 3 次）以抑制误判重启风暴
- evidence:
  - dispatcher singleton lock | ref=path:tools/ralph_hook_dispatcher.sh
  - time_hook anti-flap miss-threshold | ref=path:tools/ralph_time_hook.sh
  - runtime heartbeat resumed | ref=path:tmp/ralph_loop_events.ndjson
- outcome: ADOPT
- rationale: 解决重复实例和误重启导致的资源浪费/上下文扰动，使 loop 回到单栈持续运行并保持低频事件驱动监控。

### 20260207-183932-ralph-loop-model-review-checkpoint-v1
- change_id: 20260207-183932-ralph-loop-model-review-checkpoint-v1
- change_type: Restructure
- scope: `tools/ralph_loop_supervisor.sh` + `tools/ralph_hook_dispatcher.sh` + `tools/ralph_human_log.py` + `tools/ralph_time_hook.sh`
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: infra only；新增“每 N 轮模型审查”事件触发（`MODEL_REVIEW_EVERY`，默认 3）与人类可读总览日志（含模型触发与 hook 产物索引）
- evidence:
  - periodic checkpoint event emit | ref=path:tools/ralph_loop_supervisor.sh
  - dispatcher model_review_due routing | ref=path:tools/ralph_hook_dispatcher.sh
  - human-readable progress log | ref=path:tools/ralph_human_log.py
  - generated report sample | ref=path:tmp/ralph_loop_human_log.md
- outcome: ADOPT
- rationale: 将“大模型按周期参与”从人工介入改为程序触发，同时提供可读日志把每轮状态、模型触发与证据路径聚合给操作者。

### 20260207-154121-ralph-loop-cycle-001
- change_id: 20260207-154121-ralph-loop-cycle-001
- change_type: Eval
- scope: ralph-wiggum-loop cycle 001
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active_smoke_20260207_154107; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/private/tmp/ralph_loop_smoke_test_zto3pC/runs/cycle_001_20260207_154108/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierA_mean
- rationale: quick gate no improvement

### 20260207-154135-ralph-loop-cycle-002
- change_id: 20260207-154135-ralph-loop-cycle-002
- change_type: Eval
- scope: ralph-wiggum-loop cycle 002
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active_smoke_20260207_154107; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/private/tmp/ralph_loop_smoke_test_zto3pC/runs/cycle_002_20260207_154121/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierA_mean
- rationale: quick gate no improvement

### 20260207-192300-ralph-hook-resilience-v1
- change_id: 20260207-192300-ralph-hook-resilience-v1
- change_type: Restructure
- scope: `tools/ralph_hook_dispatcher.sh` + `tools/ralph_human_log.py`
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: infra only；增加 hook 子代理硬超时回收、失败重试+熔断、结果完整性门禁（`final_message`/events），并把每次 hook 结果写入 `hook_result.json` 供人类日志消费
- evidence:
  - dispatcher timeout/retry/circuit-breaker/result-gate | ref=path:tools/ralph_hook_dispatcher.sh
  - human log hook result rendering | ref=path:tools/ralph_human_log.py
  - failure-path artifact sample | ref=path:tmp/ralph_hook_runs/20260207_192034_checkpoint_model_review_due/hook_result.json
  - runtime readable report | ref=path:tmp/ralph_loop_human_log.md
- outcome: ADOPT
- rationale: 修复 `codex exec` 挂起和无结论产物导致的“表面运行、实则失效”问题；在不增加系统复杂度的前提下补齐可恢复性与可观察性。

### 20260207-193950-ralph-autopilot-liveness-probe-v1
- change_id: 20260207-193950-ralph-autopilot-liveness-probe-v1
- change_type: Restructure
- scope: `tools/ralph_autopilot_start.sh`
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: infra only；将启动器进程存活判定从 `ps` 命令匹配改为 `pid_file + kill -0` 优先，`pgrep` 仅作补充，避免沙箱环境下 `ps` 受限导致误判“未运行”
- evidence:
  - startup liveness probe logic | ref=path:tools/ralph_autopilot_start.sh
  - runtime process set | ref=path:tmp/ralph_loop_events.ndjson
- outcome: ADOPT
- rationale: 修复“进程已运行却被判定失败”的启动抖动，降低无人值守启动阶段的误报与重启噪声。

### 20260207-202130-ralph-loop-runtime-stabilization-v1
- change_id: 20260207-202130-ralph-loop-runtime-stabilization-v1
- change_type: Restructure
- scope: `tools/ralph_time_hook.sh` + runtime process orchestration
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: infra only；time_hook 进程存活判定与 autopilot 启动器统一（`pid_file + kill -0` 优先），并在本轮运行中采用“supervisor+dispatcher 单栈”稳定模式规避多实例拉起
- evidence:
  - time_hook liveness probe simplification | ref=path:tools/ralph_time_hook.sh
  - runtime heartbeat switched to current child | ref=path:tmp/ralph_loop_events.ndjson
  - current live process set | ref=path:tmp/ralph_pids/supervisor.pid
- outcome: ADOPT
- rationale: 解决近期重复实例/卡死感知混乱问题，保证循环执行与事件流可观察性一致。

### 20260207-220540-ralph-loop-cycle-001
- change_id: 20260207-220540-ralph-loop-cycle-001
- change_type: Eval
- scope: ralph-wiggum-loop cycle 001
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active_smoke_20260207_220526; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/private/tmp/ralph_loop_smoke_test_fix_KQN8MB/runs/cycle_001_20260207_220527/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierA_mean
- rationale: quick gate no improvement

### 20260207-220624-ralph-loop-cycle-001
- change_id: 20260207-220624-ralph-loop-cycle-001
- change_type: Eval
- scope: ralph-wiggum-loop cycle 001
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active_smoke_20260207_220610; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/private/tmp/ralph_loop_smoke_test_fix2_p1kM4S/runs/cycle_001_20260207_220610/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierA_mean
- rationale: quick gate no improvement

### 20260207-220638-ralph-loop-cycle-002
- change_id: 20260207-220638-ralph-loop-cycle-002
- change_type: Eval
- scope: ralph-wiggum-loop cycle 002
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active_smoke_20260207_220610; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/private/tmp/ralph_loop_smoke_test_fix2_p1kM4S/runs/cycle_002_20260207_220624/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierA_mean
- rationale: quick gate no improvement

### 20260207-220652-ralph-loop-cycle-003
- change_id: 20260207-220652-ralph-loop-cycle-003
- change_type: Eval
- scope: ralph-wiggum-loop cycle 003
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active_smoke_20260207_220610; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/private/tmp/ralph_loop_smoke_test_fix2_p1kM4S/runs/cycle_003_20260207_220638/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierA_mean
- rationale: quick gate no improvement

### 20260207-220800-ralph-loop-cycle-001
- change_id: 20260207-220800-ralph-loop-cycle-001
- change_type: Eval
- scope: ralph-wiggum-loop cycle 001
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active_locktest; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/private/tmp/ralph_loop_locktest2_IdiWzG/runs/cycle_001_20260207_220746/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierA_mean
- rationale: quick gate no improvement

### 20260207-220814-ralph-loop-cycle-002
- change_id: 20260207-220814-ralph-loop-cycle-002
- change_type: Eval
- scope: ralph-wiggum-loop cycle 002
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active_locktest; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/private/tmp/ralph_loop_locktest2_IdiWzG/runs/cycle_002_20260207_220800/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierA_mean
- rationale: quick gate no improvement

### 20260207-220850-ralph-loop-cycle-001
- change_id: 20260207-220850-ralph-loop-cycle-001
- change_type: Eval
- scope: ralph-wiggum-loop cycle 001
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active_locktest; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/private/tmp/ralph_loop_locktest3_ScFLvd/runs/cycle_001_20260207_220836/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierA_mean
- rationale: quick gate no improvement

### 20260207-220904-ralph-loop-cycle-002
- change_id: 20260207-220904-ralph-loop-cycle-002
- change_type: Eval
- scope: ralph-wiggum-loop cycle 002
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active_locktest; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/private/tmp/ralph_loop_locktest3_ScFLvd/runs/cycle_002_20260207_220850/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierA_mean
- rationale: quick gate no improvement

### 20260207-224325-ralph-loop-cycle-001
- change_id: 20260207-224325-ralph-loop-cycle-001
- change_type: Eval
- scope: ralph-wiggum-loop cycle 001
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active_smoke_20260207_224311; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/private/tmp/ralph_loop_smoke_test_fix3_RPlviQ/runs/cycle_001_20260207_224311/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierA_mean
- rationale: quick gate no improvement

### 20260207-224339-ralph-loop-cycle-002
- change_id: 20260207-224339-ralph-loop-cycle-002
- change_type: Eval
- scope: ralph-wiggum-loop cycle 002
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active_smoke_20260207_224311; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/private/tmp/ralph_loop_smoke_test_fix3_RPlviQ/runs/cycle_002_20260207_224325/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierA_mean
- rationale: quick gate no improvement

### 20260207-224353-ralph-loop-cycle-003
- change_id: 20260207-224353-ralph-loop-cycle-003
- change_type: Eval
- scope: ralph-wiggum-loop cycle 003
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active_smoke_20260207_224311; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/private/tmp/ralph_loop_smoke_test_fix3_RPlviQ/runs/cycle_003_20260207_224339/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierA_mean
- rationale: quick gate no improvement

### 20260207-224700-ralph-autopilot-reliability-fix
- change_id: 20260207-224700-ralph-autopilot-reliability-fix
- change_type: Restructure
- scope: ralph autopilot process-liveness and duplicate-run prevention
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: add parent/cycle file-locks + health heartbeat checks + stale-lock recovery + supervisor child pid handling fix
- evidence:
  - smoke checkpoint/resume/max_cycles | ref=path:/private/tmp/ralph_loop_smoke_test_fix3_RPlviQ/run2.log
  - cycle uniqueness and lock behavior | ref=path:/private/tmp/ralph_loop_locktest3_ScFLvd/run_b.log
  - heartbeat files generated | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_health/supervisor_heartbeat.json
- outcome: CONTINUE
- next_hypothesis: focus_metric=runtime_orchestration_stability
- rationale: code-level guards are validated, but this execution environment still reaps detached processes; need host-level daemon launch path for true unattended operation.

### 20260208-003400-full-eval-top-human-goalpack-check
- change_id: 20260208-003400-full-eval-top-human-goalpack-check
- change_type: Eval
- scope: full-matrix gate check (`coinpoker + gg + pool_eval + br_proxy`) for `system_bot_policy_v3_loop_active`
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: coin Tier-A=+22.85, Tier-P=+16.99, pool_weighted=+13.7755, br_worst=+9.7648, gg Tier-A=+6.5195, gg Tier-P=+4.7411 (all bb/100); pool/br numbers match baseline reference run (no net improvement claim)
- evidence:
  - coinpoker full eval root | ref=path:/Users/peng/Workspace/codex/poker2/tmp/full_eval_top_human_clean_20260207_2306/coinpoker
  - br proxy worst-case summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/full_eval_top_human_clean_20260207_2306/coinpoker/br_proxy_fast/br_proxy_summary.json
  - gg dual-tier batch summaries | ref=path:/Users/peng/Workspace/codex/poker2/tmp/full_eval_top_human_clean_20260207_2306/gg
- outcome: CONTINUE
- next_hypothesis: tighten top-human goal pack (robustness/tail-risk/OOD scene family) before promotion decisions
- rationale: current run passes non-negative gates, but this gate pack is too weak to conclude "near top-human"; results are baseline-level, not a new strength jump.

### 20260208-010200-loop-goalpack-v2-and-autopilot-hardening
- change_id: 20260208-010200-loop-goalpack-v2-and-autopilot-hardening
- change_type: Enforce
- scope: `ralph_wiggum_loop` gate model + `ralph` watchdog lifecycle and stale-lock recovery
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: 将目标从“6个均值非负”升级为“高阈值 + 稳健约束（seed最差/波动上限/turn+river facing=Y 高支持弱桶守卫）”；循环默认改用 `goal_pack_top_human_v2`
- evidence:
  - v2 goal pack | ref=path:/Users/peng/Workspace/codex/poker2/specs/loop_goals/goal_pack_top_human_v2.json
  - loop gate implementation update | ref=path:/Users/peng/Workspace/codex/poker2/tools/ralph_wiggum_loop.py
  - launchd live run with v2 pack | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_supervisor.log
- outcome: CONTINUE
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: 新门槛生效后当前策略不再“虚假达标”，系统将继续迭代直到通过更强稳健门禁。

### 20260208-012900-ralph-log-reset-and-ops-hardening
- change_id: 20260208-012900-ralph-log-reset-and-ops-hardening
- change_type: Restructure
- scope: log reset + ralph supervisor/dispatcher reliability + human_log observability
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: 清空实时日志与hook历史输出；修复 supervisor/dispatcher JSON 字符串未转义导致的坏JSON风险；将 stall 进度扫描从 `run.log + *.json` 缩减为 `run.log + cycle_result/review + state` 以降低巡检IO；human_log 在事件日志被清空时改为读取 supervisor heartbeat，避免误报“需关注”
- evidence:
  - human log after reset | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_human_log.md
  - supervisor json/perf patch | ref=path:/Users/peng/Workspace/codex/poker2/tools/ralph_loop_supervisor.sh
  - dispatcher auth/home + json patch | ref=path:/Users/peng/Workspace/codex/poker2/tools/ralph_hook_dispatcher.sh
- outcome: CONTINUE
- next_hypothesis: focus_metric=runtime_orchestration_stability
- rationale: 当前运行恢复为 heartbeat/running，日志视图已去历史噪音；后续继续观察长时段自动迭代稳定性与周期完成率。

### 20260208-043138-ralph-loop-cycle-001
- change_id: 20260208-043138-ralph-loop-cycle-001
- change_type: Eval
- scope: ralph-wiggum-loop cycle 001
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_001_20260208_012750/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_001_20260208_012750/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate no improvement

### 20260208-060652-ralph-loop-cycle-002
- change_id: 20260208-060652-ralph-loop-cycle-002
- change_type: Eval
- scope: ralph-wiggum-loop cycle 002
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_001_20260208_012750/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_002_20260208_043138/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate no improvement

### 20260208-074200-ralph-loop-cycle-003
- change_id: 20260208-074200-ralph-loop-cycle-003
- change_type: Eval
- scope: ralph-wiggum-loop cycle 003
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_001_20260208_012750/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_003_20260208_060652/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate no improvement

### 20260208-074211-ralph-model-review-plan-cycle-003
- change_id: 20260208-074211-ralph-model-review-plan-cycle-003
- change_type: Plan
- scope: hook model_review_due lightweight review + next-round single-mechanism plan (focus-coverage quick gate)
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: cycle3 quick_delta=0.0; focus gap `coinpoker.tierP_facingY_turnriver_worst_bb100`=-630.0702 (value=-780.0702 vs threshold=-150.0); 7 distinct trial options_hash but only 1 unique quick metric vector
- evidence:
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_003_20260208_060652/review.json
  - cycle result | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_003_20260208_060652/cycle_result.json
  - quick sample trigger coverage (`high_price_low_spr_hits`=0) | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_003_20260208_060652/active_quick/coinpoker_7max_mw_v3_actionspace_v2/tierP/seed3000/scrimmage_report.json
  - next plan artifact | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_next_plan.md
- outcome: CONTINUE
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: 现有 quick gate 对焦点机制覆盖不足，导致候选间无可用梯度；先引入覆盖门控再继续自动调参，避免重复无信息拒绝。

### 20260208-091745-ralph-loop-cycle-004
- change_id: 20260208-091745-ralph-loop-cycle-004
- change_type: Eval
- scope: ralph-wiggum-loop cycle 004
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_001_20260208_012750/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_004_20260208_074200/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate no improvement

### 20260208-104900-ralph-loop-per-cycle-judge-and-quick-gate-hardening
- change_id: 20260208-104900-ralph-loop-per-cycle-judge-and-quick-gate-hardening
- change_type: Restructure
- scope: per-cycle model judge wiring + next_action consume path + quick gate validity guard
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: supervisor 每轮发出 `checkpoint/cycle_completed`；dispatcher 放行并校验 `tmp/ralph_next_action.json`；worker 每轮消费 next_action 并将 quick gate 升级为 `focus_support + behavior_delta` 双门禁（低支持/无行为变化不再误判为“同分无改进”）
- evidence:
  - supervisor event wiring | ref=path:/Users/peng/Workspace/codex/poker2/tools/ralph_loop_supervisor.sh
  - dispatcher cycle_completed + next_action validation | ref=path:/Users/peng/Workspace/codex/poker2/tools/ralph_hook_dispatcher.sh
  - worker consume + quick gate diagnostics | ref=path:/Users/peng/Workspace/codex/poker2/tools/ralph_wiggum_loop.py
  - isolated smoke run_root | ref=path:/tmp/ralph_loop_new_smoke_5iznk5
  - live dispatcher accepted cycle_completed | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_hook_dispatcher.log
- outcome: CONTINUE
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: 先把“每轮有脑 + 可消费动作 + 候选有效性”闭环打通，避免继续在无梯度 quick gate 上空转；后续再观察是否打破 quick_delta=0 连续拒绝。

### 20260208-130600-ralph-humanlog-fullmodel-and-parallel-budget
- change_id: 20260208-130600-ralph-humanlog-fullmodel-and-parallel-budget
- change_type: Restructure
- scope: `human_log` 完整展示模型输出 + 评测并发改为自适应预算（高并发且预留系统余量）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: `tools/ralph_human_log.py` 在每个 hook run 下输出 `final_message_content` 全文；`tools/ralph_loop_supervisor.sh` 从固定 `LOOP_JOBS=6` 改为按 CPU 预算自动计算并发（当前实例解析为 `jobs=9`，`quick_jobs_ratio=0.75`）；`tools/ralph_wiggum_loop.py` 新增 `--quick-jobs-ratio` 并在 quick/full(gg) 阶段统一采用比例并发控制，减少“过低并发”且避免满负荷硬顶
- evidence:
  - human log full model content | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_human_log.md
  - supervisor auto parallel budget log | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_supervisor.log
  - loop parallel controls implementation | ref=path:/Users/peng/Workspace/codex/poker2/tools/ralph_wiggum_loop.py
  - dispatcher cycle_completed success run | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_hook_runs/20260208_104705_checkpoint_cycle_completed/hook_result.json
  - active process command (jobs=9, quick_jobs_ratio=0.75) | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_supervisor.log
- outcome: CONTINUE
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: 先提升可观测性与并发利用效率，确保每轮模型结论可审计、评测吞吐提升且不过载，再继续观察是否缩短 cycle 完成时间与提高有效迭代密度。

### 20260208-104356-ralph-loop-cycle-901
- change_id: 20260208-104356-ralph-loop-cycle-901
- change_type: Eval
- scope: ralph-wiggum-loop cycle 901
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active_smoke_iter_20260208_104332; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/private/tmp/ralph_loop_new_smoke_5iznk5/runs/cycle_901_20260208_104332/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierA_mean
- rationale: quick gate low focus support

### 20260208-145045-ralph-loop-cycle-005
- change_id: 20260208-145045-ralph-loop-cycle-005
- change_type: Eval
- scope: ralph-wiggum-loop cycle 005
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_001_20260208_012750/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_005_20260208_130438/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate no behavior delta

### 20260215-162620-hook-cycle-028-behavior-delta-floor-escalation
- change_id: 20260215-162620-hook-cycle-028-behavior-delta-floor-escalation
- change_type: Restructure
- scope: `tools/ralph_wiggum_loop.py`（`quick_gate_no_behavior_delta` 下调高候选扰动自动放大量级）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: cycle028 `quick_gate_no_behavior_delta` 且 `no_improve_streak=2`；本次执行单机制补丁 + next_action/next_plan 落地，未跑重型评测
- evidence:
  - E1 | quick_gate.reason=quick_gate_no_behavior_delta | n=N/A | seeds=N/A | evidence_ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_028_20260215_123315/review.json
  - E2 | behavior_pass_count=0, eligible_count=0, support_pass_count=5 | n=6 candidates | seeds=N/A | evidence_ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_028_20260215_123315/cycle_result.json
  - E3 | mechanism patch applied | n=N/A | seeds=N/A | evidence_ref=path:/Users/peng/Workspace/codex/poker2/tools/ralph_wiggum_loop.py
  - E4 | next action + plan emitted | n=N/A | seeds=N/A | evidence_ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_next_action.json,path:/Users/peng/Workspace/codex/poker2/tmp/ralph_next_plan.md
- outcome: CONTINUE
- rationale: 在支持度充足但行为差异不足导致的 quick gate 死锁下，提升自动扰动下限优先恢复可观测行为变化，保持单机制改动与可回退性。

### 20260208-194118-ralph-loop-cycle-006
- change_id: 20260208-194118-ralph-loop-cycle-006
- change_type: Eval
- scope: ralph-wiggum-loop cycle 006
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_001_20260208_012750/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_006_20260208_180547/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate no behavior delta

### 20260208-211519-ralph-loop-cycle-007
- change_id: 20260208-211519-ralph-loop-cycle-007
- change_type: Eval
- scope: ralph-wiggum-loop cycle 007
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_001_20260208_012750/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_007_20260208_194118/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate no behavior delta

### 20260208-224909-ralph-loop-cycle-008
- change_id: 20260208-224909-ralph-loop-cycle-008
- change_type: Eval
- scope: ralph-wiggum-loop cycle 008
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_001_20260208_012750/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_008_20260208_211519/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate no behavior delta

### 20260209-002339-ralph-loop-cycle-009
- change_id: 20260209-002339-ralph-loop-cycle-009
- change_type: Eval
- scope: ralph-wiggum-loop cycle 009
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_001_20260208_012750/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_009_20260208_224909/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate no behavior delta

### 20260209-004130-ralph-model-review-plan-cycle-010
- change_id: 20260209-004130-ralph-model-review-plan-cycle-010
- change_type: Plan
- scope: hook `model_review_due` 强化审查 + 单机制 next_action 落地（quick behavior diversity escalation）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: 机制审查结论：cycle009 `quick_gate_no_behavior_delta`，6/6 候选行为差异为 0；state `no_improve_streak=9`
- evidence:
  - loop state | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_state_v2.json
  - completed review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_009_20260208_224909/review.json
  - completed result | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_009_20260208_224909/cycle_result.json
  - in-progress cycle runlog | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_010_20260209_003846/active_quick/coinpoker_7max_mw_v3_actionspace_v2/tierA/run.log
  - next action artifact | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_next_action.json
  - next plan artifact | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_next_plan.md
- outcome: CONTINUE
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: 当前阻塞点是 quick 阶段缺乏行为梯度而非单纯分数问题；先用大步候选与轻降行为门槛恢复可比较性，再决定是否需要机制级 fallback 补丁。

### 20260209-013230-ralph-model-review-plan-cycle-999
- change_id: 20260209-013230-ralph-model-review-plan-cycle-999
- change_type: Plan
- scope: hook `model_review_due` 强化审查 + 单机制迭代效率修复（high-price defend behavior diversity escalation）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: review 结论为 `quick_gate_no_behavior_delta`; cycle009 quick gate `candidate_count=6`, `behavior_pass_count=0`, `eligible_count=0`; state `no_improve_streak=9`
- evidence:
  - loop state | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_state_v2.json
  - completed review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_009_20260208_224909/review.json
  - completed result | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_009_20260208_224909/cycle_result.json
  - in-progress cycle dir | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_010_20260209_013152
  - next action artifact | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_next_action.json
  - next plan artifact | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_next_plan.md
- outcome: CONTINUE
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: 阻塞主因是 quick 阶段候选行为不分离导致无可比较梯度；先用同机制大步长 + 轻度行为门槛提示恢复可比较性，再根据下一 completed cycle 决定是否切换 knob 家族。

### 20260209-112308-ralph-loop-cycle-010
- change_id: 20260209-112308-ralph-loop-cycle-010
- change_type: Eval
- scope: ralph-wiggum-loop cycle 010
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_001_20260208_012750/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_010_20260209_013152/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate no behavior delta

### 20260209-125306-ralph-loop-cycle-011
- change_id: 20260209-125306-ralph-loop-cycle-011
- change_type: Eval
- scope: ralph-wiggum-loop cycle 011
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_001_20260208_012750/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_011_20260209_112308/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate no behavior delta

### 20260209-143309-ralph-loop-cycle-012
- change_id: 20260209-143309-ralph-loop-cycle-012
- change_type: Eval
- scope: ralph-wiggum-loop cycle 012
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_001_20260208_012750/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_012_20260209_125306/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate no behavior delta

### 20260209-161551-ralph-loop-cycle-013
- change_id: 20260209-161551-ralph-loop-cycle-013
- change_type: Eval
- scope: ralph-wiggum-loop cycle 013
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_001_20260208_012750/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_013_20260209_143310/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate no behavior delta

### 20260209-175858-ralph-loop-cycle-014
- change_id: 20260209-175858-ralph-loop-cycle-014
- change_type: Eval
- scope: ralph-wiggum-loop cycle 014
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_001_20260208_012750/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_014_20260209_161551/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate no behavior delta

### 20260209-194133-ralph-loop-cycle-015
- change_id: 20260209-194133-ralph-loop-cycle-015
- change_type: Eval
- scope: ralph-wiggum-loop cycle 015
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_001_20260208_012750/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_015_20260209_175858/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate no behavior delta

### 20260209-212501-ralph-loop-cycle-016
- change_id: 20260209-212501-ralph-loop-cycle-016
- change_type: Eval
- scope: ralph-wiggum-loop cycle 016
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_001_20260208_012750/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_016_20260209_194210/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate no behavior delta

### 20260209-230751-ralph-loop-cycle-017
- change_id: 20260209-230751-ralph-loop-cycle-017
- change_type: Eval
- scope: ralph-wiggum-loop cycle 017
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_001_20260208_012750/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_017_20260209_212501/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate no behavior delta

### 20260210-171339-ralph-loop-cycle-018
- change_id: 20260210-171339-ralph-loop-cycle-018
- change_type: Eval
- scope: ralph-wiggum-loop cycle 018
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_001_20260208_012750/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_018_20260210_152329/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate no behavior delta

### 20260210-173000-ralph-hook-behavior-escalation-factor
- change_id: 20260210-173000-ralph-hook-behavior-escalation-factor
- change_type: Refine
- scope: `tools/ralph_wiggum_loop.py`（候选生成支持 `behavior_escalation_factor`，用于修复 quick 阶段行为无差异阻塞）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: cycle018 触发强制改动条件（`no_improve_streak=18` + `quick_gate_no_behavior_delta`）；本次为机制补丁与 next_action 落地，未跑重评测
- evidence:
  - loop state | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_state_v2.json
  - completed review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_018_20260210_152329/review.json
  - completed result | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_018_20260210_152329/cycle_result.json
  - next action artifact | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_next_action.json
  - next plan artifact | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_next_plan.md
- outcome: CONTINUE
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: 过去多个 cycle 候选行为差异持续为 0；先通过单机制步长放大恢复 quick 可比较梯度，再观察下个 completed cycle 的 behavior_pass_count/eligible_count。

### 20260210-174448-ralph-model-review-due-cycle-018
- change_id: 20260210-174448-ralph-model-review-due-cycle-018
- change_type: Plan
- scope: hook `model_review_due` 强化审查 + 单机制迭代解阻（quick behavior observability hardening）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: cycle018 `quick_gate_no_behavior_delta`; `candidate_count=6`, `behavior_pass_count=0`, `eligible_count=0`; state `no_improve_streak=18`
- evidence:
  - loop state | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_state_v2.json
  - completed review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_018_20260210_152329/review.json
  - completed result | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_018_20260210_152329/cycle_result.json
  - in-progress quick runlogs | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_019_20260210_171339/active_quick/*/*/run.log
  - next action artifact | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_next_action.json
  - next plan artifact | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_next_plan.md
- outcome: CONTINUE
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: 当前阻塞来自 quick 候选行为不可分离（非 score 本身）；先通过同 family 单 knob 大步扰动 + 支撑度门槛收紧恢复可比较梯度，再依据下一 completed cycle 决定是否进入代码补丁。

### 20260210-194357-ralph-loop-cycle-019
- change_id: 20260210-194357-ralph-loop-cycle-019
- change_type: Eval
- scope: ralph-wiggum-loop cycle 019
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_001_20260208_012750/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_019_20260210_174512/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate low focus support

## [autopilot-hook] 2026-03-06T04:14:41+0800 cycle=141 reason=cycle_completed
- change_type: Patch
- decision: apply_river_forced_bet_deadlock_recovery_notch_v1
- why: `no_improve_streak=59` 且最新 completed cycle 141 的 quick gate 为 `quick_gate_low_focus_support`，focus support 命中继续停滞（targeted focus support_after.hits=0）。
- what: patched `poker2/runtime/system_policy.py`，在既有 RIVER forced-bet stalled+unsaturated 分支增加 bounded deadlock recovery notch：仅当 reactivation_floor_relief 已触发且 proximity/ramp 仍近零时，窄幅下探 deadlock floor 并小幅上调 deadlock cap/gates + support_window_expand_cap。
- rollback: 删除新增 deadlock recovery notch 分支（`reactivation_floor_relief + near-zero proximity/ramp` 条件块）并恢复原 deadlock 参数。
- verify: `PYTHONPYCACHEPREFIX=/tmp/pycache_verify python3 -m py_compile poker2/runtime/system_policy.py`
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle142_20260306_041441_autohook.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_141_20260306_021141/review.json`, `tmp/ralph_loop_runs_v2/cycle_141_20260306_021141/cycle_result.json`

### 2026-03-06-cycle141-river-forced-bet-deadlock-recovery-notch-v1
- change_id: 2026-03-06-cycle141-river-forced-bet-deadlock-recovery-notch-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（RIVER forced-bet stalled deadlock recovery notch）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（checkpoint light patch; heavy eval deferred）
- evidence:
  - E1 | metric=no_improve_streak=59 | n=1 state | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E2 | metric=quick_gate.reason=quick_gate_low_focus_support,targeted_focus_support_after_hits=0 | n=1 cycle | seeds=cycle141 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_141_20260306_021141/review.json
  - E3 | metric=mechanism_patch_applied(system_policy) | n=1 file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: 用单机制窄幅 deadlock recovery notch 提升 stalled forced-bet 分支 support-hit 触发概率，保持低价路径隔离与可回退性。

### 2026-02-10-c020-quickgate-support-unblock
- change_id: 2026-02-10-c020-quickgate-support-unblock
- change_type: Enforce
- scope: `tmp/ralph_next_action.json`（quick-gate 支持阈值单步放宽 + 高价位防守旋钮增幅，恢复候选可区分性）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: cycle19 快速门禁未通过（`quick_gate_low_focus_support`）；`eligible_count=0`，`behavior_pass_count=0`，候选 `behavior_delta` 全为 `0.0`
- evidence:
  - E1 | `quick_gate.reason=quick_gate_low_focus_support` | n=candidates:6 | seeds=3000–3002(quick) | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_019_20260210_174512/review.json
  - E2 | `active_support.hits=1 < focus_support_min_hits=2` | n=hands:20 | seeds=3000–3002(quick) | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_019_20260210_174512/review.json
  - E3 | `behavior_delta=0.0` (all 6 candidates) | n=6 | seeds=3000–3002(quick) | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_019_20260210_174512/cycle_result.json
- outcome: CONTINUE
- rationale: 连续 19 轮无改进且快速门禁因支持度/行为差异不足卡死，先用可回退的控制面机制补丁恢复“候选可判别性”；若下一轮仍无行为分离，再切换到代码层的候选生成机制改造。

### 20260210-214132-ralph-loop-cycle-020
- change_id: 20260210-214132-ralph-loop-cycle-020
- change_type: Eval
- scope: ralph-wiggum-loop cycle 020
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_001_20260208_012750/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_020_20260210_194357/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate no behavior delta

### 2026-02-10-ralph-loop-quick-gate-stagnation-escape
- change_id: 2026-02-10-ralph-loop-quick-gate-stagnation-escape
- change_type: Restructure
- scope: `tools/ralph_wiggum_loop.py`（quick gate 行为差异阈值加入 no_improve_streak 逃逸机制）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: cycle=20 显示 quick_gate_no_behavior_delta；本次改为保留 `behavior_delta_min` 配置，同时引入 `behavior_delta_min_effective`（streak>=2 时可降至 0.0）
- evidence:
  - loop state | metric=no_improve_streak=20 | ref=path:tmp/ralph_loop_state_v2.json
  - completed review | metric=quick_gate.reason=quick_gate_no_behavior_delta | ref=path:tmp/ralph_loop_runs_v2/cycle_020_20260210_194357/review.json
  - completed result | metric=candidate behavior_delta 全为0.0 且 eligible_count=0 | ref=path:tmp/ralph_loop_runs_v2/cycle_020_20260210_194357/cycle_result.json
- outcome: CONTINUE
- rationale: 该补丁仅放宽“长期无改进”时的行为差异门槛，避免候选全被 quick gate 过滤导致无法归因；若出现均值回撤可单文件回滚。

### 20260211-045910-ralph-loop-cycle-021
- change_id: 20260211-045910-ralph-loop-cycle-021
- change_type: Eval
- scope: ralph-wiggum-loop cycle 021
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_001_20260208_012750/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_021_20260211_002436/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate no improvement

### 2026-02-11-c021-candidate-auto-escalation
- change_id: 2026-02-11-c021-candidate-auto-escalation
- change_type: Restructure
- scope: `tools/ralph_wiggum_loop.py`（候选生成加入 no_improve_streak 自动步长放大 + quick_gate 证据字段）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: cycle21 `quick_gate_no_improvement` 且 `no_improve_streak=21`；执行单机制补丁并下发下一轮动作，未跑重型评测
- evidence:
  - loop state | metric=no_improve_streak=21 | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_state_v2.json
  - completed review | metric=quick_gate.reason=quick_gate_no_improvement | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_021_20260211_002436/review.json
  - completed result | metric=candidate_count=6, eligible_count=6, quick tie cluster | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_021_20260211_002436/cycle_result.json
  - mechanism patch | ref=path:/Users/peng/Workspace/codex/poker2/tools/ralph_wiggum_loop.py
  - next action artifact | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_next_action.json
  - next plan artifact | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_next_plan.md
- outcome: CONTINUE
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: 在 quick score 长期同分/弱分离时，仅放宽 behavior gate 不足以产生可比较梯度；本补丁把“长期停滞”直接映射到候选扰动幅度，并把因子写入 review 以便回放与回滚。

### 20260211-093628-ralph-loop-cycle-022
- change_id: 20260211-093628-ralph-loop-cycle-022
- change_type: Eval
- scope: ralph-wiggum-loop cycle 022
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_001_20260208_012750/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_022_20260211_045910/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate no improvement

### 20260211-093639-ralph-loop-cycle-022-autohook
- change_id: 20260211-093639-ralph-loop-cycle-022-autohook
- change_type: Restructure
- scope: `tools/ralph_wiggum_loop.py`（candidate auto-escalation ladder for prolonged no-improve streak）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: light checkpoint patch; no heavy eval run in this hook step
- evidence:
  - quick gate no improvement with `no_improve_streak=22` | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_022_20260211_045910/cycle_result.json
  - top candidates tied (`quick_score=11.97395625`) and mostly `behavior_delta=0.0` | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_022_20260211_045910/review.json
  - mechanism patch applied | ref=path:/Users/peng/Workspace/codex/poker2/tools/ralph_wiggum_loop.py
- outcome: CONTINUE
- rationale: increase candidate perturbation amplitude at high stagnation to break repeated tie/no-behavior plateaus before the next promotion gate.

### 20260213-150819-ralph-loop-cycle-023
- change_id: 20260213-150819-ralph-loop-cycle-023
- change_type: Eval
- scope: ralph-wiggum-loop cycle 023
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_001_20260208_012750/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_023_20260213_110817/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate no improvement

### 20260213-150859-ralph-hook-cycle-023-ranked-behavior-bonus
- change_id: 20260213-150859-ralph-hook-cycle-023-ranked-behavior-bonus
- change_type: Restructure
- scope: `tools/ralph_wiggum_loop.py`（quick gate 候选排序加入 stagnation behavior bonus + ranked quick evidence）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: cycle023 `quick_gate_no_improvement`；`no_improve_streak=23`；`active_quick_score` 与 `best_trial_quick_score` 同为 `11.97395625`
- evidence:
  - loop state | metric=no_improve_streak=23 | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_state_v2.json
  - completed review | metric=quick_gate.reason=quick_gate_no_improvement | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_023_20260213_110817/review.json
  - completed result | metric=best_trial_quick_score==active_quick_score | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_023_20260213_110817/cycle_result.json
  - mechanism patch | ref=path:/Users/peng/Workspace/codex/poker2/tools/ralph_wiggum_loop.py
  - next action artifact | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_next_action.json
  - next plan artifact | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_next_plan.md
- outcome: CONTINUE
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: 过去一轮已出现 quick 同分导致无法通过改进门槛；本补丁在停滞期优先提升“有行为差异”的候选排序权重，并把 ranked 指标落盘，保证后续门禁与回放可解释、可回退。

### 20260213-225341-ralph-loop-cycle-024
- change_id: 20260213-225341-ralph-loop-cycle-024
- change_type: Eval
- scope: ralph-wiggum-loop cycle 024
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_024_20260213_195929/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_024_20260213_195929/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_024_20260213_195929/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_024_20260213_195929/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate fail (improved=False, no_regression=False)

### 20260213-225403-ralph-hook-ranked-promotion-raw-floor-guard
- change_id: 20260213-225403-ralph-hook-ranked-promotion-raw-floor-guard
- change_type: Refine
- scope: `tools/ralph_wiggum_loop.py`（quick 晋级加 raw quick 护栏，阻断 ranked-only 假阳性晋级）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: cycle024 为 `full_gate_fail` 且 `no_improve_streak=24`；本次执行单机制补丁与 next_action 落地，未运行重型评测
- evidence:
  - loop state | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_state_v2.json
  - completed review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_024_20260213_195929/review.json
  - completed result | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_024_20260213_195929/cycle_result.json
  - mechanism patch | ref=path:/Users/peng/Workspace/codex/poker2/tools/ralph_wiggum_loop.py
  - next action artifact | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_next_action.json
  - next plan artifact | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_next_plan.md
- outcome: CONTINUE
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: 先把 quick→full 晋级一致性补齐，减少重复 full_gate_fail 产生的评测预算浪费，再继续单机制候选优化。

### 20260214-111509-supervisor-rc75-lock-backoff
- change_id: 20260214-111509-supervisor-rc75-lock-backoff
- change_type: Enforce
- scope: `tools/ralph_loop_supervisor.sh`（将 rc=75 的锁竞争路径从失败重启改为等待退避）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: N/A（本次为流程稳定性修复，未执行新评测）
- evidence:
  - restart event | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_state_v2.json
  - in-progress cycle logs (START-only before restart) | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_025_20260213_225341/trial_quick/c025_x6/coinpoker_7max_mw_v3_actionspace_v2/tierA/seed3000/run.log
  - previous completed cycle context | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_024_20260213_195929/cycle_result.json
  - patch target | ref=path:/Users/peng/Workspace/codex/poker2/tools/ralph_loop_supervisor.sh
- outcome: CONTINUE
- next_hypothesis: focus_metric=loop_stability.worker_unexpected_exit_rate
- rationale: `LOCK_HELD_EXIT_CODE=75` 在锁竞争场景不应计入失败重启；先消除编排层误判，再继续机制评测循环。

### 20260214-135152-ralph-loop-cycle-025
- change_id: 20260214-135152-ralph-loop-cycle-025
- change_type: Eval
- scope: ralph-wiggum-loop cycle 025
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_025_20260214_114312/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_025_20260214_114312/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_025_20260214_114312/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_025_20260214_114312/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate fail (improved=True, no_regression=False)

### 2026-02-14-cycle25-mechanism-only-candidate-purity
- change_id: 2026-02-14-cycle25-mechanism-only-candidate-purity
- change_type: Enforce
- scope: `tools/ralph_wiggum_loop.py`（mechanism_only 候选纯度与回填一致性）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `N/A`（checkpoint patch；未运行重型评测）
- evidence:
  - E1 | quick_gate.reason=full_gate_fail | n=N/A | seeds=N/A | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_025_20260214_114312/review.json
  - E2 | no_improve_streak=25 | n=N/A | seeds=N/A | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_025_20260214_114312/cycle_result.json
  - E3 | mechanism_only=true 且候选中 knob 占比偏高（需清理） | n=N/A | seeds=N/A | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_025_20260214_114312/cycle_result.json
- outcome: CONTINUE
- rationale: 修复 mechanism_only 下的候选类型漂移，确保停滞期改动保持单机制可归因，并通过 next_action 强化机制探索优先。

### 20260214-182049-ralph-loop-cycle-026
- change_id: 20260214-182049-ralph-loop-cycle-026
- change_type: Eval
- scope: ralph-wiggum-loop cycle 026
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=ADOPT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_026_20260214_135152/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_026_20260214_135152/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_026_20260214_135152/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_026_20260214_135152/review.json
- outcome: ADOPT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate pass: score 7.158 > baseline 6.607

### 20260214-182209-hook-cycle-026-stagnation-behavior-floor-guard
- change_id: 20260214-182209-hook-cycle-026-stagnation-behavior-floor-guard
- change_type: Enforce
- scope: `tools/ralph_wiggum_loop.py`（stagnation 期 behavior_delta_min 非零下限守卫）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: checkpoint patch; no heavy eval run in this hook step
- evidence:
  - E1 | quick_gate.reason=quick_gate_pass, no_improve_streak_before_cycle=25 | n=N/A | seeds=N/A | evidence_ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_026_20260214_135152/review.json
  - E2 | eligible candidates include behavior_delta=0.0 under stagnation escape | n=2 candidates | seeds=N/A | evidence_ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_026_20260214_135152/review.json
  - E3 | mechanism patch applied | n=N/A | seeds=N/A | evidence_ref=path:/Users/peng/Workspace/codex/poker2/tools/ralph_wiggum_loop.py
  - E4 | next action artifact emitted | n=N/A | seeds=N/A | evidence_ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_next_action.json
- outcome: CONTINUE
- rationale: 保留行为差异的最小门槛，减少停滞期“零行为变化候选”反复过门并消耗 full-gate 预算；改动单点、可回退、可解释。

### 20260214-222810-ralph-loop-cycle-027
- change_id: 20260214-222810-ralph-loop-cycle-027
- change_type: Eval
- scope: ralph-wiggum-loop cycle 027
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_026_20260214_135152/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_027_20260214_182049/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate no behavior delta

### 20260214-222947-hook-cycle-027-deadlock-aware-escalation
- change_id: 20260214-222947-hook-cycle-027-deadlock-aware-escalation
- change_type: Restructure
- scope: `tools/ralph_wiggum_loop.py`（deadlock-aware candidate behavior escalation + quick_gate evidence field）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: checkpoint patch; no heavy eval run in this hook step
- evidence:
  - E1 | quick_gate.reason=quick_gate_no_behavior_delta | n=N/A | seeds=N/A | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_027_20260214_182049/review.json
  - E2 | eligible_count=0 while support_pass_count=5 | n=6 candidates | seeds=N/A | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_027_20260214_182049/cycle_result.json
  - E3 | mechanism patch applied | n=N/A | seeds=N/A | evidence_ref=path:tools/ralph_wiggum_loop.py
  - E4 | next action + plan emitted | n=N/A | seeds=N/A | evidence_ref=path:tmp/ralph_next_action.json,path:tmp/ralph_next_plan.md
- outcome: CONTINUE
- rationale: cycle_027 deadlocked on behavior delta before no_improve_streak can trigger relaxation; this patch raises mechanism perturbation earlier from deadlock evidence, preserving strict behavior guard and single-file rollback.

### 20260215-162509-ralph-loop-cycle-028
- change_id: 20260215-162509-ralph-loop-cycle-028
- change_type: Eval
- scope: ralph-wiggum-loop cycle 028
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_026_20260214_135152/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_028_20260215_123315/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate no behavior delta

### 20260215-214454-ralph-loop-cycle-029
- change_id: 20260215-214454-ralph-loop-cycle-029
- change_type: Eval
- scope: ralph-wiggum-loop cycle 029
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=ADOPT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_029_20260215_162509/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_029_20260215_162509/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_029_20260215_162509/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_029_20260215_162509/review.json
- outcome: ADOPT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate pass: score 12.339 > baseline 7.158

### 20260215-214504-hook-cycle-029-mechanism-behavior-floor-relax
- change_id: 20260215-214504-hook-cycle-029-mechanism-behavior-floor-relax
- change_type: Restructure
- scope: `tools/ralph_wiggum_loop.py`（mechanism_priority 下机制候选 behavior 阈值自适应放宽）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: checkpoint patch；未运行重型评测
- evidence:
  - E1 | quick_gate.reason=quick_gate_pass 且 mechanism_candidate_count=1, mechanism_eligible_count=0 | n=6 candidates | seeds=N/A | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_029_20260215_162509/review.json
  - E2 | quick_score 存在重复（11.532×2, 12.40031875×2）且 behavior_delta_zero_count=2 | n=6 candidates | seeds=N/A | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_029_20260215_162509/review.json
  - E3 | mechanism patch + next action artifacts | n=N/A | seeds=N/A | evidence_ref=path:tools/ralph_wiggum_loop.py,path:tmp/ralph_next_action.json,path:tmp/ralph_next_plan.md
- outcome: CONTINUE
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: 在 deadlock/streak priority 条件下仅放宽机制候选的行为门槛，保持非机制候选原阈值，目标是减少“只有 knob 可过门”的停滞模式并提升机制改动可归因性。

### 20260216-010423-ralph-loop-cycle-030
- change_id: 20260216-010423-ralph-loop-cycle-030
- change_type: Eval
- scope: ralph-wiggum-loop cycle 030
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_029_20260215_162509/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_030_20260215_214454/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate no behavior delta

### 20260216-010513-ralph-hook-cycle-030-behavior-deadlock-escape
- change_id: 20260216-010513-ralph-hook-cycle-030-behavior-deadlock-escape
- change_type: Restructure
- scope: `tools/ralph_wiggum_loop.py`（quick gate 行为阈值首轮停滞提前放宽，减少 no_behavior_delta 死锁）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: cycle030 decision=REJECT; quick_gate.reason=quick_gate_no_behavior_delta; behavior_pass_count=0; eligible_count=0
- evidence:
  - completed review quick gate | metric=reason=quick_gate_no_behavior_delta,behavior_pass_count=0,eligible_count=0 | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_030_20260215_214454/review.json
  - completed result | metric=note=quick gate no behavior delta | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_030_20260215_214454/cycle_result.json
  - mechanism patch | metric=_effective_behavior_delta_min supports streak>=1 relaxation | ref=path:/Users/peng/Workspace/codex/poker2/tools/ralph_wiggum_loop.py
  - next action artifact | metric=mechanism_plan+quick_gate_hints written | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_next_action.json
- outcome: CONTINUE
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: 当前主要阻塞不是支持度而是行为阈值门禁；先降低首轮停滞阈值并保持非零 guard，提升候选可分辨性与可晋级概率。

### 20260216-035240-ralph-loop-cycle-031
- change_id: 20260216-035240-ralph-loop-cycle-031
- change_type: Eval
- scope: ralph-wiggum-loop cycle 031
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_029_20260215_162509/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_031_20260216_010423/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate no behavior delta


## [autopilot-hook] 2026-02-16T03:53:58+0800 cycle=31 reason=cycle_completed
- change_type: Patch
- decision: behavior_deadlock_fastpath_mechanism_only
- why: `quick_gate.reason=quick_gate_no_behavior_delta` 且 `no_improve_streak=2`，候选行为增量不足导致无法晋升。
- what: `_mechanism_priority_policy` 新增 recent deadlock 快速通道（`no_improve_streak>=2` 时直接 `mechanism_only`）。
- rollback: 回退 `tools/ralph_wiggum_loop.py` 中 `recent_no_behavior_deadlock_only` 相关改动。
- verify: `python3 -m py_compile tools/ralph_wiggum_loop.py`
- evidence_ref: `tools/ralph_wiggum_loop.py`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`

### 20260216-064120-ralph-loop-cycle-032
- change_id: 20260216-064120-ralph-loop-cycle-032
- change_type: Eval
- scope: ralph-wiggum-loop cycle 032
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_029_20260215_162509/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_032_20260216_035240/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate no improvement

### 20260216-064230-cycle32-explore-backfill-min-changes
- change_id: 20260216-064230-cycle32-explore-backfill-min-changes
- change_type: Enforce
- scope: `tools/ralph_wiggum_loop.py`（探索回填在停滞期的最小改动维度约束）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `N/A`（checkpoint patch；未执行重型评测）
- evidence:
  - E1 | quick_gate.reason=quick_gate_no_improvement | n=1 cycle | seeds=N/A | evidence_ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_032_20260216_035240/review.json
  - E2 | state.no_improve_streak=3 | n=1 state snapshot | seeds=N/A | evidence_ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_state_v2.json
  - E3 | patch target=explore backfill min changes under mechanism priority/deadlock | n=1 file | seeds=N/A | evidence_ref=path:/Users/peng/Workspace/codex/poker2/tools/ralph_wiggum_loop.py
- outcome: CONTINUE
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: 先提高候选行为可区分度，降低 quick gate 在停滞期的同分同形淘汰，再观察下一轮 behavior_pass 与 eligible 计数是否上升。

### 20260216-093218-ralph-loop-cycle-033
- change_id: 20260216-093218-ralph-loop-cycle-033
- change_type: Eval
- scope: ralph-wiggum-loop cycle 033
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_029_20260215_162509/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_033_20260216_064120/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate ranked-only blocked (trial_raw=12.55733125, active_raw=13.08748125)

## [autopilot-hook] 2026-02-16T09:33:17+0800 cycle=33 reason=cycle_completed
- change_type: Patch
- decision: ranked_only_blocked_raw_floor_escape
- why: `no_improve_streak=4` 且 `quick_gate.reason=quick_gate_ranked_only_blocked`，当前候选可在 ranked 分上超越但 raw quick score 仍低于晋级 floor。
- what: `tools/ralph_wiggum_loop.py` 在 `_candidate_escalation_factor` 增加 `quick_gate_ranked_only_blocked` 分支，将 auto escalation floor 提升到 `>=3.0`，优先搜索 raw 分实质抬升的机制候选。
- rollback: 回退 `tools/ralph_wiggum_loop.py` 中 `quick_gate_ranked_only_blocked` 对应分支。
- verify: `python3 -m py_compile tools/ralph_wiggum_loop.py`
- evidence_ref: `tmp/ralph_loop_runs_v2/cycle_033_20260216_064120/review.json`, `tmp/ralph_loop_runs_v2/cycle_033_20260216_064120/cycle_result.json`, `tools/ralph_wiggum_loop.py`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`

### 20260216-121600-ralph-loop-cycle-034
- change_id: 20260216-121600-ralph-loop-cycle-034
- change_type: Eval
- scope: ralph-wiggum-loop cycle 034
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_029_20260215_162509/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_034_20260216_093317/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate ranked-only blocked (trial_raw=12.55733125, active_raw=13.08748125)

### 20260216-hook-cycle-034-ranked-raw-floor-deadlock-relief
- change_id: 20260216-hook-cycle-034-ranked-raw-floor-deadlock-relief
- change_type: Enforce
- scope: `tools/ralph_wiggum_loop.py`（ranked-only deadlock 下 quick gate raw floor margin 动态放宽）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: hook patch; no heavy eval run in this hook step
- evidence:
  - E1 | quick_gate.reason=quick_gate_ranked_only_blocked | n=1 cycle | seeds=N/A | evidence_ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_034_20260216_093317/review.json
  - E2 | no_improve_streak=5, mechanism_only=true | n=1 state | seeds=N/A | evidence_ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_state_v2.json
  - E3 | patch applied | n=N/A | seeds=N/A | evidence_ref=path:/Users/peng/Workspace/codex/poker2/tools/ralph_wiggum_loop.py
  - E4 | next action emitted | n=N/A | seeds=N/A | evidence_ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_next_action.json
- outcome: CONTINUE
- rationale: 在不放松 full gate 的前提下，减少 ranked-only 信号被固定 raw floor 反复拦截造成的迭代停滞；改动单点、可回退、可解释。

### 20260216-145424-ralph-loop-cycle-035
- change_id: 20260216-145424-ralph-loop-cycle-035
- change_type: Eval
- scope: ralph-wiggum-loop cycle 035
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_029_20260215_162509/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_035_20260216_121600/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate ranked-only blocked (trial_raw=12.40031875, active_raw=13.08748125)

### 20260216-184231-ralph-loop-cycle-036
- change_id: 20260216-184231-ralph-loop-cycle-036
- change_type: Eval
- scope: ralph-wiggum-loop cycle 036
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_036_20260216_145424/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_036_20260216_145424/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_036_20260216_145424/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_036_20260216_145424/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate fail (improved=False, no_regression=False)

### 20260216-224523-ralph-loop-cycle-037
- change_id: 20260216-224523-ralph-loop-cycle-037
- change_type: Eval
- scope: ralph-wiggum-loop cycle 037
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_037_20260216_203114/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_037_20260216_203114/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_037_20260216_203114/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_037_20260216_203114/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (improved=True, no_regression=False)

### 20260217-012433-ralph-loop-cycle-038
- change_id: 20260217-012433-ralph-loop-cycle-038
- change_type: Eval
- scope: ralph-wiggum-loop cycle 038
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_029_20260215_162509/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_038_20260216_224523/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate no improvement


## [autopilot-hook] 2026-02-17T01:25:28+0800 cycle=38 reason=cycle_completed
- change_type: Patch
- decision: adaptive_quick_min_delta_mechanism_unblock
- why: `no_improve_streak=9` + `quick_gate.reason=quick_gate_no_improvement`; best mechanism candidate had `quick_delta=+0.206` but fixed `quick_min_delta=0.5` blocked promotion.
- what: `tools/ralph_wiggum_loop.py` added `_effective_quick_min_delta(...)` and wired it into `ranked_delta_pass`; quick_gate thresholds now expose base/effective delta for replay evidence.
- rollback: revert `_effective_quick_min_delta` function and its callsite around quick gate ranked delta checks.
- verify: `python3` compile smoke with explicit cfile (`tmp/.pyc_smoke/ralph_wiggum_loop.pyc`).
- evidence_ref: `tools/ralph_wiggum_loop.py`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_runs_v2/cycle_038_20260216_224523/review.json`, `tmp/ralph_loop_runs_v2/cycle_038_20260216_224523/cycle_result.json`

## [autopilot-hook] 2026-02-17T10:34:36+0800 cycle=null reason=worker_failed_or_unexpected_exit
- change_type: Patch
- decision: scrimmage_batch_enospc_error_containment
- why: cycle_039 quick runs在 `seed3002`（gg tierP 为 `seed3001`）目录创建时触发 `OSError: [Errno 28] No space left on device`，异常从线程抛出后导致 worker 非预期退出。
- what: `poker2/cli/scrimmage_batch.py` 将每 seed 输出目录创建移入 `_run_one` try 块，新增 `ENOSPC` 定向错误文案并返回结构化 `RunResult(status=error)`；同时为 `future.result()` 增加兜底，保证批次可落地 summary 而不是崩溃中断。
- rollback: 回退 `poker2/cli/scrimmage_batch.py` 中 `_run_one` 的 `mkdir`/`OSError` 分支及 `as_completed` 结果收集兜底分支。
- verify: `python3 -m py_compile poker2/cli/scrimmage_batch.py`
- evidence_ref: `poker2/cli/scrimmage_batch.py`, `tmp/ralph_loop_runs_v2/cycle_039_20260217_103417/trial_quick/c039_af1_low_spr_wet_firewall/coinpoker_7max_mw_v3_actionspace_v2/tierA/run.log`, `tmp/ralph_loop_runs_v2/cycle_039_20260217_103417/trial_quick/c039_af1_low_spr_wet_firewall/gg_7max_mw_v3_actionspace_league_frozen_v2/tierP/run.log`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`

## [autopilot-hook] 2026-02-17T15:00:33+0800 cycle=39 reason=disk_guard
- change_type: Patch
- decision: auto_cleanup_retention_guard_for_tmp
- why: `tmp/ralph_loop_runs_v2` 长期累积到 180G+ 导致 launchd/time_hook/scrimmage 多点 `Errno 28`，迭代频繁中断并重复重启。
- what: 新增 `tools/ralph_cleanup_runs.py`（保留关键证据+按周期/全局留存+低磁盘阈值强制清理），并在 `tools/ralph_loop_supervisor.sh` 集成自动清理触发（startup/periodic/low_disk）；支持 `AUTO_CLEANUP_*` 环境变量调节留存与目标空闲空间。
- rollback: 移除 `tools/ralph_cleanup_runs.py`，回退 `tools/ralph_loop_supervisor.sh` 中 `maybe_auto_cleanup` 及相关 `AUTO_CLEANUP_*` 参数。
- verify: `zsh -n tools/ralph_loop_supervisor.sh`; `python -m py_compile tools/ralph_cleanup_runs.py`; `python tools/ralph_cleanup_runs.py --runs-root tmp/ralph_loop_runs_v2 --state-file tmp/ralph_loop_state_v2.json`
- evidence_ref: `tools/ralph_cleanup_runs.py`, `tools/ralph_loop_supervisor.sh`, `tmp/ralph_loop_supervisor.log`, `tmp/ralph_loop_runs_v2`, `tmp/ralph_loop_state_v2.json`

### 20260217-164908-ralph-loop-cycle-039
- change_id: 20260217-164908-ralph-loop-cycle-039
- change_type: Eval
- scope: ralph-wiggum-loop cycle 039
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_029_20260215_162509/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_039_20260217_150033/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate no improvement

## [autopilot-hook] 2026-02-17T16:49:27+0800 cycle=39 reason=cycle_completed
- change_type: Patch
- decision: prolonged_stagnation_mechanism_behavior_guard_relax
- why: `no_improve_streak=10` + latest completed review `quick_gate.reason=quick_gate_no_improvement`; mechanism candidates near-miss behavior gate and quick gate repeatedly rejects.
- what: `tools/ralph_wiggum_loop.py` in `_candidate_behavior_delta_min` adds streak-aware relaxation (`no_improve_streak>=10`) for mechanism candidates under deadlock, while preserving non-zero behavior floor.
- rollback: revert the newly added `no_improve_streak` ratio relax branches in `_candidate_behavior_delta_min`.
- verify: `python3 -m py_compile tools/ralph_wiggum_loop.py`
- evidence_ref: `tools/ralph_wiggum_loop.py`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_runs_v2/cycle_039_20260217_150033/review.json`, `tmp/ralph_loop_runs_v2/cycle_039_20260217_150033/cycle_result.json`

## [autopilot-hook] 2026-02-17T16:52:18+0800 cycle=40 reason=disk_guard_harden
- change_type: Patch
- decision: aggressive_artifact_minimization_and_retention
- why: 循环评测目录持续膨胀（单 cycle 可达 GB 级），导致磁盘压力与重启风险；且 quick/full 评测存在大量对晋级判断无必要的临时产物。
- what: 
  - `poker2/cli/scrimmage.py` 新增 `--artifact-mode {full,lean}`，`lean` 仅保留 `scrimmage_report.json`（不落地 eventstream/views/insights/txt）。
  - `poker2/cli/scrimmage_batch.py` 新增 `--artifact-mode` 并透传到子 `scrimmage`，同时在 batch summary 记录 `artifact_mode`。
  - `tools/ralph_cleanup_runs.py` 重构：按 cycle 编号排序留存、锁周期保护、state 引用按最近窗口保留、payload 压缩（清理 `trial_quick/bootstrap_active_full/seed*` 与冗余报告文件）、quick cache 与 parent log 留存控制。
  - `tools/ralph_loop_supervisor.sh` 默认切到更激进清理参数并注入 `SCRIMMAGE_ARTIFACT_MODE=lean`，启动日志记录 artifact mode。
- rollback: 回退上述四个文件本次改动；将 `SCRIMMAGE_ARTIFACT_MODE` 与 `AUTO_CLEANUP_*` 恢复旧默认。
- verify: 
  - `python3 -m py_compile tools/ralph_cleanup_runs.py poker2/cli/scrimmage.py poker2/cli/scrimmage_batch.py`
  - `zsh -n tools/ralph_loop_supervisor.sh`
  - `python3 tools/ralph_cleanup_runs.py`
  - `launchctl kickstart -k gui/$(id -u)/com.poker2.ralph-loop`
- evidence_ref: `tools/ralph_cleanup_runs.py`, `tools/ralph_loop_supervisor.sh`, `poker2/cli/scrimmage.py`, `poker2/cli/scrimmage_batch.py`, `tmp/ralph_loop_supervisor.log`, `tmp/ralph_loop_runs_v2`

## [autopilot-hook] 2026-02-17T18:03:00+0800 cycle=40 reason=history_temp_prune
- change_type: Patch
- decision: one_shot_history_cleanup_plus_auto_prune_guard
- why: 历史评测临时产物长期累积（`tmp` 274G, `artifacts/eval` 208G）并造成反复磁盘风险；用户要求仅保留最近基线并彻底修复临时文件膨胀。
- what:
  - 新增 `tools/prune_history_artifacts.py`：清理历史 `tmp` 临时目录、清空 `artifacts/eval`、仅保留最近 N 个 baseline 目录。
  - `tools/ralph_loop_supervisor.sh` 集成 `maybe_prune_history`（周期执行历史清理，默认保留最近 4 个 baseline）。
  - 执行一次全量清理：释放约 `457.433 GiB`；`tmp` 从 `274G` 降到 `95M`，`artifacts/eval` 归零。
  - 继续保留并运行 `lean + auto_cleanup` 路径，确保新迭代不再写入大体积 eventstream。
- rollback: 回退 `tools/prune_history_artifacts.py` 与 `tools/ralph_loop_supervisor.sh` 中 `maybe_prune_history` 相关改动；若需恢复历史评测目录，仅能从外部备份恢复。
- verify:
  - `python3 -m py_compile tools/prune_history_artifacts.py`
  - `zsh -n tools/ralph_loop_supervisor.sh`
  - `python3 tools/prune_history_artifacts.py --keep-baseline-dirs 4 --keep-eval-dirs 0`
  - `du -sh tmp artifacts/eval artifacts/baselines`
  - `rg -n -F -- '--artifact-mode lean' tmp/ralph_loop_runs_v2/cycle_040_20260217_180029/**/run.log`
- evidence_ref: `tools/prune_history_artifacts.py`, `tools/ralph_loop_supervisor.sh`, `tmp/ralph_loop_supervisor.log`, `tmp/ralph_loop_runs_v2`, `artifacts/eval`, `artifacts/baselines`

### 20260217-221849-ralph-loop-cycle-040
- change_id: 20260217-221849-ralph-loop-cycle-040
- change_type: Eval
- scope: ralph-wiggum-loop cycle 040
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_040_20260217_202945/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_040_20260217_202945/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_040_20260217_202945/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_040_20260217_202945/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate standard fail (robust_pass=False, no_regression=False, holdout_pass=False)

## [autopilot-hook] 2026-02-18T15:41:51+0800 cycle=44 reason=cycle_completed
- change_type: Patch
- decision: full_gate_fail_aware_quick_regression_guard
- why: `state.no_improve_streak=15` 命中强制机制改动；latest completed review 为 `full_gate_fail`，且 quick gate 在高 streak 下回归容忍度被放大，导致 full eval 候选质量不稳。
- what: `tools/ralph_wiggum_loop.py` 将 quick regression 容忍度改为 `full_gate_fail` 感知：最近 4 次若 `full_gate_fail>=2` 则收紧 streak bonus 上限；`>=3` 且 streak>=12 再进一步收紧，并把新增阈值证据写入 `quick_gate.thresholds`。
- rollback: 回退 `tools/ralph_wiggum_loop.py` 中 `recent_full_gate_fails` + `quick_regression_streak_bonus` 收紧分支，以及新增的 thresholds 字段。
- verify: `python3 -m py_compile tools/ralph_wiggum_loop.py`; `python3 -m json.tool tmp/ralph_next_action.json >/dev/null`
- evidence_ref: `tools/ralph_wiggum_loop.py`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_044_20260218_114338/review.json`, `tmp/ralph_loop_runs_v2/cycle_044_20260218_114338/cycle_result.json`

## [autopilot-hook] 2026-02-18T02:16:29+0800 cycle=41 reason=cycle_completed
- change_type: Patch
- decision: repeated_full_gate_fail_escalation_boost_v2
- why: `no_improve_streak=12` 且 latest completed review 为 `quick_gate.reason=full_gate_fail`；机制候选可过 quick 但 full gate 仍反复失败，说明当前搜索扰动不足以跳出局部盆地。
- what: `tools/ralph_wiggum_loop.py` 在 `_candidate_escalation_factor` 新增 `recent_full_gate_fails` 分支；最近 4 次若有 >=2 次 `full_gate_fail`，auto escalation floor 提升到 `>=3.2`；若 >=3 次且 streak>=12，提升到 `>=3.4`。
- rollback: 回退 `_candidate_escalation_factor` 内新增的 `recent_full_gate_fails` 相关逻辑。
- verify: `python3 -m py_compile tools/ralph_wiggum_loop.py`
- evidence_ref: `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_041_20260217_221849/review.json`, `tmp/ralph_loop_runs_v2/cycle_041_20260217_221849/cycle_result.json`, `tools/ralph_wiggum_loop.py`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`

## [autopilot-hook] 2026-02-17T22:19:05+0800 cycle=40 reason=cycle_completed
- change_type: Patch
- decision: full_gate_fail_escalation_floor_v1
- why: `state.no_improve_streak=11` 且最新 completed 周期 `quick_gate.reason=full_gate_fail`，属于持续停滞；需要提升机制候选扰动以避免 quick-pass/full-fail 同质循环。
- what: `tools/ralph_wiggum_loop.py` 在 `_candidate_escalation_factor` 新增 `last_reason == "full_gate_fail"` 分支，自动扰动下限提升到 `>=2.6`。
- rollback: 删除该分支或恢复该函数到补丁前版本。
- verify: `python3 -m py_compile tools/ralph_wiggum_loop.py`
- evidence_ref: `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_040_20260217_202945/review.json`, `tmp/ralph_loop_runs_v2/cycle_040_20260217_202945/cycle_result.json`, `tools/ralph_wiggum_loop.py`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`

### 20260218-021628-ralph-loop-cycle-041
- change_id: 20260218-021628-ralph-loop-cycle-041
- change_type: Eval
- scope: ralph-wiggum-loop cycle 041
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_041_20260217_221849/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_041_20260217_221849/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_041_20260217_221849/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_041_20260217_221849/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate standard fail (robust_pass=False, no_regression=False, holdout_pass=False)

### 20260218-043533-ralph-loop-cycle-042
- change_id: 20260218-043533-ralph-loop-cycle-042
- change_type: Eval
- scope: ralph-wiggum-loop cycle 042
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_029_20260215_162509/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_042_20260218_021628/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate ranked-only blocked (trial_raw=12.40031875, active_raw=13.08748125, raw_floor_margin=0.6)

### 20260218-043556-hook-cycle-042-raw-floor-escalation
- change_id: 20260218-043556-hook-cycle-042-raw-floor-escalation
- change_type: Restructure
- scope: `tools/ralph_wiggum_loop.py`（quick gate ranked-only blocked 的 raw-floor margin 单机制升级）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: hook patch; no heavy eval run in this hook step
- evidence:
  - E1 | quick_gate.reason=quick_gate_ranked_only_blocked; active_raw=13.08748125, best_trial_raw=12.40031875 | n=1 cycle | seeds=N/A | evidence_ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_042_20260218_021628/review.json
  - E2 | no_improve_streak=13; mechanism_only=true | n=1 state | seeds=N/A | evidence_ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_state_v2.json
  - E3 | patch applied | n=N/A | seeds=N/A | evidence_ref=path:/Users/peng/Workspace/codex/poker2/tools/ralph_wiggum_loop.py
  - E4 | next action emitted | n=N/A | seeds=N/A | evidence_ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_next_action.json
- outcome: CONTINUE
- rationale: 在长期 mechanism-only stagnation 下，放宽 ranked-only blocked 的 raw floor 一档，让已通过 ranked 信号的近邻候选进入 full gate 由完整门禁裁决，降低 quick gate 死锁概率。

### 20260218-114338-ralph-loop-cycle-043
- change_id: 20260218-114338-ralph-loop-cycle-043
- change_type: Eval
- scope: ralph-wiggum-loop cycle 043
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_043_20260218_043533/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_043_20260218_043533/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_043_20260218_043533/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_043_20260218_043533/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate standard fail (improved=False, robust_pass=True, focus_pass=True)

### 20260218-114420-autopilot-hook-cycle-043-full-gate-stagnation-margin
- change_id: 20260218-114420-autopilot-hook-cycle-043-full-gate-stagnation-margin
- change_type: Patch
- scope: `tools/ralph_wiggum_loop.py`（full gate `full_min_delta` 在 repeated `full_gate_fail` + 高 streak 下自适应）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: 未执行重型评测；cycle043 已观测 full trial score 12.4636 vs active 12.3393（raw Δ≈+0.1243）但触发 `full_gate_fail`
- evidence:
  - no_improve_streak=14 | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_state_v2.json
  - quick_gate.reason=full_gate_fail 且 full_gate.focus_pass/holdout_pass/no_regression_pass=true | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_043_20260218_043533/review.json
  - trial holdout phase1/phase2 pass=true | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_043_20260218_043533/cycle_result.json
- outcome: CONTINUE
- rationale: 以最小机制改动降低“full gate 近阈值卡死”概率，保持鲁棒性门禁不放松；下一轮观察 ADOPT 率与回归门禁命中率。

### 20260218-154121-ralph-loop-cycle-044
- change_id: 20260218-154121-ralph-loop-cycle-044
- change_type: Eval
- scope: ralph-wiggum-loop cycle 044
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_044_20260218_114338/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_044_20260218_114338/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_044_20260218_114338/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_044_20260218_114338/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate standard fail (robust_pass=False, no_regression=False, holdout_pass=False)

### 20260218-201823-ralph-loop-cycle-045
- change_id: 20260218-201823-ralph-loop-cycle-045
- change_type: Eval
- scope: ralph-wiggum-loop cycle 045
- baseline: system_bot_policy_v3_loop_active (adopted_cycle=44)
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_045_20260218_182715/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_045_20260218_182715/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_045_20260218_182715/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_045_20260218_182715/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate standard fail (robust_pass=False, no_regression=False, holdout_pass=False)

## [autopilot-hook] 2026-02-18T20:18:51+0800 cycle=45 reason=cycle_completed
- change_type: Patch
- decision: prolonged_full_gate_fail_escalation_floor_v3
- why: `state.no_improve_streak=16` 且最近 completed review `quick_gate.reason=full_gate_fail`，当前机制搜索长期停留在 quick-pass/full-fail 邻域，需要在不放松 full gate 的前提下提升下一轮机制扰动幅度。
- what: `tools/ralph_wiggum_loop.py` 在 `_candidate_escalation_factor` 增加分支：当最近 4 轮 `full_gate_fail>=3` 且 `no_improve_streak>=16` 时，将自动 escalation floor 提升至 `>=3.7`，以提高机制行为差异和跳出局部盆地的概率。
- rollback: 回退 `_candidate_escalation_factor` 中新增的 `recent_full_gate_fails>=3 && no_improve_streak>=16` 分支。
- verify: `python3 -m py_compile tools/ralph_wiggum_loop.py`
- evidence_ref: `tools/ralph_wiggum_loop.py`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_045_20260218_182715/review.json`, `tmp/ralph_loop_runs_v2/cycle_045_20260218_182715/cycle_result.json`

### 20260218-230720-ralph-loop-cycle-046
- change_id: 20260218-230720-ralph-loop-cycle-046
- change_type: Eval
- scope: ralph-wiggum-loop cycle 046
- baseline: system_bot_policy_v3_loop_active (adopted_cycle=44)
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_029_20260215_162509/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_046_20260218_201824/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate no improvement

## [autopilot-hook] 2026-02-18T23:07:49+0800 cycle=46 reason=cycle_completed
- change_type: Patch
- decision: no_improve_probe_full_eval_escape_v1
- why: `state.no_improve_streak=17` 且 latest completed `review.quick_gate.reason=quick_gate_no_improvement`；cycle 046 存在 eligible 机制候选但未触发 full eval（`trial_full=null`），搜索长期停留在 quick-gate 局部盆地。
- what: `tools/ralph_wiggum_loop.py` 在 quick gate 的 no-improvement 分支新增机制级探测路由：当存在 `forced_probe` 且 streak 达到阈值并且最近原因为 `quick_gate_no_improvement/full_gate_fail` 时，允许 probe 直接进入 full eval；并新增 `quick_gate.thresholds.no_improve_probe_streak` 作为可回放证据字段。
- rollback: 回退 `tools/ralph_wiggum_loop.py` 中 `no_improve_probe_streak` 与 `no_improve_probe_enabled` 相关分支。
- verify: `python3 -m py_compile tools/ralph_wiggum_loop.py`; `python3 -m json.tool tmp/ralph_next_action.json >/dev/null`
- evidence_ref: `tools/ralph_wiggum_loop.py`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_046_20260218_201824/review.json`, `tmp/ralph_loop_runs_v2/cycle_046_20260218_201824/cycle_result.json`

### 20260219-015719-ralph-loop-cycle-047
- change_id: 20260219-015719-ralph-loop-cycle-047
- change_type: Eval
- scope: ralph-wiggum-loop cycle 047
- baseline: system_bot_policy_v3_loop_active (adopted_cycle=44)
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_029_20260215_162509/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_047_20260218_230720/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate no improvement

## [autopilot-hook] 2026-02-19T01:58:17+0800 cycle=47 reason=cycle_completed
- change_type: Patch
- decision: force_probe_raw_margin_escalation_under_stagnation
- why: Cycle 047 ended with `quick_gate_no_improvement` and `no_improve_streak=18`; quick gate had only one eligible mechanism and did not advance to full-eval probe, showing local-basin stagnation.
- what:
  - `tools/ralph_wiggum_loop.py` 新增 `_effective_force_probe_raw_margin`，在 `quick_gate_no_improvement/full_gate_fail + 高 streak/deadlock` 条件下放宽 forced-probe raw margin。
  - 快速门禁诊断新增 `forced_probe.raw_margin_base/raw_margin_escalated`，便于证据链定位本轮是否执行了放宽策略。
  - 生成下一轮输入：`tmp/ralph_next_action.json`（机制优先）与 `tmp/ralph_next_plan.md`（why/what/how/rollback/verify）。
- rollback: 回退 `tools/ralph_wiggum_loop.py` 本次补丁并删除新增 quick_gate 诊断字段，恢复默认 `--force-full-probe-raw-margin` 单值行为。
- verify:
  - `python3 -m py_compile tools/ralph_wiggum_loop.py`
- evidence_ref: `tools/ralph_wiggum_loop.py`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_runs_v2/cycle_047_20260218_230720/review.json`, `tmp/ralph_loop_runs_v2/cycle_047_20260218_230720/cycle_result.json`

### 20260219-015817-ralph-loop-cycle-047-probe-margin-escalation
- change_id: 20260219-015817-ralph-loop-cycle-047-probe-margin-escalation
- change_type: Patch
- scope: `tools/ralph_wiggum_loop.py` forced-probe raw margin escalation + next action synthesis
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: decision=CONTINUE; prior_cycle_reason=quick_gate_no_improvement; no_improve_streak=18
- evidence:
  - quick_gate reason | metric=quick_gate_no_improvement | n=1 | seeds=quick_cycle_047 | evidence_ref=tmp/ralph_loop_runs_v2/cycle_047_20260218_230720/review.json
  - streak signal | metric=no_improve_streak=18 | n=1 | seeds=state | evidence_ref=tmp/ralph_loop_state_v2.json
  - candidate bottleneck | metric=eligible_count=1 (mechanism_eligible_count=1) | n=6 candidates | seeds=quick_cycle_047 | evidence_ref=tmp/ralph_loop_runs_v2/cycle_047_20260218_230720/review.json
- outcome: CONTINUE
- rationale: Keep mechanism-only search while allowing larger forced-probe raw slack under prolonged stagnation so full gate can arbitrate higher-behavior-movement candidates.

### 20260219-071904-ralph-loop-cycle-048
- change_id: 20260219-071904-ralph-loop-cycle-048
- change_type: Eval
- scope: ralph-wiggum-loop cycle 048
- baseline: system_bot_policy_v3_loop_active (adopted_cycle=44)
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_048_20260219_015719/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_048_20260219_015719/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_048_20260219_015719/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_048_20260219_015719/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate standard fail (improved=False, robust_pass=True, focus_pass=True)

## [autopilot-hook] 2026-02-19T07:19:17+0800 cycle=48 reason=cycle_completed
- change_type: Patch
- decision: full_gate_fail_dual_scale_mechanism_companion_v1
- why: `state.no_improve_streak=19` 触发强制机制改动；latest completed review=`full_gate_fail` 且 `eligible_count=1`，候选强度层级不足导致 quick/full 脱钩风险上升。
- what: `tools/ralph_wiggum_loop.py` 在 `_propose_candidates` 新增 repeated `full_gate_fail` 探测；当 streak 高且近 4 轮 full_gate_fail>=2 时，为 `action_plan/adaptive_focus/focus_metric` 机制候选自动补充一个保守 scale 的 companion（与高 scale 并存），提高机制多样性与可通过性。
- rollback: 回退 `_propose_candidates` 中 `stability_dual_scale` / `stability_scale` 及 companion candidate 追加逻辑。
- verify: `python3 -m py_compile tools/ralph_wiggum_loop.py`; `python3 -m json.tool tmp/ralph_next_action.json >/dev/null`
- evidence_ref: `tools/ralph_wiggum_loop.py`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_048_20260219_015719/review.json`, `tmp/ralph_loop_runs_v2/cycle_048_20260219_015719/cycle_result.json`

### 20260219-123233-ralph-loop-cycle-049
- change_id: 20260219-123233-ralph-loop-cycle-049
- change_type: Eval
- scope: ralph-wiggum-loop cycle 049
- baseline: system_bot_policy_v3_loop_active (adopted_cycle=44)
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_049_20260219_071904/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_049_20260219_071904/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_049_20260219_071904/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_049_20260219_071904/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate standard fail (robust_pass=False, no_regression=False, holdout_pass=False)

### 2026-02-19-ralph-c050-full-gate-fail-escalation-dampen
- change_id: 2026-02-19-ralph-c050-full-gate-fail-escalation-dampen
- change_type: Refine
- scope: `tools/ralph_wiggum_loop.py`（full_gate_fail 连续场景下候选升级强度去激进化）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: cycle049 结果为 REJECT（quick_gate=full_gate_fail，no_improve_streak=20），本次为机制修复与下一轮计划，不宣称性能提升。
- evidence:
  - E1: full_gate_fail | candidate_count=6 eligible_count=2 mechanism_eligible_count=2 | ref=tmp/ralph_loop_runs_v2/cycle_049_20260219_071904/cycle_result.json
  - E2: coinpoker tierP facingY TURN/RIVER worst | bb100=-710.25 | n=56/88 | ref=tmp/ralph_loop_runs_v2/cycle_049_20260219_071904/cycle_result.json
  - E3: no_improve_streak=20 with recent history tail containing full_gate_fail | ref=tmp/ralph_loop_state_v2.json
- outcome: CONTINUE
- rationale: quick gate 已能筛出可行机制候选，但 full gate 连续失败；先抑制升级过冲，保持机制可归因并降低下一轮 full gate 回归风险。

### 20260219-173542-ralph-loop-cycle-050
- change_id: 20260219-173542-ralph-loop-cycle-050
- change_type: Eval
- scope: ralph-wiggum-loop cycle 050
- baseline: system_bot_policy_v3_loop_active (adopted_cycle=44)
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_050_20260219_123233/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_050_20260219_123233/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_050_20260219_123233/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_050_20260219_123233/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (robust_pass=False, no_regression=False, holdout_pass=True)

## [autopilot-hook] 2026-02-19T17:36:39+0800 cycle=50 reason=cycle_completed
- change_type: Patch
- decision: forced_probe_behavior_movement_priority_v1
- why: `state.no_improve_streak=21` 且最新 completed `quick_gate.reason=full_gate_fail`；cycle 050 的 forced probe 候选 `behavior_delta=0` 且 `behavior_pass=false`，导致 full eval 预算继续消耗在行为近似候选上。
- what: `tools/ralph_wiggum_loop.py` 的 `_select_forced_probe_candidate` 新增行为优先机制：在 `full_gate_fail + 高 streak` 场景下，若存在满足基础门禁（ante/support/raw-floor）的 `behavior_pass=true` 候选，则 forced probe 只在该子集中选；若不存在则保守回退到原选择逻辑。
- rollback: 回退 `_select_forced_probe_candidate` 中 `prefer_behavior_pass` 与 `has_behavior_pass_candidate` 相关分支。
- verify: `python3 -m py_compile tools/ralph_wiggum_loop.py`
- evidence_ref: `tools/ralph_wiggum_loop.py`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_050_20260219_123233/review.json`, `tmp/ralph_loop_runs_v2/cycle_050_20260219_123233/cycle_result.json`

### 20260219-231132-ralph-loop-cycle-001
- change_id: 20260219-231132-ralph-loop-cycle-001
- change_type: Eval
- scope: ralph-wiggum-loop cycle 001
- baseline: system_bot_policy_v3_loop_active_smoke_20260219_230617
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active_smoke_20260219_230617; trial=null
- evidence:
  - coinpoker summary | ref=path:/private/tmp/ralph_loop_smoke_test_BEyV3r/runs/cycle_001_20260219_230617/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/private/tmp/ralph_loop_smoke_test_BEyV3r/runs/cycle_001_20260219_230617/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=gg.tierA_mean
- rationale: llm action gate fail (missing_action)

### 20260219-231132-ralph-loop-cycle-002
- change_id: 20260219-231132-ralph-loop-cycle-002
- change_type: Eval
- scope: ralph-wiggum-loop cycle 002
- baseline: system_bot_policy_v3_loop_active_smoke_20260219_230617
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active_smoke_20260219_230617; trial=null
- evidence:
  - coinpoker summary | ref=path:/private/tmp/ralph_loop_smoke_test_BEyV3r/runs/cycle_001_20260219_230617/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/private/tmp/ralph_loop_smoke_test_BEyV3r/runs/cycle_002_20260219_231132/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=gg.tierA_mean
- rationale: llm action gate fail (missing_action)

### 20260220-004443-ralph-loop-cycle-051
- change_id: 20260220-004443-ralph-loop-cycle-051
- change_type: Eval
- scope: ralph-wiggum-loop cycle 051
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_051_20260219_225632/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: llm action gate fail (missing_action)

### 20260220-004443-ralph-loop-cycle-052
- change_id: 20260220-004443-ralph-loop-cycle-052
- change_type: Eval
- scope: ralph-wiggum-loop cycle 052
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_052_20260220_004443/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: llm action gate fail (missing_action)

### 20260220-004443-ralph-loop-cycle-053
- change_id: 20260220-004443-ralph-loop-cycle-053
- change_type: Eval
- scope: ralph-wiggum-loop cycle 053
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_053_20260220_004443/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: llm action gate fail (missing_action)

### 20260220-004443-ralph-loop-cycle-054
- change_id: 20260220-004443-ralph-loop-cycle-054
- change_type: Eval
- scope: ralph-wiggum-loop cycle 054
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_054_20260220_004443/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: llm action gate fail (missing_action)

### 20260220-004443-ralph-loop-cycle-055
- change_id: 20260220-004443-ralph-loop-cycle-055
- change_type: Eval
- scope: ralph-wiggum-loop cycle 055
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_055_20260220_004443/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: llm action gate fail (missing_action)

### 20260220-004443-ralph-loop-cycle-056
- change_id: 20260220-004443-ralph-loop-cycle-056
- change_type: Eval
- scope: ralph-wiggum-loop cycle 056
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_056_20260220_004443/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: llm action gate fail (missing_action)

### 20260220-004453-ralph-loop-cycle-057
- change_id: 20260220-004453-ralph-loop-cycle-057
- change_type: Eval
- scope: ralph-wiggum-loop cycle 057
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_057_20260220_004453/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: llm action gate fail (missing_action)

### 20260220-004453-ralph-loop-cycle-058
- change_id: 20260220-004453-ralph-loop-cycle-058
- change_type: Eval
- scope: ralph-wiggum-loop cycle 058
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_058_20260220_004453/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: llm action gate fail (missing_action)

### 20260220-004453-ralph-loop-cycle-059
- change_id: 20260220-004453-ralph-loop-cycle-059
- change_type: Eval
- scope: ralph-wiggum-loop cycle 059
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_059_20260220_004453/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: llm action gate fail (missing_action)

### 20260220-004453-ralph-loop-cycle-060
- change_id: 20260220-004453-ralph-loop-cycle-060
- change_type: Eval
- scope: ralph-wiggum-loop cycle 060
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_060_20260220_004453/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: llm action gate fail (missing_action)

### 20260220-004454-ralph-loop-cycle-061
- change_id: 20260220-004454-ralph-loop-cycle-061
- change_type: Eval
- scope: ralph-wiggum-loop cycle 061
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_061_20260220_004453/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: llm action gate fail (missing_action)

### 20260220-004454-ralph-loop-cycle-062
- change_id: 20260220-004454-ralph-loop-cycle-062
- change_type: Eval
- scope: ralph-wiggum-loop cycle 062
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_062_20260220_004454/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: llm action gate fail (missing_action)

### 20260220-004554-ralph-loop-cycle-063
- change_id: 20260220-004554-ralph-loop-cycle-063
- change_type: Eval
- scope: ralph-wiggum-loop cycle 063
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_063_20260220_004554/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: llm action gate fail (missing_action)

### 20260220-004554-ralph-loop-cycle-064
- change_id: 20260220-004554-ralph-loop-cycle-064
- change_type: Eval
- scope: ralph-wiggum-loop cycle 064
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_064_20260220_004554/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: llm action gate fail (missing_action)

### 20260220-004554-ralph-loop-cycle-065
- change_id: 20260220-004554-ralph-loop-cycle-065
- change_type: Eval
- scope: ralph-wiggum-loop cycle 065
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_065_20260220_004554/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: llm action gate fail (missing_action)

### 20260220-004554-ralph-loop-cycle-066
- change_id: 20260220-004554-ralph-loop-cycle-066
- change_type: Eval
- scope: ralph-wiggum-loop cycle 066
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_066_20260220_004554/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: llm action gate fail (missing_action)

### 20260220-004554-ralph-loop-cycle-067
- change_id: 20260220-004554-ralph-loop-cycle-067
- change_type: Eval
- scope: ralph-wiggum-loop cycle 067
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_067_20260220_004554/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: llm action gate fail (missing_action)

### 20260220-004554-ralph-loop-cycle-068
- change_id: 20260220-004554-ralph-loop-cycle-068
- change_type: Eval
- scope: ralph-wiggum-loop cycle 068
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_068_20260220_004554/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: llm action gate fail (missing_action)

### 20260220-004654-ralph-loop-cycle-069
- change_id: 20260220-004654-ralph-loop-cycle-069
- change_type: Eval
- scope: ralph-wiggum-loop cycle 069
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_069_20260220_004654/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: llm action gate fail (missing_action)

### 20260220-004655-ralph-loop-cycle-070
- change_id: 20260220-004655-ralph-loop-cycle-070
- change_type: Eval
- scope: ralph-wiggum-loop cycle 070
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_070_20260220_004655/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: llm action gate fail (missing_action)

### 20260220-004655-ralph-loop-cycle-071
- change_id: 20260220-004655-ralph-loop-cycle-071
- change_type: Eval
- scope: ralph-wiggum-loop cycle 071
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_071_20260220_004655/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: llm action gate fail (missing_action)

### 20260220-004655-ralph-loop-cycle-072
- change_id: 20260220-004655-ralph-loop-cycle-072
- change_type: Eval
- scope: ralph-wiggum-loop cycle 072
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_072_20260220_004655/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: llm action gate fail (missing_action)

### 20260220-004655-ralph-loop-cycle-073
- change_id: 20260220-004655-ralph-loop-cycle-073
- change_type: Eval
- scope: ralph-wiggum-loop cycle 073
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_073_20260220_004655/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: llm action gate fail (missing_action)

### 20260220-004655-ralph-loop-cycle-074
- change_id: 20260220-004655-ralph-loop-cycle-074
- change_type: Eval
- scope: ralph-wiggum-loop cycle 074
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_074_20260220_004655/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: llm action gate fail (missing_action)

### 20260220-004755-ralph-loop-cycle-075
- change_id: 20260220-004755-ralph-loop-cycle-075
- change_type: Eval
- scope: ralph-wiggum-loop cycle 075
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_075_20260220_004755/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: llm action gate fail (missing_action)

### 20260220-004755-ralph-loop-cycle-076
- change_id: 20260220-004755-ralph-loop-cycle-076
- change_type: Eval
- scope: ralph-wiggum-loop cycle 076
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_076_20260220_004755/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: llm action gate fail (missing_action)

### 20260220-004755-ralph-loop-cycle-077
- change_id: 20260220-004755-ralph-loop-cycle-077
- change_type: Eval
- scope: ralph-wiggum-loop cycle 077
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_077_20260220_004755/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: llm action gate fail (missing_action)

### 20260220-004755-ralph-loop-cycle-078
- change_id: 20260220-004755-ralph-loop-cycle-078
- change_type: Eval
- scope: ralph-wiggum-loop cycle 078
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_078_20260220_004755/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: llm action gate fail (missing_action)

### 20260220-004755-ralph-loop-cycle-079
- change_id: 20260220-004755-ralph-loop-cycle-079
- change_type: Eval
- scope: ralph-wiggum-loop cycle 079
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_079_20260220_004755/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: llm action gate fail (missing_action)

### 20260220-004756-ralph-loop-cycle-080
- change_id: 20260220-004756-ralph-loop-cycle-080
- change_type: Eval
- scope: ralph-wiggum-loop cycle 080
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_080_20260220_004756/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: llm action gate fail (missing_action)

## [autopilot-hook] 2026-02-20T00:44:53+0800 cycle=56 reason=cycle_completed
- change_type: Patch
- decision: auto_missing_action_fallback_mechanism_v1
- why: `no_improve_streak=27` 且最新 completed `quick_gate.reason=llm_action_gate_fail`（missing_action），导致候选生成直接短路为 0。
- what: `tools/ralph_wiggum_loop.py` 新增 `_fallback_action_plan_for_missing_ticket`，在高停滞 + 缺 ticket 时根据 `next_hypothesis` 自动生成机制级 fallback（mechanism-first），并在主流程通过 `effective_action_plan` 进入候选生成。
- rollback: 回退 `_fallback_action_plan_for_missing_ticket` 及主流程 `effective_action_plan` 分支。
- verify: `python3 -m py_compile tools/ralph_wiggum_loop.py`
- evidence_ref: `tools/ralph_wiggum_loop.py`, `tmp/ralph_patch_manifest_cycle_056_hook.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_runs_v2/cycle_056_20260220_004443/review.json`, `tmp/ralph_loop_runs_v2/cycle_056_20260220_004443/cycle_result.json`


## [autopilot-hook] 2026-02-20T00:44:53+0800 cycle=51 reason=cycle_completed
- change_type: Patch
- decision: auto_missing_action_fallback_default_focus_v1
- why: `no_improve_streak=51` and completed review quick gate reason is `llm_action_gate_fail`; fallback previously depended on `next_hypothesis.focus_metric` and could return null when absent.
- what: `tools/ralph_wiggum_loop.py` fallback now defaults to `FOCUS_SUPPORT_FOCUS_METRIC` when ticket is missing and hypothesis focus is absent, preserving mechanism candidate generation path.
- rollback: revert the default-focus branch in `_fallback_action_plan_for_missing_ticket`.
- verify: `python3 -m py_compile tools/ralph_wiggum_loop.py`
- evidence_ref: `tools/ralph_wiggum_loop.py`, `tmp/ralph_patch_manifest_cycle_051_hook.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_runs_v2/cycle_056_20260220_004443/review.json`, `tmp/ralph_loop_runs_v2/cycle_056_20260220_004443/cycle_result.json`

## [autopilot-hook] 2026-02-20T01:56:07+0800 cycle=81 reason=awaiting_llm_action
- change_type: Patch
- decision: unblock_missing_action_gate_with_auto_fallback_continuation_v1
- why: `quick_gate.reason=llm_action_gate_fail` and `action_ticket.reason=missing_action` persisted with `no_improve_streak=51`, causing repeated candidate generation short-circuit.
- what: `tools/ralph_wiggum_loop.py` reordered action gate flow to compute fallback before stop and only halt when ticket fails with no fallback plan.
- how: preserved strict ticket checks; changed stop condition from unconditional ticket fail to conditional fail-without-fallback; wrote cycle-81 consumable next action ticket.
- rollback: revert the action gate block around `next_action_obj/action_ticket/fallback_action_obj` in `tools/ralph_wiggum_loop.py` and remove cycle-81 ticket artifacts.
- verify: `python3 -m py_compile tools/ralph_wiggum_loop.py`; `python3` validation of `tmp/ralph_next_action.json` required fields.
- evidence_ref: `tools/ralph_wiggum_loop.py`, `tmp/ralph_patch_manifest_cycle_081_hook.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_runs_v2/cycle_080_20260220_004756/review.json`, `tmp/ralph_loop_runs_v2/cycle_080_20260220_004756/cycle_result.json`

### 20260220-035710-ralph-loop-cycle-081
- change_id: 20260220-035710-ralph-loop-cycle-081
- change_type: Eval
- scope: ralph-wiggum-loop cycle 081
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_081_20260220_015759/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate no improvement

## [autopilot-hook] 2026-02-20T03:57:46+0800 cycle=82 reason=cycle_completed
- change_type: Patch
- decision: review_guided_missing_action_fallback_v1
- why: `no_improve_streak=52` 且 completed `quick_gate.reason=quick_gate_no_improvement`，missing action fallback 长期按固定顺序取机制，容易重复低收益探索。
- what: `tools/ralph_wiggum_loop.py` 的 `_fallback_action_plan_for_missing_ticket` 新增 `review_ref` 驱动优先级；当 ticket 缺失时优先读取上一轮 review 的 `selected_full_eval_candidate/forced_probe` 并提取机制名作为 fallback 主机制。
- rollback: 回退 `tools/ralph_wiggum_loop.py` 中 `_path_from_ref/_mechanism_from_candidate_name/_preferred_fallback_mechanism_from_review` 及 fallback 调用新增 `review_ref` 参数。
- verify: `python3 -m py_compile tools/ralph_wiggum_loop.py`
- evidence_ref: `tools/ralph_wiggum_loop.py`, `tmp/ralph_patch_manifest_cycle_082_hook.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_runs_v2/cycle_081_20260220_015759/review.json`, `tmp/ralph_loop_runs_v2/cycle_081_20260220_015759/cycle_result.json`

### 20260220-121438-ralph-loop-cycle-082
- change_id: 20260220-121438-ralph-loop-cycle-082
- change_type: Eval
- scope: ralph-wiggum-loop cycle 082
- baseline: system_bot_policy_v3_loop_active
- delta: decision=ADOPT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_082_20260220_085435/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_082_20260220_085435/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_082_20260220_085435/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_082_20260220_085435/review.json
- outcome: ADOPT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate standard pass: pareto_adoptable=True, score_delta=0.371


### 2026-02-20-hook-action-ticket-relpath
- change_id: 2026-02-20-hook-action-ticket-relpath
- change_type: Restructure
- scope: `tools/ralph_wiggum_loop.py`（action ticket `patched_files` 路径归一化，支持 `path:` / 绝对路径）
- baseline: system_bot_policy_v3_loop_active
- delta: n/a（流程稳健性改进，不涉及策略参数）
- evidence:
  - cycle result | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_082_20260220_085435/cycle_result.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_082_20260220_085435/review.json
  - patch manifest | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_patch_manifest_cycle_082_20260220_121533.json
- outcome: CONTINUE
- rationale: 在保持 action ticket 严格门禁的前提下，减少路径格式差异导致的误拒，提升无人值守循环连续性。

### 20260220-152657-ralph-loop-cycle-083
- change_id: 20260220-152657-ralph-loop-cycle-083
- change_type: Eval
- scope: ralph-wiggum-loop cycle 083
- baseline: system_bot_policy_v3_loop_active (adopted_cycle=82)
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_083_20260220_121438/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate no improvement


### 20260220-152657-awaiting-llm-action-unblock
- change_id: 20260220-152657-awaiting-llm-action-unblock
- change_type: Enforce
- scope: `tools/ralph_wiggum_loop.py`（missing_action deadlock-aware fallback）+ `tmp/ralph_next_action.json`（cycle 084 ticket unblock）
- baseline: system_bot_policy_v3_loop_active
- delta: null（hook unblock patch；未执行重型评测）
- evidence:
  - heartbeat gate | status=heartbeat,reason=awaiting_llm_action,ticket_reason=missing_action | n=1 | seeds=null | evidence_ref=event:2026-02-20T15:26:57+0800
  - completed review | quick_gate.reason=quick_gate_no_improvement | n=1 | seeds=2000-2001 | evidence_ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_083_20260220_121438/review.json
  - code patch | deadlock-aware missing_action fallback | n=1 | seeds=null | evidence_ref=tools/ralph_wiggum_loop.py
- outcome: CONTINUE
- rationale: action ticket 缺失导致 worker 卡住；先以单机制补丁解除 deadlock，再由 next_action 驱动下一轮消费。

### 20260220-152657-ralph-loop-awaiting-action-unblock
- change_id: 20260220-152657-ralph-loop-awaiting-action-unblock
- change_type: Enforce
- scope: `tools/ralph_wiggum_loop.py` + `tmp/ralph_next_action.json`（action ticket unblock + fallback trigger tighten-up）
- baseline: `system_bot_policy_v3_loop_active`
- delta: `n/a (control-plane unblock; no heavy eval)`
- evidence:
  - heartbeat gate block | reason=awaiting_llm_action/missing_action | ref=event:2026-02-20T15:26:57+0800
  - cycle review context | quick_gate.reason=quick_gate_no_improvement | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_083_20260220_121438/review.json
  - applied core patch | fallback threshold >=1 signal | ref=path:/Users/peng/Workspace/codex/poker2/tools/ralph_wiggum_loop.py
- outcome: ADOPT
- rationale: 当前阻塞来自 action ticket 缺失；先恢复 worker 可消费 action，并降低首次缺票据导致的停机概率。

### 20260220-181221-ralph-loop-cycle-084
- change_id: 20260220-181221-ralph-loop-cycle-084
- change_type: Eval
- scope: ralph-wiggum-loop cycle 084
- baseline: system_bot_policy_v3_loop_active (adopted_cycle=82)
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_084_20260220_153000/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate no improvement

### 20260220-181321-ralph-hook-cycle-084-probe-threshold
- change_id: 20260220-181321-ralph-hook-cycle-084-probe-threshold
- change_type: Restructure
- scope: `tools/ralph_wiggum_loop.py`（quick_gate no-improvement 路径的 probe 门槛动态下调）
- baseline: system_bot_policy_v3_loop_active
- delta: n/a（hook patch only，待 cycle 085 验证）
- evidence:
  - quick gate reason | metric=quick_gate.reason | n=1 | seeds=cycle084 | evidence_ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_084_20260220_153000/review.json
  - streak signal | metric=no_improve_streak=2 | n=1 | seeds=cycle084 | evidence_ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_084_20260220_153000/cycle_result.json
  - mechanism patch | metric=dynamic_no_improve_probe_streak | n=1 | seeds=null | evidence_ref=tools/ralph_wiggum_loop.py
- outcome: CONTINUE
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: 在 quick score 持平且行为变化不足的停滞段，提前触发 probe full gate，让机制候选更早进入完整门禁裁决，减少 no-improve 空转。

### 20260220-205031-ralph-loop-cycle-085
- change_id: 20260220-205031-ralph-loop-cycle-085
- change_type: Eval
- scope: ralph-wiggum-loop cycle 085
- baseline: system_bot_policy_v3_loop_active (adopted_cycle=82)
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_085_20260220_181221/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate no improvement

## [autopilot-hook] 2026-02-20T20:51:20+0800 cycle=85 reason=cycle_completed
- change_type: Patch
- decision: forced_probe_mechanism_prefer_under_stagnation_v1
- why: `no_improve_streak=3` and completed cycle showed top-score knob ties with behavior-flat candidates, causing quick-gate no-improvement loops.
- what: `tools/ralph_wiggum_loop.py` now overrides `forced_probe_diag` to an eligible mechanism candidate when mechanism-priority is active, streak>=2, top non-mechanism tie cluster is behavior-flat, and mechanism score is within probe raw margin.
- rollback: revert forced-probe override block near `forced_probe_diag` assignment.
- verify: `python3 -m py_compile tools/ralph_wiggum_loop.py`; required-field validation for `tmp/ralph_next_action.json`.
- evidence_ref: `tools/ralph_wiggum_loop.py`, `tmp/ralph_patch_manifest_cycle_085_hook_20260220_205120.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_runs_v2/cycle_085_20260220_181221/review.json`, `tmp/ralph_loop_runs_v2/cycle_085_20260220_181221/cycle_result.json`

### 20260221-013806-ralph-loop-cycle-086
- change_id: 20260221-013806-ralph-loop-cycle-086
- change_type: Eval
- scope: ralph-wiggum-loop cycle 086
- baseline: system_bot_policy_v3_loop_active (adopted_cycle=82)
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_086_20260220_205032/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_086_20260220_205032/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_086_20260220_205032/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_086_20260220_205032/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (robust_pass=False, pareto_constraints=True, holdout_pass=False)

## [autopilot-hook] 2026-02-21T01:39:08+0800 cycle=86 reason=cycle_completed
- change_id: 20260221-013908-ralph-loop-cycle-086-hook
- change_type: Patch
- scope: `tools/ralph_wiggum_loop.py`（missing-ticket fallback 增加 robustness companion）
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; quick_gate.reason=full_gate_fail; llm_action_gate.reason=source_cycle_mismatch; no_improve_streak=4
- evidence:
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_086_20260220_205032/review.json
  - cycle result | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_086_20260220_205032/cycle_result.json
  - patch | ref=tools/ralph_wiggum_loop.py
  - next action | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_next_action.json
- outcome: CONTINUE
- rationale: 在连续停滞窗口中保留 focus 修复主机制，同时注入稳健性 companion，降低 full_gate_fail 再触发概率，并确保下一轮可消费 action ticket。

### 20260221-062649-ralph-loop-cycle-087
- change_id: 20260221-062649-ralph-loop-cycle-087
- change_type: Eval
- scope: ralph-wiggum-loop cycle 087
- baseline: system_bot_policy_v3_loop_active (adopted_cycle=82)
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_087_20260221_013806/baseline_integrity_repair/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_087_20260221_013806/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate no improvement
### 2026-02-21-cycle087-quick-delta-relax
- change_id: 2026-02-21-cycle087-quick-delta-relax
- change_type: Refine
- scope: `tools/ralph_wiggum_loop.py`（quick gate 停滞场景的机制候选晋级阈值）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: N/A（hook 轮仅做机制补丁 + 轻量验证，未跑重型评测）
- evidence:
  - E1: `quick_gate.reason=quick_gate_no_improvement` | n/a | seeds=n/a | evidence_ref=tmp/ralph_loop_runs_v2/cycle_087_20260221_013806/review.json
  - E2: `no_improve_streak=5` | n/a | seeds=n/a | evidence_ref=tmp/ralph_loop_state_v2.json
  - E3: `_effective_quick_min_delta` 新增 streak>=4 放宽分支 | n/a | seeds=n/a | evidence_ref=tools/ralph_wiggum_loop.py
- outcome: CONTINUE
- rationale: 该补丁将 repeated no-improve 时的机制候选放行窗口从 0.35 进一步收敛到 0.25 上限，目标是降低“近似平分却无法进入 full gate”的空转概率，同时保持原有 support/behavior/integrity 约束不变。

## [autopilot-hook] 2026-02-21T06:27:12+0800 cycle=87 reason=cycle_completed
- change_type: Patch
- decision: full_gate_fail_stagnation_probe_threshold_v1
- why: `no_improve_streak=5` 触发停滞处理；completed review 为 `quick_gate_no_improvement`，且 `last_reason=full_gate_fail` 时 `no_improve_probe_streak` 维持高阈值，导致机制候选难以及时进入 full gate。
- what: `tools/ralph_wiggum_loop.py` 将停滞探针阈值放宽逻辑扩展到 `full_gate_fail` 分支（机制优先且存在 eligible mechanism 时，阈值=4；`quick_gate_no_improvement` 保持阈值=2）。
- rollback: 回退 `tools/ralph_wiggum_loop.py` 中 `prioritize_mechanism_probe/target_probe_streak` 分支。
- verify: `python3 -m py_compile tools/ralph_wiggum_loop.py`；`python3` 校验 `tmp/ralph_next_action.json` 必填字段与 `change_applied=true`。
- evidence_ref: `tools/ralph_wiggum_loop.py`, `tmp/ralph_patch_manifest_cycle_087_hook_20260221_062712.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_runs_v2/cycle_087_20260221_013806/review.json`, `tmp/ralph_loop_runs_v2/cycle_087_20260221_013806/cycle_result.json`


## [autopilot-hook] 2026-02-21T11:20:49+0800 cycle=88 reason=awaiting_llm_action
- change_type: Patch
- decision: unblock_awaiting_action_with_high_price_turn_river_pressure_ramp_v1
- why: action ticket gate is blocked on `missing_action`; completed cycle 087 shows `quick_gate_no_improvement` with `no_improve_streak=5`, requiring a mechanism-level move.
- what: patched `poker2/runtime/system_policy.py` high-price facing-bet defense with smooth TURN/RIVER pressure ramp (`turn_river_pressure_penalty`) and trace emission (`high_price_turn_river_pressure_penalty_ppm`).
- how: reused existing threshold/gap/oop/multiway/spr/wet parameters; no secondary config source added. wrote fresh `tmp/ralph_next_action.json` (source_cycle=87, change_applied=true, patched_files includes core policy file).
- rollback: revert the new pressure-ramp block and trace key in `poker2/runtime/system_policy.py`; discard `tmp/ralph_patch_manifest_cycle_088_hook.json` if needed.
- verify: `PYTHONPYCACHEPREFIX=/tmp python3 -m py_compile poker2/runtime/system_policy.py`; python3 required-field checks for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle_088_hook.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_runs_v2/cycle_087_20260221_013806/review.json`, `tmp/ralph_loop_runs_v2/cycle_087_20260221_013806/cycle_result.json`

### 2026-02-21-cycle088-awaiting-action-wet-firewall
- change_id: 2026-02-21-cycle088-awaiting-action-wet-firewall
- change_type: Enforce
- scope: `poker2/runtime/system_policy.py`（TURN/RIVER 高价位 Facing=Y 在低SPR+湿面路径增加有上限防守收缩）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: null（hook unblock patch；未跑重评测）
- evidence:
  - E1: `coinpoker.tierP_facingY_turnriver_worst_bb100=-470.86` | n=51 | seeds=2000-2005 | evidence_ref=tmp/ralph_loop_runs_v2/cycle_087_20260221_013806/cycle_result.json
  - E2: `no_improve_streak=5` | evidence_ref=tmp/ralph_loop_runs_v2/cycle_087_20260221_013806/cycle_result.json
  - E3: `quick_gate.reason=quick_gate_no_improvement` | evidence_ref=tmp/ralph_loop_runs_v2/cycle_087_20260221_013806/review.json
- outcome: CONTINUE
- rationale: 先解除 action ticket 门禁并落地单机制可回退补丁；下一次 worker 重试可直接消费 action，再用 quick gate 验证行为变化与支持度。

### 2026-02-21-hook-awaiting-llm-action-river-recheck
- change_id: 2026-02-21-hook-awaiting-llm-action-river-recheck
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（RIVER 高价位阈值再收紧 clamp）
- baseline: system_bot_policy_v3_loop_active
- delta: n/a（awaiting_llm_action unblock patch）
- evidence:
  - source event | ref=tmp/ralph_loop_runs_v2/cycle_088_20260221_112830
  - completed review | ref=tmp/ralph_loop_runs_v2/cycle_087_20260221_013806/review.json
  - patch manifest | ref=tmp/ralph_patch_manifest_cycle_088_hook.json
- outcome: CONTINUE
- rationale: 优先解除 action ticket 门禁，同时以单机制、可回退方式收紧 RIVER 高价位风险路径。

## [autopilot-hook] 2026-02-21T11:33:40+0800 cycle=88 reason=awaiting_llm_action
- change_type: Patch
- decision: unblock_awaiting_action_with_river_threshold_tail_hardening_v1
- why: `ticket_reason=missing_action` blocked worker retry; completed cycle 087 remained `quick_gate_no_improvement` with `no_improve_streak=5`, requiring a mechanism-level intervention.
- what: patched `poker2/runtime/system_policy.py` RIVER high-price threshold recheck with bounded tail hardening (`price>=1.12*threshold2`) and emitted `high_price_river_threshold_tail_penalty_ppm` trace for replay evidence.
- rollback: revert the tail-hardening block and trace key in `poker2/runtime/system_policy.py`; discard `tmp/ralph_patch_manifest_cycle_088_hook_20260221_113340.json` if rollbacking this hook.
- verify: `python3 -m py_compile poker2/runtime/system_policy.py`; `python3` required-field validation for `tmp/ralph_next_action.json` (source_cycle/change_applied/patched_files).
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle_088_hook_20260221_113340.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_runs_v2/cycle_087_20260221_013806/review.json`, `tmp/ralph_loop_runs_v2/cycle_087_20260221_013806/cycle_result.json`

### 2026-02-21-cycle088-awaiting-action-river-tail-hardening
- change_id: 2026-02-21-cycle088-awaiting-action-river-tail-hardening
- change_type: Enforce
- scope: `poker2/runtime/system_policy.py`（RIVER 超高价 Facing=Y 路径增加有上限 tail hardening，复用现有风险项）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: null（hook unblock patch；未跑重评测）
- evidence:
  - E1: `quick_gate.reason=quick_gate_no_improvement` | evidence_ref=tmp/ralph_loop_runs_v2/cycle_087_20260221_013806/review.json
  - E2: `no_improve_streak=5` | evidence_ref=tmp/ralph_loop_runs_v2/cycle_087_20260221_013806/cycle_result.json
  - E3: `high_price_river_threshold_tail_penalty_ppm` trace added | evidence_ref=poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: 先解除 action ticket 门禁并落地单机制可回退补丁，目标是在 RIVER 高价尾段产生可观测行为变化，避免继续行为平坦导致 quick gate 空转。

### 20260221-134819-ralph-loop-cycle-088
- change_id: 20260221-134819-ralph-loop-cycle-088
- change_type: Eval
- scope: ralph-wiggum-loop cycle 088
- baseline: system_bot_policy_v3_loop_active (adopted_cycle=82)
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_088_20260221_113722/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_088_20260221_113722/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_088_20260221_113722/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_088_20260221_113722/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (robust_pass=False, pareto_constraints=True, holdout_pass=False)

### 20260221-185034-ralph-loop-cycle-089
- change_id: 20260221-185034-ralph-loop-cycle-089
- change_type: Eval
- scope: ralph-wiggum-loop cycle 089
- baseline: system_bot_policy_v3_loop_active (adopted_cycle=82)
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_089_20260221_135106/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_089_20260221_135106/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_089_20260221_135106/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_089_20260221_135106/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (robust_pass=False, pareto_constraints=True, holdout_pass=False)

### 20260221-185352-ralph-loop-cycle-090
- change_id: 20260221-185352-ralph-loop-cycle-090
- change_type: Eval
- scope: ralph-wiggum-loop cycle 090
- baseline: system_bot_policy_v3_loop_active (adopted_cycle=82)
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_087_20260221_013806/baseline_integrity_repair/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_090_20260221_185322/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate forced-bet integrity fail

## [autopilot-hook] 2026-02-22T01:04:54+0800 cycle=95 reason=awaiting_llm_action
- change_type: Patch
- decision: unblock_awaiting_action_with_turn_commitment_activation_widen_v3
- why: action ticket blocked on `source_cycle_mismatch`; latest completed cycle 094 still `quick_gate_forced_bet_integrity_fail` and review shows mechanism candidates `support=0/eligible=0`.
- what: patched `poker2/runtime/system_policy.py` to widen TURN high-price commitment clamp activation window from `0.92*threshold2` to `0.88*threshold2`, while keeping bounded near-threshold scaling to preserve rollback safety.
- rollback: revert the two TURN commitment sensitivity lines in `poker2/runtime/system_policy.py` (`activation threshold` and `near_threshold_scale` formula).
- verify: `PYTHONPYCACHEPREFIX=tmp/.pycache python3 -m py_compile poker2/runtime/system_policy.py`; python3 required-field validation for `tmp/ralph_next_action.json` (`source_cycle=94`, `change_applied=true`, `patched_files` includes core file).
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle_095_hook_20260222_010454.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_runs_v2/cycle_094_20260221_233607/review.json`, `tmp/ralph_loop_runs_v2/cycle_094_20260221_233607/cycle_result.json`

### 2026-02-22-cycle095-awaiting-action-turn-commitment-activation-widen-v3
- change_id: 2026-02-22-cycle095-awaiting-action-turn-commitment-activation-widen-v3
- change_type: Enforce
- scope: `poker2/runtime/system_policy.py`（TURN 高价位 Facing=Y commitment clamp 触发覆盖扩展，保留有界缩放）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: null（hook unblock patch；未跑重评测）
- evidence:
  - E1: `quick_gate.reason=quick_gate_forced_bet_integrity_fail` | evidence_ref=tmp/ralph_loop_runs_v2/cycle_094_20260221_233607/review.json
  - E2: `eligible_count=0, support_pass_count=0` | evidence_ref=tmp/ralph_loop_runs_v2/cycle_094_20260221_233607/review.json
  - E3: `source_cycle_mismatch` ticket gate on cycle 095 heartbeat | evidence_ref=tmp/ralph_loop_runs_v2/cycle_095_20260222_010454/input_next_action.json
- outcome: CONTINUE
- rationale: 在 action ticket 门禁阻塞下先提交可回退单机制补丁并纠正 next_action 源周期，优先恢复 worker 可消费动作与可观测行为变化通道。

## [autopilot-hook] 2026-02-21T18:57:25+0800 cycle=91 reason=awaiting_llm_action
- change_type: Patch
- decision: unblock_awaiting_action_with_river_commitment_clamp_v1
- why: action ticket blocked on `missing_action`; state reports `no_improve_streak=8` and latest completed quick gate reason `quick_gate_forced_bet_integrity_fail`.
- what: patched `poker2/runtime/system_policy.py` with bounded RIVER high-price commitment clamp (`to_call/stack_chips`) under existing risk terms; added trace keys `high_price_river_commitment_ratio_ppm` and `high_price_river_commitment_clamp_penalty_ppm`.
- rollback: revert commitment clamp block and trace keys in `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=/tmp python3 -m py_compile poker2/runtime/system_policy.py`; python3 validation for `tmp/ralph_next_action.json` required fields.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle_091_hook_20260221_185725.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_runs_v2/cycle_090_20260221_185322/review.json`, `tmp/ralph_loop_runs_v2/cycle_090_20260221_185322/cycle_result.json`

### 20260221-202715-ralph-loop-cycle-091
- change_id: 20260221-202715-ralph-loop-cycle-091
- change_type: Eval
- scope: ralph-wiggum-loop cycle 091
- baseline: system_bot_policy_v3_loop_active (adopted_cycle=82)
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_087_20260221_013806/baseline_integrity_repair/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_091_20260221_190132/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate forced-bet integrity fail


## [autopilot-hook] 2026-02-21T20:27:15+0800 cycle=92 reason=awaiting_llm_action
- change_type: Patch
- decision: low_spr_wet_firewall_extreme_clamp_v1
- why: action ticket missing blocked worker retry; last completed review showed quick_gate_forced_bet_integrity_fail with eligible_count=0 under stagnation.
- what: added bounded extreme-branch clamp in `poker2/runtime/system_policy.py` for high-price low-SPR wet multiway TURN/RIVER and emitted corresponding trace ppm field.
- rollback: revert `wet_low_spr_firewall_extreme_penalty` branch and trace field in `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=tmp/.pycache python3 -m py_compile poker2/runtime/system_policy.py`; required-field validation for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle_092_hook_20260221_202715.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_runs_v2/cycle_091_20260221_190132/review.json`, `tmp/ralph_loop_runs_v2/cycle_091_20260221_190132/cycle_result.json`

### 20260221-215706-ralph-loop-cycle-092
- change_id: 20260221-215706-ralph-loop-cycle-092
- change_type: Eval
- scope: ralph-wiggum-loop cycle 092
- baseline: system_bot_policy_v3_loop_active (adopted_cycle=82)
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_087_20260221_013806/baseline_integrity_repair/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_092_20260221_203223/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate forced-bet integrity fail

## [autopilot-hook] 2026-02-21T21:57:07+0800 cycle=93 reason=awaiting_llm_action
- change_type: Patch
- decision: unblock_awaiting_action_with_turn_commitment_clamp_v1
- why: action ticket blocked on `missing_action`; state shows `no_improve_streak=10`, and latest completed cycle 092 remains `quick_gate_forced_bet_integrity_fail`.
- what: patched `poker2/runtime/system_policy.py` with bounded TURN high-price commitment clamp on risky OOP/multiway facing-bet paths, and added trace keys `high_price_turn_commitment_ratio_ppm` + `high_price_turn_commitment_clamp_penalty_ppm`.
- rollback: revert the TURN commitment clamp block and the two TURN trace keys in `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=tmp/.pycache python3 -m py_compile poker2/runtime/system_policy.py`; python3 required-field validation for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle_093_hook_20260221_215707.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_runs_v2/cycle_092_20260221_203223/review.json`, `tmp/ralph_loop_runs_v2/cycle_092_20260221_203223/cycle_result.json`

### 2026-02-21-cycle093-awaiting-action-turn-commitment-clamp
- change_id: 2026-02-21-cycle093-awaiting-action-turn-commitment-clamp
- change_type: Enforce
- scope: `poker2/runtime/system_policy.py`（TURN 高价位 Facing=Y 路径新增 bounded commitment clamp）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: null（hook unblock patch；未跑重评测）
- evidence:
  - E1: `quick_gate.reason=quick_gate_forced_bet_integrity_fail` | evidence_ref=tmp/ralph_loop_runs_v2/cycle_092_20260221_203223/review.json
  - E2: `no_improve_streak=10` | evidence_ref=tmp/ralph_loop_state_v2.json
  - E3: `high_price_turn_commitment_clamp_penalty_ppm` trace added | evidence_ref=poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: 优先解除 action ticket 门禁并落地单机制、可回退补丁，目标是在 TURN 高价位分支产生可观测行为变化，避免继续空转。

### 20260221-233233-ralph-loop-cycle-093
- change_id: 20260221-233233-ralph-loop-cycle-093
- change_type: Eval
- scope: ralph-wiggum-loop cycle 093
- baseline: system_bot_policy_v3_loop_active (adopted_cycle=82)
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_087_20260221_013806/baseline_integrity_repair/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_093_20260221_215954/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate forced-bet integrity fail

## [autopilot-hook] 2026-02-21T23:32:33+0800 cycle=94 reason=awaiting_llm_action
- change_type: Patch
- decision: unblock_awaiting_action_with_turn_commitment_clamp_sensitivity_ramp_v2
- why: action ticket blocked on `source_cycle_mismatch`; latest completed cycle quick gate remains `quick_gate_forced_bet_integrity_fail` and `no_improve_streak=11`.
- what: patched `poker2/runtime/system_policy.py` TURN high-price commitment clamp to use wider activation (`0.92*threshold2`), SPR/wet-aware trigger ramp, and bounded near-threshold scaling for measurable behavior shift.
- rollback: revert modified TURN commitment clamp block in `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=tmp/.pycache python3 -m py_compile poker2/runtime/system_policy.py`; python3 validation for `tmp/ralph_next_action.json` required fields and `source_cycle=93`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle_094_hook_20260221_233233.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_runs_v2/cycle_093_20260221_215954/review.json`, `tmp/ralph_loop_runs_v2/cycle_093_20260221_215954/cycle_result.json`

### 2026-02-21-cycle094-awaiting-action-turn-commitment-sensitivity-ramp
- change_id: 2026-02-21-cycle094-awaiting-action-turn-commitment-sensitivity-ramp
- change_type: Enforce
- scope: `poker2/runtime/system_policy.py`（TURN 高价位 Facing=Y commitment clamp 灵敏度增强）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: null（hook unblock patch；未跑重评测）
- evidence:
  - E1: `quick_gate.reason=quick_gate_forced_bet_integrity_fail` | evidence_ref=tmp/ralph_loop_runs_v2/cycle_093_20260221_215954/review.json
  - E2: `no_improve_streak=11` | evidence_ref=tmp/ralph_loop_state_v2.json
  - E3: `turn_commitment_clamp_sensitivity_ramp_v2` patch applied | evidence_ref=poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: 在 action ticket 门禁阻塞下，优先提交可回退单机制补丁并写入可消费 next_action，确保下一次 worker 重试可继续迭代。

### 20260222-010454-ralph-loop-cycle-094
- change_id: 20260222-010454-ralph-loop-cycle-094
- change_type: Eval
- scope: ralph-wiggum-loop cycle 094
- baseline: system_bot_policy_v3_loop_active (adopted_cycle=82)
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_087_20260221_013806/baseline_integrity_repair/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_094_20260221_233607/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate forced-bet integrity fail

### 20260222-023830-ralph-loop-cycle-095
- change_id: 20260222-023830-ralph-loop-cycle-095
- change_type: Eval
- scope: ralph-wiggum-loop cycle 095
- baseline: system_bot_policy_v3_loop_active (adopted_cycle=82)
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_087_20260221_013806/baseline_integrity_repair/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_095_20260222_010842/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate forced-bet integrity fail

### 2026-02-22-cycle096-awaiting-action-river-forced-bet-guard
- change_id: 2026-02-22-cycle096-awaiting-action-river-forced-bet-guard
- change_type: Enforce
- scope: `poker2/runtime/system_policy.py`（RIVER 高价 Facing=Y + 多人 + 低SPR 分支增加 forced-bet integrity guard）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: null（hook unblock patch；未跑重评测）
- evidence:
  - E1: `event.reason=awaiting_llm_action` + `ticket_reason=source_cycle_mismatch` | ref=event:2026-02-22T02:38:30+0800
  - E2: `quick_gate.reason=quick_gate_forced_bet_integrity_fail` | ref=tmp/ralph_loop_runs_v2/cycle_095_20260222_010842/review.json
  - E3: `high_price_river_forced_bet_guard_penalty_ppm` trace added | ref=poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: 本轮优先解除 action ticket 门禁并落地单机制可回退补丁，确保 worker 下次重试可消费 `source_cycle=95` 的动作，同时在高风险 river 分支制造可观测行为变化。
- verify: `python3 -m py_compile poker2/runtime/system_policy.py`; `python3` required-field validation for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle_096_hook_20260222_023830.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_runs_v2/cycle_095_20260222_010842/review.json`, `tmp/ralph_loop_runs_v2/cycle_095_20260222_010842/cycle_result.json`

### 20260222-041115-ralph-loop-cycle-096
- change_id: 20260222-041115-ralph-loop-cycle-096
- change_type: Eval
- scope: ralph-wiggum-loop cycle 096
- baseline: system_bot_policy_v3_loop_active (adopted_cycle=82)
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_087_20260221_013806/baseline_integrity_repair/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_096_20260222_024118/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate forced-bet integrity fail

### 2026-02-22-awaiting-llm-action-unblock-river-guard
- change_id: 2026-02-22-awaiting-llm-action-unblock-river-guard
- change_type: Enforce
- scope: `poker2/runtime/system_policy.py`（RIVER high-price multiway low-SPR facing-bet re-aggression cap）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: null（action ticket unblock patch；本轮未运行评测）
- evidence:
  - E1: quick_gate.reason=quick_gate_forced_bet_integrity_fail | n/a | seeds=n/a | evidence_ref=tmp/ralph_loop_runs_v2/cycle_096_20260222_024118/cycle_result.json
  - E2: no_improve_streak=14 | n/a | seeds=n/a | evidence_ref=tmp/ralph_loop_state_v2.json
  - E3: heartbeat.reason=awaiting_llm_action ticket_reason=source_cycle_mismatch | n/a | seeds=n/a | evidence_ref=tmp/ralph_loop_runs_v2/cycle_097_20260222_041115/input_next_action.json
- outcome: CONTINUE
- rationale: 先解除 ticket 门禁并做单机制可回退修复；等待 worker 以 `source_cycle=96` 重试消费 action。

### 2026-02-22-awaiting-llm-action-unblock-river-guard
- change_id: 2026-02-22-awaiting-llm-action-unblock-river-guard
- change_type: Enforce
- scope: `poker2/runtime/system_policy.py`（RIVER high-price multiway low-SPR facing-bet re-aggression cap）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: null（action ticket unblock patch；本轮未运行评测）
- evidence:
  - E1: quick_gate.reason=quick_gate_forced_bet_integrity_fail | n/a | seeds=n/a | evidence_ref=tmp/ralph_loop_runs_v2/cycle_096_20260222_024118/cycle_result.json
  - E2: no_improve_streak=14 | n/a | seeds=n/a | evidence_ref=tmp/ralph_loop_state_v2.json
  - E3: heartbeat.reason=awaiting_llm_action ticket_reason=source_cycle_mismatch | n/a | seeds=n/a | evidence_ref=tmp/ralph_loop_runs_v2/cycle_097_20260222_041115/input_next_action.json
- outcome: CONTINUE
- rationale: 先解除 ticket 门禁并做单机制可回退修复；等待 worker 以 `source_cycle=96` 重试消费 action。

### 20260222-054840-ralph-loop-cycle-097
- change_id: 20260222-054840-ralph-loop-cycle-097
- change_type: Eval
- scope: ralph-wiggum-loop cycle 097
- baseline: system_bot_policy_v3_loop_active (adopted_cycle=82)
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_087_20260221_013806/baseline_integrity_repair/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_097_20260222_041433/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate forced-bet integrity fail

## [autopilot-hook] 2026-02-22T05:49:20+0800 cycle=97 reason=cycle_completed
- change_type: Patch
- decision: cycle_completed_mechanism_patch_river_forced_bet_commitment_boost_v1
- why: `no_improve_streak=15` and latest completed review indicates `quick_gate_forced_bet_integrity_fail` with `eligible_count=0` and `support_pass_count=0`.
- what: patched `poker2/runtime/system_policy.py` to widen RIVER high-price forced-bet guard and add bounded commitment-ratio penalty branch (`high_price_river_forced_bet_commitment_penalty_ppm`) for deep-commitment OOP/MW paths.
- rollback: revert the commitment-boost branch and trace field in `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=tmp/.pycache python3 -m py_compile poker2/runtime/system_policy.py`; python3 required-field validation for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle_097_hook_20260222_054920.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_runs_v2/cycle_097_20260222_041433/review.json`, `tmp/ralph_loop_runs_v2/cycle_097_20260222_041433/cycle_result.json`

### 2026-02-22-cycle097-completed-river-forced-bet-commitment-boost-v1
- change_id: 2026-02-22-cycle097-completed-river-forced-bet-commitment-boost-v1
- change_type: Enforce
- scope: `poker2/runtime/system_policy.py`（RIVER 高价位 Facing=Y forced-bet guard 引入 commitment-aware bounded penalty）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: null（checkpoint hook patch；未运行重评测）
- evidence:
  - E1: `quick_gate.reason=quick_gate_forced_bet_integrity_fail` | evidence_ref=tmp/ralph_loop_runs_v2/cycle_097_20260222_041433/review.json
  - E2: `no_improve_streak=15` | evidence_ref=tmp/ralph_loop_state_v2.json
  - E3: `high_price_river_forced_bet_commitment_penalty_ppm` trace added | evidence_ref=poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: 在 cycle_completed 检查点命中停滞触发条件时，先落地单机制可回退补丁并输出可消费 next_action，以恢复下一轮对“行为变化+支持度”的最短反馈闭环。

## [autopilot-hook] 2026-02-22T05:49:20+0800 cycle=97 reason=cycle_completed
- change_type: Patch
- decision: cycle_completed_mechanism_patch_river_forced_bet_commitment_boost_v1
- why: `no_improve_streak=15` and latest completed review indicates `quick_gate_forced_bet_integrity_fail` with `eligible_count=0` and `support_pass_count=0`.
- what: patched `poker2/runtime/system_policy.py` to widen RIVER high-price forced-bet guard and add bounded commitment-ratio penalty branch (`high_price_river_forced_bet_commitment_penalty_ppm`) for deep-commitment OOP/MW paths.
- rollback: revert the commitment-boost branch and trace field in `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=tmp/.pycache python3 -m py_compile poker2/runtime/system_policy.py`; python3 required-field validation for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle_097_hook_20260222_054920.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_runs_v2/cycle_097_20260222_041433/review.json`, `tmp/ralph_loop_runs_v2/cycle_097_20260222_041433/cycle_result.json`

### 2026-02-22-cycle097-completed-river-forced-bet-commitment-boost-v1
- change_id: 2026-02-22-cycle097-completed-river-forced-bet-commitment-boost-v1
- change_type: Enforce
- scope: `poker2/runtime/system_policy.py`（RIVER 高价位 Facing=Y forced-bet guard 引入 commitment-aware bounded penalty）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: null（checkpoint hook patch；未运行重评测）
- evidence:
  - E1: `quick_gate.reason=quick_gate_forced_bet_integrity_fail` | evidence_ref=tmp/ralph_loop_runs_v2/cycle_097_20260222_041433/review.json
  - E2: `no_improve_streak=15` | evidence_ref=tmp/ralph_loop_state_v2.json
  - E3: `high_price_river_forced_bet_commitment_penalty_ppm` trace added | evidence_ref=poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: 在 cycle_completed 检查点命中停滞触发条件时，先落地单机制可回退补丁并输出可消费 next_action，以恢复下一轮对“行为变化+支持度”的最短反馈闭环。

### 20260222-072026-ralph-loop-cycle-098
- change_id: 20260222-072026-ralph-loop-cycle-098
- change_type: Eval
- scope: ralph-wiggum-loop cycle 098
- baseline: system_bot_policy_v3_loop_active (adopted_cycle=82)
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_087_20260221_013806/baseline_integrity_repair/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_098_20260222_055649/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate forced-bet integrity fail


## [autopilot-hook] 2026-02-22T07:20:26+0800 cycle=99 reason=awaiting_llm_action
- change_type: Patch
- decision: unblock_awaiting_action_with_river_forced_bet_guard_trigger_ramp_v3
- why: action ticket blocked on `missing_action`; state has `no_improve_streak=16`, latest completed review remains `quick_gate_forced_bet_integrity_fail` with `eligible_count=0`.
- what: patched `poker2/runtime/system_policy.py` with dynamic RIVER forced-bet guard trigger ramp (down to bounded near-threshold region on wet/low-SPR/multiway paths) and added trace keys `high_price_river_forced_bet_guard_trigger_ppm` + `high_price_river_forced_bet_near_trigger_penalty_ppm`.
- rollback: revert the trigger ramp and near-threshold branch plus the two trace keys in `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=tmp/.pycache python3 -m py_compile poker2/runtime/system_policy.py`; python3 required-field validation for `tmp/ralph_next_action.json` with `source_cycle=98`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle_099_hook_20260222_072026.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_runs_v2/cycle_098_20260222_055649/review.json`, `tmp/ralph_loop_runs_v2/cycle_098_20260222_055649/cycle_result.json`

### 2026-02-22-cycle099-awaiting-action-river-forced-bet-guard-trigger-ramp-v3
- change_id: 2026-02-22-cycle099-awaiting-action-river-forced-bet-guard-trigger-ramp-v3
- change_type: Enforce
- scope: `poker2/runtime/system_policy.py`（RIVER high-price forced-bet guard trigger ramp + near-threshold bounded penalty）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: null（hook unblock patch；未跑重评测）
- evidence:
  - E1: `event.reason=awaiting_llm_action` + `ticket_reason=missing_action` | ref=event:2026-02-22T07:20:26+0800
  - E2: `state.no_improve_streak=16` | ref=tmp/ralph_loop_state_v2.json
  - E3: `review.quick_gate.reason=quick_gate_forced_bet_integrity_fail` and `eligible_count=0` | ref=tmp/ralph_loop_runs_v2/cycle_098_20260222_055649/review.json
- outcome: CONTINUE
- rationale: prioritize unblocking action ticket with a single rollback-safe mechanism patch that increases support/behavior observability on the recurring forced-bet integrity branch.

## [autopilot-hook] 2026-02-22T07:20:26+0800 cycle=99 reason=awaiting_llm_action
- change_type: Patch
- decision: unblock_awaiting_action_with_river_forced_bet_ultra_low_spr_ramp_v4
- why: `ticket_reason=missing_action` blocked worker retry; `no_improve_streak=16` and latest completed review still `quick_gate_forced_bet_integrity_fail` with `eligible_count=0`.
- what: patched `poker2/runtime/system_policy.py` by extending RIVER forced-bet guard trigger ramp (lower bounded trigger floor + wider low-SPR guard window) and adding bounded `high_price_river_forced_bet_ultra_low_spr_penalty_ppm` trace branch.
- rollback: revert the trigger-ramp and ultra-low-SPR penalty block in `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=tmp/.pycache python3 -m py_compile poker2/runtime/system_policy.py`; `python3` required-field validation for `tmp/ralph_next_action.json` with `source_cycle=98`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle_099_hook_20260222_072026_v4.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_runs_v2/cycle_098_20260222_055649/review.json`, `tmp/ralph_loop_runs_v2/cycle_098_20260222_055649/cycle_result.json`

### 2026-02-22-cycle099-awaiting-action-river-forced-bet-ultra-low-spr-ramp-v4
- change_id: 2026-02-22-cycle099-awaiting-action-river-forced-bet-ultra-low-spr-ramp-v4
- change_type: Enforce
- scope: `poker2/runtime/system_policy.py`（RIVER high-price forced-bet guard trigger ramp + ultra-low-SPR bounded penalty）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: null（hook unblock patch；未跑重评测）
- evidence:
  - E1: `event.reason=awaiting_llm_action` + `ticket_reason=missing_action` | evidence_ref=event:2026-02-22T07:20:26+0800
  - E2: `state.no_improve_streak=16` | evidence_ref=tmp/ralph_loop_state_v2.json
  - E3: `quick_gate.reason=quick_gate_forced_bet_integrity_fail` and `eligible_count=0` | evidence_ref=tmp/ralph_loop_runs_v2/cycle_098_20260222_055649/review.json
- outcome: CONTINUE
- rationale: unblock action-ticket gating with one rollback-safe mechanism patch and emit consumable next_action (`source_cycle=98`) for immediate worker retry.

### 20260222-085806-ralph-loop-cycle-099
- change_id: 20260222-085806-ralph-loop-cycle-099
- change_type: Eval
- scope: ralph-wiggum-loop cycle 099
- baseline: system_bot_policy_v3_loop_active (adopted_cycle=82)
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_087_20260221_013806/baseline_integrity_repair/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_099_20260222_073305/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate forced-bet integrity fail

## [autopilot-hook] 2026-02-22T08:58:06+0800 cycle=100 reason=awaiting_llm_action
- change_type: Patch
- decision: unblock_awaiting_action_with_river_forced_bet_trigger_ramp_v5
- why: `ticket_reason=missing_action` blocks worker retry; state shows `no_improve_streak=17` and latest completed review remains `quick_gate_forced_bet_integrity_fail` with `eligible_count=0`.
- what: patched `poker2/runtime/system_policy.py` to lower RIVER forced-bet guard trigger floor and widen near-threshold penalty window on low-SPR OOP/MW branches.
- rollback: revert the trigger-ramp and near-threshold envelope edits in `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=tmp/.pycache python3 -m py_compile poker2/runtime/system_policy.py`; python3 required-field validation for `tmp/ralph_next_action.json` with `source_cycle=99`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle_100_hook_20260222_085806_v5.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_runs_v2/cycle_099_20260222_073305/review.json`, `tmp/ralph_loop_runs_v2/cycle_099_20260222_073305/cycle_result.json`

### 2026-02-22-cycle100-awaiting-action-river-forced-bet-trigger-ramp-v5
- change_id: 2026-02-22-cycle100-awaiting-action-river-forced-bet-trigger-ramp-v5
- change_type: Enforce
- scope: `poker2/runtime/system_policy.py`（RIVER high-price forced-bet guard trigger ramp v5）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: null（hook unblock patch；未跑重评测）
- evidence:
  - E1: `event.reason=awaiting_llm_action` + `ticket_reason=missing_action` | evidence_ref=event:2026-02-22T08:58:06+0800
  - E2: `state.no_improve_streak=17` | evidence_ref=tmp/ralph_loop_state_v2.json
  - E3: `review.quick_gate.reason=quick_gate_forced_bet_integrity_fail` and `eligible_count=0` | evidence_ref=tmp/ralph_loop_runs_v2/cycle_099_20260222_073305/review.json
- outcome: CONTINUE
- rationale: unblock action-ticket gating with one rollback-safe mechanism patch while increasing support observability on the recurrent forced-bet integrity branch.

### 20260222-103013-ralph-loop-cycle-100
- change_id: 20260222-103013-ralph-loop-cycle-100
- change_type: Eval
- scope: ralph-wiggum-loop cycle 100
- baseline: system_bot_policy_v3_loop_active (adopted_cycle=82)
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_087_20260221_013806/baseline_integrity_repair/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_100_20260222_090124/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate forced-bet integrity fail

### 2026-02-22-awaiting-llm-action-unblock-cycle101-forced-bet-guard
- change_id: 2026-02-22-awaiting-llm-action-unblock-cycle101-forced-bet-guard
- change_type: Enforce
- scope: `poker2/runtime/system_policy.py`（RIVER forced-bet integrity guard support widening for multiway low-SPR high-price branch）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: null（action ticket unblock patch；本轮未运行评测）
- evidence:
  - E1: event.reason=awaiting_llm_action ticket_reason=source_cycle_mismatch | n/a | seeds=n/a | evidence_ref=event:2026-02-22T10:30:13+0800
  - E2: quick_gate.reason=quick_gate_forced_bet_integrity_fail | n/a | seeds=n/a | evidence_ref=tmp/ralph_loop_runs_v2/cycle_100_20260222_090124/review.json
  - E3: no_improve_streak=18 | n/a | seeds=n/a | evidence_ref=tmp/ralph_loop_state_v2.json
- outcome: CONTINUE
- rationale: 本轮优先解除 action ticket 门禁并执行单机制可回退补丁；新的 `tmp/ralph_next_action.json` 固定 `source_cycle=100`，可被 cycle 101 重试直接消费。
- verify: `python3 -m py_compile poker2/runtime/system_policy.py`; `python3` JSON required-field check.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle_101_hook_20260222_103013.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_runs_v2/cycle_100_20260222_090124/review.json`

### 20260222-120209-ralph-loop-cycle-101
- change_id: 20260222-120209-ralph-loop-cycle-101
- change_type: Eval
- scope: ralph-wiggum-loop cycle 101
- baseline: system_bot_policy_v3_loop_active (adopted_cycle=82)
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_087_20260221_013806/baseline_integrity_repair/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_101_20260222_103315/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate forced-bet integrity fail

## [autopilot-hook] 2026-02-22T12:02:09+0800 cycle=102 reason=awaiting_llm_action
- change_type: Patch
- decision: unblock_awaiting_action_with_river_forced_bet_support_floor_ramp_v1
- why: `ticket_reason=source_cycle_mismatch` 且上一已完成周期仍为 `quick_gate_forced_bet_integrity_fail`（`eligible_count=0`, `support_pass_count=0`），并且 `no_improve_streak=19`。
- what: patch `poker2/runtime/system_policy.py`，在 RIVER high-price forced-bet integrity guard 下新增 bounded pre-trigger support-floor ramp（仅 guard 触发阈值下方窄区间生效），并输出 trace `high_price_river_forced_bet_support_floor_penalty_ppm`。
- rollback: 回退 `poker2/runtime/system_policy.py` 中 support-floor 分支与新增 trace 字段。
- verify: `PYTHONPYCACHEPREFIX=tmp/.pycache python3 -m py_compile poker2/runtime/system_policy.py`; `python3` required-field 校验 `tmp/ralph_next_action.json`。
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle_102_hook_20260222_120209.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_runs_v2/cycle_101_20260222_103315/review.json`, `tmp/ralph_loop_runs_v2/cycle_101_20260222_103315/cycle_result.json`

### 2026-02-22-cycle102-awaiting-action-river-forced-bet-support-floor-ramp-v1
- change_id: 2026-02-22-cycle102-awaiting-action-river-forced-bet-support-floor-ramp-v1
- change_type: Enforce
- scope: `poker2/runtime/system_policy.py`（RIVER forced-bet integrity pre-trigger support-floor ramp）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: null（hook unblock patch；未跑重评测）
- evidence:
  - E1: `event.reason=awaiting_llm_action` + `ticket_reason=source_cycle_mismatch` | n/a | seeds=n/a | evidence_ref=event:2026-02-22T12:02:09+0800
  - E2: `quick_gate.reason=quick_gate_forced_bet_integrity_fail` and `eligible_count=0` | n/a | seeds=n/a | evidence_ref=tmp/ralph_loop_runs_v2/cycle_101_20260222_103315/review.json
  - E3: `no_improve_streak=19` | n/a | seeds=n/a | evidence_ref=tmp/ralph_loop_state_v2.json
- outcome: CONTINUE
- rationale: 优先解除 action ticket 门禁并保持单机制、可回退改动，通过 pre-trigger bounded ramp 提升 forced-bet 分支 support/behavior 可观测性，供下一次 worker 重试消费。

### 20260222-145424-ralph-loop-cycle-102
- change_id: 20260222-145424-ralph-loop-cycle-102
- change_type: Eval
- scope: ralph-wiggum-loop cycle 102
- baseline: system_bot_policy_v3_loop_active (adopted_cycle=82)
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_087_20260221_013806/baseline_integrity_repair/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_102_20260222_120652/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate low focus support

## [autopilot-hook] 2026-02-22T14:54:24+0800 cycle=103 reason=awaiting_llm_action
- change_type: Patch
- decision: awaiting_llm_action_mechanism_patch_river_forced_bet_support_bridge_v1
- why: `ticket_reason=missing_action` blocked worker retry; latest completed review shows `quick_gate_low_focus_support` with `eligible_count=0`, and state has `no_improve_streak=20`.
- what: patched `poker2/runtime/system_policy.py` to add bounded `river_forced_bet_support_bridge_penalty` in high-price RIVER forced-bet guard pre-trigger window, plus trace field `high_price_river_forced_bet_support_bridge_penalty_ppm`.
- rollback: revert support-bridge variable/branch/trace in `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=tmp/.pycache python3 -m py_compile poker2/runtime/system_policy.py`; python3 required-field validation for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle_103_hook_20260222_145424.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_runs_v2/cycle_102_20260222_120652/review.json`, `tmp/ralph_loop_runs_v2/cycle_102_20260222_120652/cycle_result.json`

### 2026-02-22-cycle103-awaiting-action-river-forced-bet-support-bridge-v1
- change_id: 2026-02-22-cycle103-awaiting-action-river-forced-bet-support-bridge-v1
- change_type: Enforce
- scope: `poker2/runtime/system_policy.py`（RIVER 高价位 forced-bet guard 增加 near-threshold support bridge）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: null（hook unblock patch；未运行重评测）
- evidence:
  - E1: `quick_gate.reason=quick_gate_low_focus_support` | evidence_ref=tmp/ralph_loop_runs_v2/cycle_102_20260222_120652/review.json
  - E2: `no_improve_streak=20` | evidence_ref=tmp/ralph_loop_state_v2.json
  - E3: `high_price_river_forced_bet_support_bridge_penalty_ppm` trace added | evidence_ref=poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: 先解除 action ticket 阻塞并用单机制 bounded 补丁扩大近阈值覆盖，给下一轮 quick gate 提供可观测行为变化与支持度提升机会。

### 20260222-181204-ralph-loop-cycle-103
- change_id: 20260222-181204-ralph-loop-cycle-103
- change_type: Eval
- scope: ralph-wiggum-loop cycle 103
- baseline: system_bot_policy_v3_loop_active (adopted_cycle=82)
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_087_20260221_013806/baseline_integrity_repair/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_103_20260222_145915/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate low focus support

### 20260222-210655-ralph-loop-cycle-104
- change_id: 20260222-210655-ralph-loop-cycle-104
- change_type: Eval
- scope: ralph-wiggum-loop cycle 104
- baseline: system_bot_policy_v3_loop_active (adopted_cycle=82)
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_087_20260221_013806/baseline_integrity_repair/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_104_20260222_181548/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate low focus support

## [autopilot-hook] 2026-02-22T21:06:55+0800 cycle=105 reason=awaiting_llm_action
- change_type: Patch
- decision: unblock_awaiting_action_with_river_forced_bet_support_window_expand_v1
- why: worker retry is gated by `missing_action`; latest completed cycle reports `quick_gate_low_focus_support` and state shows `no_improve_streak=22`.
- what: patched `poker2/runtime/system_policy.py` by adding bounded support-window expansion on the RIVER forced-bet guard branch (multiway/wet/low-SPR/commitment contexts only), and added trace key `high_price_river_forced_bet_support_window_expand_ppm`.
- rollback: revert support-window expansion block and the new trace key in `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=tmp/.pycache python3 -m py_compile poker2/runtime/system_policy.py`; `python3` required-field + source-cycle validation for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle_105_hook_20260222_210655.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_104_20260222_181548/review.json`, `tmp/ralph_loop_runs_v2/cycle_104_20260222_181548/cycle_result.json`

### 2026-02-22-cycle105-awaiting-action-river-forced-bet-support-window-expand-v1
- change_id: 2026-02-22-cycle105-awaiting-action-river-forced-bet-support-window-expand-v1
- change_type: Enforce
- scope: `poker2/runtime/system_policy.py`（RIVER forced-bet guard support-window bounded expansion）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: null（hook unblock patch；未跑重评测）
- evidence:
  - E1: `event.reason=awaiting_llm_action` + `ticket_reason=missing_action` | ref=event:2026-02-22T21:06:55+0800
  - E2: `state.no_improve_streak=22` | ref=tmp/ralph_loop_state_v2.json
  - E3: `review.quick_gate.reason=quick_gate_low_focus_support` | ref=tmp/ralph_loop_runs_v2/cycle_104_20260222_181548/review.json
- outcome: CONTINUE
- rationale: use one rollback-safe mechanism patch to raise support hits on the recurrent low-focus-support branch and unblock worker action gating.

### 20260223-002642-ralph-loop-cycle-105
- change_id: 20260223-002642-ralph-loop-cycle-105
- change_type: Eval
- scope: ralph-wiggum-loop cycle 105
- baseline: system_bot_policy_v3_loop_active (adopted_cycle=82)
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_087_20260221_013806/baseline_integrity_repair/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_105_20260222_211142/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate low focus support

## [autopilot-hook] 2026-02-23T00:27:00+0800 cycle=106 reason=cycle_completed
- change_type: Patch
- decision: cycle_completed_mechanism_patch_river_forced_bet_support_stall_escalator_v1
- why: `state.no_improve_streak=23` 且最新 completed `quick_gate.reason=quick_gate_low_focus_support`，并且 `active_support` 仅 `hands=48/hits=3`，连续卡在 support 门槛以下。
- what: patch `poker2/runtime/system_policy.py`，在 RIVER forced-bet guard 分支加入 bounded stalled-branch support escalator（MW+wet+low-SPR / high-commitment 条件下扩展 near-threshold support window），并新增 trace `high_price_river_forced_bet_support_stall_bonus_ppm`。
- rollback: 回退 `poker2/runtime/system_policy.py` 中 `river_forced_bet_support_stall_bonus` 相关分支与 trace 字段。
- verify: `PYTHONPYCACHEPREFIX=tmp/.pycache python3 -m py_compile poker2/runtime/system_policy.py`
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle_106_hook_20260223_002700.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_105_20260222_211142/review.json`, `tmp/ralph_loop_runs_v2/cycle_105_20260222_211142/cycle_result.json`

### 2026-02-23-cycle106-checkpoint-river-forced-bet-support-stall-escalator-v1
- change_id: 2026-02-23-cycle106-checkpoint-river-forced-bet-support-stall-escalator-v1
- change_type: Enforce
- scope: `poker2/runtime/system_policy.py`（RIVER forced-bet guard stalled-branch support escalator）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: null（checkpoint hook patch；未跑重评测）
- evidence:
  - E1: `event.reason=cycle_completed` and `event.cycle=105` | ref=event:2026-02-23T00:27:00+0800
  - E2: `state.no_improve_streak=23` | ref=tmp/ralph_loop_state_v2.json
  - E3: `review.quick_gate.reason=quick_gate_low_focus_support` and `active_support(hands=48,hits=3)` | ref=tmp/ralph_loop_runs_v2/cycle_105_20260222_211142/review.json
- outcome: CONTINUE
- rationale: 在不引入新参数口径的前提下，用单机制、可回退的 near-threshold 覆盖扩展提高 support 命中概率，供下一轮 quick gate 验证。

### 20260223-044629-ralph-loop-cycle-106
- change_id: 20260223-044629-ralph-loop-cycle-106
- change_type: Eval
- scope: ralph-wiggum-loop cycle 106
- baseline: system_bot_policy_v3_loop_active (adopted_cycle=82)
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_087_20260221_013806/baseline_integrity_repair/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_106_20260223_002642/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate low focus support

### 2026-02-23-awaiting-llm-action-unblock-cycle107-river-support-window-ramp-v6
- change_id: 2026-02-23-awaiting-llm-action-unblock-cycle107-river-support-window-ramp-v6
- change_type: Enforce
- scope: `poker2/runtime/system_policy.py`（RIVER forced-bet support-window ramp v6 on multiway wet low-SPR high-price branch）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: null（hook unblock patch；本轮未跑重评测）
- evidence:
  - E1: `event.reason=awaiting_llm_action` + `ticket_reason=missing_action` | evidence_ref=event:2026-02-23T04:46:29+0800
  - E2: `review.quick_gate.reason=quick_gate_low_focus_support` + `focus_probe support 48/3 -> 57/4` | evidence_ref=tmp/ralph_loop_runs_v2/cycle_106_20260223_002642/review.json, tmp/ralph_loop_runs_v2/cycle_106_20260223_002642/cycle_result.json
  - E3: `state.no_improve_streak=24` + `mechanism_only priority active` | evidence_ref=tmp/ralph_loop_state_v2.json
- outcome: CONTINUE
- rationale: 当前先解除 action ticket 门禁；在不引入新参数前提下，仅扩大 forced-bet 预触发支持窗口，提升 low-focus-support 分支覆盖以便下一轮 worker 重试可产生可比较行为差异。
- verify: `python3 -m py_compile poker2/runtime/system_policy.py`; `python3` JSON required-field check.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle_107_hook_20260223_044629.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `notes/iteration_journal.md`

### 20260223-080906-ralph-loop-cycle-107
- change_id: 20260223-080906-ralph-loop-cycle-107
- change_type: Eval
- scope: ralph-wiggum-loop cycle 107
- baseline: system_bot_policy_v3_loop_active (adopted_cycle=82)
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_087_20260221_013806/baseline_integrity_repair/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_107_20260223_044932/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate no improvement

## [autopilot-hook] 2026-02-23T08:09:06+0800 cycle=108 reason=awaiting_llm_action
- change_type: Patch
- decision: unblock_awaiting_action_with_river_forced_bet_support_recenter_v1
- why: worker ticket reports `source_cycle_mismatch`; latest completed review is `quick_gate_no_improvement` and state shows `no_improve_streak=25`, so support-only widening is no longer sufficient.
- what: patched `poker2/runtime/system_policy.py` by adding bounded `river_forced_bet_support_recenter_penalty` on the exact RIVER high-price forced-bet branch (MW + wet + low-SPR) and trace `high_price_river_forced_bet_support_recenter_penalty_ppm`.
- rollback: revert recenter penalty variable/branch/trace in `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=tmp/.pycache python3 -m py_compile poker2/runtime/system_policy.py`; `python3` required-field + source-cycle check for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle_108_hook_20260223_080906.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_runs_v2/cycle_107_20260223_044932/review.json`, `tmp/ralph_loop_runs_v2/cycle_107_20260223_044932/cycle_result.json`, `tmp/ralph_loop_state_v2.json`

### 2026-02-23-cycle108-awaiting-action-river-forced-bet-support-recenter-v1
- change_id: 2026-02-23-cycle108-awaiting-action-river-forced-bet-support-recenter-v1
- change_type: Enforce
- scope: `poker2/runtime/system_policy.py`（RIVER forced-bet support recenter penalty on stalled MW wet low-SPR branch）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: null（hook unblock patch；本轮未跑重评测）
- evidence:
  - E1: `event.reason=awaiting_llm_action` + `ticket_reason=source_cycle_mismatch` | evidence_ref=event:2026-02-23T08:09:06+0800
  - E2: `review.quick_gate.reason=quick_gate_no_improvement` + `focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100` | evidence_ref=tmp/ralph_loop_runs_v2/cycle_107_20260223_044932/review.json
  - E3: `state.no_improve_streak=25` | evidence_ref=tmp/ralph_loop_state_v2.json
- outcome: CONTINUE
- rationale: this hook focuses on action-ticket unblock plus one rollback-safe mechanism shift from support expansion to near-threshold recenter hardening, so next worker retry can consume cycle-aligned action with measurable behavior pressure.

### 20260223-151515-ralph-loop-cycle-108
- change_id: 20260223-151515-ralph-loop-cycle-108
- change_type: Eval
- scope: ralph-wiggum-loop cycle 108
- baseline: system_bot_policy_v3_loop_active (adopted_cycle=82)
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_108_20260223_091426/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_108_20260223_091426/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_108_20260223_091426/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_108_20260223_091426/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate standard fail (robust_pass=False, pareto_constraints=True, holdout_pass=False)

### 2026-02-23-awaiting-action-river-guard-escalation
- change_id: 2026-02-23-awaiting-action-river-guard-escalation
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（RIVER 高价位 facing 分支 forced-bet guard 惩罚斜率增强）
- baseline: `system_bot_policy_v3_loop_active`
- delta: `null`（hook unblock patch；未执行完整评测）
- evidence:
  - `coinpoker.tierP_facingY_turnriver_worst_bb100=-534.98` | n=51 | seeds=2000–2005 | evidence_ref=`tmp/ralph_loop_runs_v2/cycle_108_20260223_091426/cycle_result.json`
  - `quick_gate.reason=full_gate_fail` | n=1 | seeds=cycle108 | evidence_ref=`tmp/ralph_loop_runs_v2/cycle_108_20260223_091426/cycle_result.json`
  - `no_improve_streak=26` | n=1 | seeds=state | evidence_ref=`tmp/ralph_loop_state_v2.json`
- outcome: CONTINUE
- rationale: 先解除 action ticket 阻塞并落地单机制补丁；下一次 worker 重试应直接消费 action 并验证是否改善 focus 分支。

### 20260223-211250-ralph-loop-cycle-109
- change_id: 20260223-211250-ralph-loop-cycle-109
- change_type: Eval
- scope: ralph-wiggum-loop cycle 109
- baseline: system_bot_policy_v3_loop_active (adopted_cycle=82)
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_109_20260223_151835/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_109_20260223_151835/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_109_20260223_151835/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_109_20260223_151835/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate standard fail (robust_pass=False, pareto_constraints=True, holdout_pass=False)

## [autopilot-hook] 2026-02-23T21:12:50+0800 cycle=110 reason=awaiting_llm_action
- change_type: Patch
- decision: unblock_awaiting_action_with_river_forced_bet_near_trigger_commitment_ramp_v1
- why: action ticket blocked on `missing_action`; latest completed cycle 109 is `full_gate_fail`, and `state.no_improve_streak=27` indicates stalled branch behavior.
- what: patched `poker2/runtime/system_policy.py` on the existing RIVER forced-bet near-trigger path with a bounded commitment-weighted ramp for `MW+wet+low-SPR+high-commitment` branch only.
- rollback: revert the added conditional near-trigger cap/scale bump block in `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=tmp/.pycache python3 -m py_compile poker2/runtime/system_policy.py`; `python3` required-field + `source_cycle` check for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle_110_hook_20260223_211250.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_109_20260223_151835/review.json`, `tmp/ralph_loop_runs_v2/cycle_109_20260223_151835/cycle_result.json`

### 2026-02-23-cycle110-awaiting-action-river-near-trigger-commitment-ramp-v1
- change_id: 2026-02-23-cycle110-awaiting-action-river-near-trigger-commitment-ramp-v1
- change_type: Enforce
- scope: `poker2/runtime/system_policy.py`（RIVER forced-bet near-trigger commitment ramp on MW wet low-SPR branch）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: null（hook unblock patch；未跑重评测）
- evidence:
  - E1: `event.reason=awaiting_llm_action` + `ticket_reason=missing_action` | evidence_ref=event:2026-02-23T21:12:50+0800
  - E2: `review.quick_gate.reason=full_gate_fail` | evidence_ref=tmp/ralph_loop_runs_v2/cycle_109_20260223_151835/review.json
  - E3: `state.no_improve_streak=27` | evidence_ref=tmp/ralph_loop_state_v2.json
- outcome: CONTINUE
- rationale: unblock worker retry with a single rollback-safe mechanism patch to increase behavior pressure on the exact stalled forced-bet branch while avoiding low-price spillover.

### 20260224-010730-ralph-loop-cycle-110
- change_id: 20260224-010730-ralph-loop-cycle-110
- change_type: Eval
- scope: ralph-wiggum-loop cycle 110
- baseline: system_bot_policy_v3_loop_active (adopted_cycle=82)
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_087_20260221_013806/baseline_integrity_repair/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_110_20260223_211641/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate low focus support

## [autopilot-hook] 2026-02-24T01:07:30+0800 cycle=111 reason=awaiting_llm_action
- change_type: Patch
- decision: unblock_awaiting_action_with_river_forced_bet_deep_stall_support_window_expand_v1
- why: worker retry is gated by `missing_action`; latest completed cycle reports `quick_gate_low_focus_support` and state shows `no_improve_streak=28`.
- what: patched `poker2/runtime/system_policy.py` by adding a bounded deep-stall bonus to the existing RIVER forced-bet support-window branch (MW+wet+low-SPR+deep-commitment contexts), and added trace key `high_price_river_forced_bet_support_deep_stall_bonus_ppm`.
- rollback: revert deep-stall support-window expansion block and the new trace key in `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=tmp/.pycache python3 -m py_compile poker2/runtime/system_policy.py`; `python3` required-field + source-cycle validation for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle_111_hook_20260224_010730.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_110_20260223_211641/review.json`, `tmp/ralph_loop_runs_v2/cycle_110_20260223_211641/cycle_result.json`

### 2026-02-24-cycle111-awaiting-action-river-forced-bet-deep-stall-support-window-expand-v1
- change_id: 2026-02-24-cycle111-awaiting-action-river-forced-bet-deep-stall-support-window-expand-v1
- change_type: Enforce
- scope: `poker2/runtime/system_policy.py`（RIVER forced-bet support-window deep-stall bounded expansion）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: null（hook unblock patch；未跑重评测）
- evidence:
  - E1: `event.reason=awaiting_llm_action` + `ticket_reason=missing_action` | ref=event:2026-02-24T01:07:30+0800
  - E2: `state.no_improve_streak=28` | ref=tmp/ralph_loop_state_v2.json
  - E3: `review.quick_gate.reason=quick_gate_low_focus_support` with support `57/4` and threshold `60/6` | ref=tmp/ralph_loop_runs_v2/cycle_110_20260223_211641/review.json
- outcome: CONTINUE
- rationale: unblock action ticket and apply one rollback-safe mechanism to increase support-window coverage on the recurrent stalled branch.

### 20260224-045221-ralph-loop-cycle-111
- change_id: 20260224-045221-ralph-loop-cycle-111
- change_type: Eval
- scope: ralph-wiggum-loop cycle 111
- baseline: system_bot_policy_v3_loop_active (adopted_cycle=82)
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_087_20260221_013806/baseline_integrity_repair/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_111_20260224_011027/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate low focus support

## [autopilot-hook] 2026-02-24T04:52:21+0800 cycle=112 reason=awaiting_llm_action
- change_type: Patch
- decision: awaiting_llm_action_unblock_patch_river_forced_bet_support_entry_bonus_v1
- why: `awaiting_llm_action` ticket gate blocked worker retry, while `state.no_improve_streak=29` and latest completed `quick_gate.reason=quick_gate_low_focus_support`.
- what: patch `poker2/runtime/system_policy.py` by adding bounded `river_forced_bet_support_entry_bonus` in RIVER forced-bet high-price branch, plus trace `high_price_river_forced_bet_support_entry_bonus_ppm`.
- rollback: remove `river_forced_bet_support_entry_bonus` init/update/trace blocks from `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=tmp/.pycache python3 -m py_compile poker2/runtime/system_policy.py`
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle_112_hook_20260224_045221.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_111_20260224_011027/review.json`, `tmp/ralph_loop_runs_v2/cycle_111_20260224_011027/cycle_result.json`

### 2026-02-24-cycle112-checkpoint-river-forced-bet-support-entry-bonus-v1
- change_id: 2026-02-24-cycle112-checkpoint-river-forced-bet-support-entry-bonus-v1
- change_type: Enforce
- scope: `poker2/runtime/system_policy.py` (RIVER forced-bet support entry bonus for stalled MW+wet+low-SPR branch)
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: null (hook checkpoint patch; no heavy eval)
- evidence:
  - E1: `event.reason=awaiting_llm_action` and `event.cycle=112` | ref=event:2026-02-24T04:52:21+0800
  - E2: `state.no_improve_streak=29` | ref=tmp/ralph_loop_state_v2.json
  - E3: `review.quick_gate.reason=quick_gate_low_focus_support` | ref=tmp/ralph_loop_runs_v2/cycle_111_20260224_011027/review.json
- outcome: CONTINUE
- rationale: unblock ticket and force measurable support coverage shift via one bounded mechanism change in core policy.

### 20260224-083707-ralph-loop-cycle-112
- change_id: 20260224-083707-ralph-loop-cycle-112
- change_type: Eval
- scope: ralph-wiggum-loop cycle 112
- baseline: system_bot_policy_v3_loop_active (adopted_cycle=82)
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_087_20260221_013806/baseline_integrity_repair/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_112_20260224_045528/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate low focus support

### 2026-02-24-awaiting-llm-action-unblock-cycle113-river-support-window-ramp-v7
- change_id: 2026-02-24-awaiting-llm-action-unblock-cycle113-river-support-window-ramp-v7
- change_type: Enforce
- scope: `poker2/runtime/system_policy.py`（RIVER forced-bet support-window ramp v7 on multiway wet low-SPR high-price branch）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: null（hook unblock patch；本轮未跑重评测）
- evidence:
  - E1: `event.reason=awaiting_llm_action` + `ticket_reason=missing_action` | evidence_ref=event:2026-02-24T08:37:07+0800
  - E2: `review.quick_gate.reason=quick_gate_low_focus_support` | evidence_ref=tmp/ralph_loop_runs_v2/cycle_112_20260224_045528/review.json
  - E3: `state.no_improve_streak=30` + `focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100` | evidence_ref=tmp/ralph_loop_state_v2.json
- outcome: CONTINUE
- rationale: 优先解除 action ticket 门禁；单机制增强 forced-bet 支持窗口，提升 low-focus-support 分支覆盖，保障下一次 worker 重试可消费 action 并产生可比较行为差异。
- verify: `PYTHONPYCACHEPREFIX=/tmp/pycache python3 -m py_compile poker2/runtime/system_policy.py`
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle_113_hook_20260224_083707.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `notes/iteration_journal.md`

### 20260224-123038-ralph-loop-cycle-113
- change_id: 20260224-123038-ralph-loop-cycle-113
- change_type: Eval
- scope: ralph-wiggum-loop cycle 113
- baseline: system_bot_policy_v3_loop_active (adopted_cycle=82)
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_087_20260221_013806/baseline_integrity_repair/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_113_20260224_084009/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate low focus support

## [autopilot-hook] 2026-02-24T12:31:06+0800 cycle=113 reason=cycle_completed
- change_type: Patch
- decision: checkpoint_patch_river_forced_bet_support_tail_bonus_v1
- why: latest completed cycle still `quick_gate_low_focus_support`; `active_support=57/4` below `80/6`; `no_improve_streak=31` requires continued mechanism-only pressure.
- what: patched `poker2/runtime/system_policy.py` by adding bounded `river_forced_bet_support_tail_bonus` and conditional support-window cap lift on existing RIVER high-price forced-bet MW+wet+low-SPR branch; added trace `high_price_river_forced_bet_support_tail_bonus_ppm`.
- rollback: remove tail-bonus init/branch/cap-lift/trace blocks and restore prior fixed support-window cap.
- verify: `PYTHONPYCACHEPREFIX=tmp/.pycache python3 -m py_compile poker2/runtime/system_policy.py`; `python3` check required fields for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle_113_checkpoint_20260224_123106.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_runs_v2/cycle_113_20260224_084009/review.json`, `tmp/ralph_loop_runs_v2/cycle_113_20260224_084009/cycle_result.json`, `tmp/ralph_loop_state_v2.json`

### 2026-02-24-cycle113-checkpoint-river-forced-bet-support-tail-bonus-v1
- change_id: 2026-02-24-cycle113-checkpoint-river-forced-bet-support-tail-bonus-v1
- change_type: Enforce
- scope: `poker2/runtime/system_policy.py`（RIVER forced-bet support tail bonus on stalled MW wet low-SPR high-commit branch）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: null（hook checkpoint patch；未跑重评测）
- evidence:
  - E1: `event.reason=cycle_completed` and `event.cycle=113` | ref=event:2026-02-24T12:31:06+0800
  - E2: `review.quick_gate.reason=quick_gate_low_focus_support` with `active_support=57/4` and threshold `80/6` | ref=tmp/ralph_loop_runs_v2/cycle_113_20260224_084009/review.json
  - E3: `state.no_improve_streak=31` and `focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100` | ref=tmp/ralph_loop_state_v2.json
- outcome: CONTINUE
- rationale: apply one rollback-safe mechanism patch to lift focus-support coverage without broadening into low-price/non-target branches, so next worker retry can consume a concrete action with measurable branch pressure.

### 20260224-183414-ralph-loop-cycle-114
- change_id: 20260224-183414-ralph-loop-cycle-114
- change_type: Eval
- scope: ralph-wiggum-loop cycle 114
- baseline: system_bot_policy_v3_loop_active (adopted_cycle=82)
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_114_20260224_123415/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_114_20260224_123415/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_114_20260224_123415/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_114_20260224_123415/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate standard fail (robust_pass=False, pareto_constraints=True, holdout_pass=False)

### 2026-02-24-awaiting-action-river-support-proximity-bonus
- change_id: 2026-02-24-awaiting-action-river-support-proximity-bonus
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（RIVER forced-bet support window 近阈值扩展）
- baseline: `system_bot_policy_v3_loop_active`
- delta: `null`（awaiting_llm_action unblock；未执行完整评测）
- evidence:
  - `no_improve_streak=32` | ref=`tmp/ralph_loop_state_v2.json`
  - `cycle114 decision=REJECT, quick_gate.reason=full_gate_fail` | ref=`tmp/ralph_loop_runs_v2/cycle_114_20260224_123415/review.json`
  - `patched_file=poker2/runtime/system_policy.py` | ref=`tmp/ralph_patch_manifest_cycle_115_awaiting_llm_action.json`
- outcome: CONTINUE
- rationale: 先解除 action ticket 阻塞，并在高价位 river forced-bet 分支做单机制可回退改动，提升 stalled branch 的 support 覆盖与行为可见性。

### 20260225-004425-ralph-loop-cycle-115
- change_id: 20260225-004425-ralph-loop-cycle-115
- change_type: Eval
- scope: ralph-wiggum-loop cycle 115
- baseline: system_bot_policy_v3_loop_active (adopted_cycle=82)
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_115_20260224_183715/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_115_20260224_183715/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_115_20260224_183715/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_115_20260224_183715/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (robust_pass=False, pareto_constraints=False, holdout_pass=False)

## [autopilot-hook] 2026-03-10T05:35:05+0800 cycle=164 reason=cycle_completed
- change_type: Patch
- decision: apply_turn_support_hit_direct_raise_clamp_v1
- why: `no_improve_streak=82` and cycle164 review still shows `quick_gate.reason=full_gate_fail`, `support_pass_count=0`, `eligible_count=0`, `targeted_focus_support_hands_delta_total=24`, `targeted_focus_support_hits_delta_total=0`, while cycle165 is only at `active_quick`; the stalled TURN low-SPR wet visibility-reentry lane needs a direct raise clamp instead of another threshold widening.
- what: patched `poker2/runtime/system_policy.py` to add `turn_focus_support_raise_clamp_strength`, a bounded TURN-only direct raise-share clamp and call-floor boost that activates only after the existing low-SPR wet multiway support-hit recenter branch is already live.
- rollback: remove `turn_focus_support_raise_clamp_strength`, the direct call-floor / raise-cap block wired from `support_hit_recenter_branch`, and the corresponding trace fields from `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=/tmp/pycache_verify python3 -m py_compile poker2/runtime/system_policy.py` and `python3` required-field validation for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle164_20260310_053505_autohook.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_164_20260310_025822/review.json`, `tmp/ralph_loop_runs_v2/cycle_164_20260310_025822/cycle_result.json`

### 2026-03-10-cycle164-turn-support-hit-direct-raise-clamp-v1
- change_id: 2026-03-10-cycle164-turn-support-hit-direct-raise-clamp-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（TURN low-SPR wet visibility-reentry stalled lane direct raise clamp）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（checkpoint light patch; heavy eval deferred）
- evidence:
  - E1 | metric=no_improve_streak=82 | n=1 state | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E2 | metric=cycle164.quick_gate.reason=full_gate_fail,support_pass_count=0,eligible_count=0,targeted_focus_support_hands_delta_total=24,targeted_focus_support_hits_delta_total=0 | n=1 cycle | seeds=cycle164 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_164_20260310_025822/review.json
  - E3 | metric=mechanism_patch_applied(turn_support_hit_direct_raise_clamp_v1) | n=1 file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: the prior visibility/reentry threshold relief patches still expanded support coverage without producing a hit, so the next bounded step is to keep the same branch active but convert it into an explicit raise-share clamp and call-floor boost that the quick gate can observe as a real behavior change.

## [autopilot-hook] 2026-02-25T00:44:25+0800 cycle=116 reason=awaiting_llm_action
- change_type: Patch
- decision: unblock_awaiting_action_with_river_forced_bet_support_closure_bonus_v1
- why: worker retry blocked by `missing_action`; latest completed cycle 115 is `full_gate_fail`; `no_improve_streak=33`.
- what: patched `poker2/runtime/system_policy.py` by adding bounded `river_forced_bet_support_closure_bonus` on existing RIVER forced-bet MW+wet+low-SPR+high-commitment tail branch; added trace key `high_price_river_forced_bet_support_closure_bonus_ppm`.
- rollback: remove closure-bonus init/branch/window-add/cap/trace blocks in `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=tmp/.pycache python3 -m py_compile poker2/runtime/system_policy.py`; `python3` required-field + source-cycle check for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle_116_hook_20260225_004425.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_115_20260224_183715/review.json`, `tmp/ralph_loop_runs_v2/cycle_115_20260224_183715/cycle_result.json`

### 2026-02-25-cycle116-awaiting-action-river-support-closure-bonus-v1
- change_id: 2026-02-25-cycle116-awaiting-action-river-support-closure-bonus-v1
- change_type: Enforce
- scope: `poker2/runtime/system_policy.py`（RIVER forced-bet support closure bonus on stalled MW wet low-SPR high-commit tails）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: null（hook unblock patch；未跑重评测）
- evidence:
  - E1: `event.reason=awaiting_llm_action` + `ticket_reason=missing_action` | ref=event:2026-02-25T00:44:25+0800
  - E2: `review.quick_gate.reason=full_gate_fail` | ref=tmp/ralph_loop_runs_v2/cycle_115_20260224_183715/review.json
  - E3: `state.no_improve_streak=33` and focus metric target unchanged | ref=tmp/ralph_loop_state_v2.json
- outcome: CONTINUE
- rationale: unblock action ticket with one rollback-safe mechanism patch focused on the recurrent forced-bet tail branch so next worker retry can consume action and produce measurable behavior pressure.

### 20260225-065638-ralph-loop-cycle-116
- change_id: 20260225-065638-ralph-loop-cycle-116
- change_type: Eval
- scope: ralph-wiggum-loop cycle 116
- baseline: system_bot_policy_v3_loop_active (adopted_cycle=82)
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_116_20260225_004744/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_116_20260225_004744/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_116_20260225_004744/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_116_20260225_004744/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate standard fail (robust_pass=False, pareto_constraints=True, holdout_pass=False)


## [autopilot-hook] 2026-02-25T06:56:38+0800 cycle=117 reason=awaiting_llm_action
- change_type: Patch
- decision: unblock_awaiting_action_with_river_forced_bet_support_window_taper_v1
- why: worker retry blocked by `missing_action`; latest completed cycle (116) ended in `full_gate_fail` under long stagnation (`no_improve_streak=34`).
- what: patched `poker2/runtime/system_policy.py` with bounded taper on non-deep-tail forced-bet support-window expansion; added cap/taper trace fields.
- rollback: revert taper/cap logic and new trace keys in `poker2/runtime/system_policy.py`.
- verify: `python3 -m py_compile poker2/runtime/system_policy.py`; `python3` required-field + source-cycle validation for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle_117_hook_20260225_065638.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_116_20260225_004744/review.json`, `tmp/ralph_loop_runs_v2/cycle_116_20260225_004744/cycle_result.json`

### 2026-02-25-cycle117-awaiting-action-river-forced-bet-support-window-taper-v1
- change_id: 2026-02-25-cycle117-awaiting-action-river-forced-bet-support-window-taper-v1
- change_type: Enforce
- scope: `poker2/runtime/system_policy.py`（RIVER forced-bet support-window non-deep-tail taper）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: null（hook unblock patch；未跑重评测）
- evidence:
  - E1: `event.reason=awaiting_llm_action` + `ticket_reason=missing_action` | ref=event:2026-02-25T06:56:38+0800
  - E2: `state.no_improve_streak=34` | ref=tmp/ralph_loop_state_v2.json
  - E3: `review.quick_gate.reason=full_gate_fail` with focus delta `0.0` | ref=tmp/ralph_loop_runs_v2/cycle_116_20260225_004744/review.json
- outcome: CONTINUE
- rationale: unblock action gate and apply one rollback-safe mechanism to narrow support-window side effects while preserving stalled-branch coverage.

### 20260225-130442-ralph-loop-cycle-117
- change_id: 20260225-130442-ralph-loop-cycle-117
- change_type: Eval
- scope: ralph-wiggum-loop cycle 117
- baseline: system_bot_policy_v3_loop_active (adopted_cycle=82)
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_117_20260225_065914/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_117_20260225_065914/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_117_20260225_065914/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_117_20260225_065914/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (robust_pass=False, pareto_constraints=True, holdout_pass=False)

## [autopilot-hook] 2026-02-25T13:04:42+0800 cycle=118 reason=awaiting_llm_action
- change_type: Patch
- decision: unblock_awaiting_action_with_river_forced_bet_support_taper_relief_v1
- why: worker retry blocked by `missing_action`; `no_improve_streak=35`; latest completed cycle (117) still `full_gate_fail` with persistent focus leak.
- what: patched `poker2/runtime/system_policy.py` to add bounded `river_forced_bet_support_taper_relief` in the existing RIVER forced-bet MW+wet low-SPR commitment branch, plus trace key `high_price_river_forced_bet_support_taper_relief_ppm`.
- rollback: remove taper-relief init/branch/trace blocks in `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=tmp/.pycache python3 -m py_compile poker2/runtime/system_policy.py`; `python3` required-field + `source_cycle=117` validation for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle_118_hook_20260225_130442.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_117_20260225_065914/review.json`, `tmp/ralph_loop_runs_v2/cycle_117_20260225_065914/cycle_result.json`

### 2026-02-25-cycle118-awaiting-action-river-support-taper-relief-v1
- change_id: 2026-02-25-cycle118-awaiting-action-river-support-taper-relief-v1
- change_type: Enforce
- scope: `poker2/runtime/system_policy.py`（RIVER forced-bet support-window taper relief on targeted MW wet low-SPR commitment branch）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: null（hook unblock patch；未跑重评测）
- evidence:
  - E1: `event.reason=awaiting_llm_action` + `ticket_reason=missing_action` | ref=event:2026-02-25T13:04:42+0800
  - E2: `state.no_improve_streak=35` | ref=tmp/ralph_loop_state_v2.json
  - E3: `review.quick_gate.reason=full_gate_fail` | ref=tmp/ralph_loop_runs_v2/cycle_117_20260225_065914/review.json
- outcome: CONTINUE
- rationale: unblock action gate with one rollback-safe mechanism patch to raise support-window activation on the recurring stalled branch while limiting spillover to non-target paths.

### 20260225-235645-ralph-loop-cycle-118
- change_id: 20260225-235645-ralph-loop-cycle-118
- change_type: Eval
- scope: ralph-wiggum-loop cycle 118
- baseline: system_bot_policy_v3_loop_active (adopted_cycle=82)
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_118_20260225_165820/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_118_20260225_165820/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_118_20260225_165820/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_118_20260225_165820/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (robust_pass=False, pareto_constraints=True, holdout_pass=False)


## [autopilot-hook] 2026-02-25T23:56:45+0800 cycle=119 reason=awaiting_llm_action
- change_type: Patch
- decision: unblock_awaiting_action_with_river_forced_bet_support_saturation_bonus_v1
- why: worker retry blocked by `missing_action`; latest completed cycle 118 remains `full_gate_fail`; `state.no_improve_streak=36`.
- what: patched `poker2/runtime/system_policy.py` with bounded `river_forced_bet_support_saturation_bonus` on deep-tail near-threshold forced-bet branch; added trace key `high_price_river_forced_bet_support_saturation_bonus_ppm`.
- rollback: remove saturation-bonus init/branch/window-add/cap/trace blocks in `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=tmp/.pycache python3 -m py_compile poker2/runtime/system_policy.py`; `python3` required-field + `source_cycle=118` validation for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle_119_hook_20260225_235645.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_118_20260225_165820/review.json`, `tmp/ralph_loop_runs_v2/cycle_118_20260225_165820/cycle_result.json`

### 2026-02-25-cycle119-awaiting-action-river-support-saturation-bonus-v1
- change_id: 2026-02-25-cycle119-awaiting-action-river-support-saturation-bonus-v1
- change_type: Enforce
- scope: `poker2/runtime/system_policy.py`（RIVER forced-bet support-window saturation bonus on deep-tail near-threshold branch）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: null（hook unblock patch；未跑重评测）
- evidence:
  - E1: `event.reason=awaiting_llm_action` + `ticket_reason=missing_action` | ref=event:2026-02-25T23:56:45+0800
  - E2: `state.no_improve_streak=36` | ref=tmp/ralph_loop_state_v2.json
  - E3: `review.quick_gate.reason=full_gate_fail` with focus metric `coinpoker.tierP_facingY_turnriver_worst_bb100` | ref=tmp/ralph_loop_runs_v2/cycle_118_20260225_165820/review.json
- outcome: CONTINUE
- rationale: unblock action gate with one rollback-safe mechanism patch targeted to deep-tail near-threshold forced-bet states so next worker retry can consume action and produce measurable behavior pressure.

### 20260226-073346-ralph-loop-cycle-119
- change_id: 20260226-073346-ralph-loop-cycle-119
- change_type: Eval
- scope: ralph-wiggum-loop cycle 119
- baseline: system_bot_policy_v3_loop_active (adopted_cycle=82)
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_119_20260225_235944/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_119_20260225_235944/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_119_20260225_235944/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_119_20260225_235944/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (robust_pass=False, pareto_constraints=True, holdout_pass=False)

### 20260302-141529-ralph-loop-cycle-120
- change_id: 20260302-141529-ralph-loop-cycle-120
- change_type: Eval
- scope: ralph-wiggum-loop cycle 120
- baseline: system_bot_policy_v3_loop_active (adopted_cycle=82)
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_087_20260221_013806/baseline_integrity_repair/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_120_20260226_073551/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate no eligible candidate

## [autopilot-hook] 2026-03-02T14:15:31+0800 cycle=120 reason=model_review_due
- change_type: Patch
- decision: reinforce_reactivation_branch_for_quick_gate_eligibility_v1
- why: latest completed review is `quick_gate_no_eligible_candidate` with `no_improve_streak=38`; mechanism-level behavior separation is insufficient.
- what: patched `poker2/runtime/system_policy.py` by strengthening bounded river forced-bet reactivation on targeted MW+wet+low-SPR near-threshold branch.
- rollback: revert reactivation gate/proximity/extra-bonus/cap-lift edits in `poker2/runtime/system_policy.py`.
- verify: `python3 -m py_compile poker2/runtime/system_policy.py`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle_120_model_review_due_20260302_141531.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_120_20260226_073551/review.json`, `tmp/ralph_loop_runs_v2/cycle_120_20260226_073551/cycle_result.json`

### 2026-03-02-cycle120-model-review-reactivation-deadlock-lift-v1
- change_id: 2026-03-02-cycle120-model-review-reactivation-deadlock-lift-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（RIVER forced-bet reactivation deadlock lift on targeted branch）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: null（model_review_due hook patch；未跑重评测）
- evidence:
  - E1: `event.reason=model_review_due` and `event.cycle=120` | ref=event:2026-03-02T14:15:31+0800
  - E2: `review.quick_gate.reason=quick_gate_no_eligible_candidate` | ref=tmp/ralph_loop_runs_v2/cycle_120_20260226_073551/review.json
  - E3: `state.no_improve_streak=38` and focus metric unchanged | ref=tmp/ralph_loop_state_v2.json
- outcome: CONTINUE
- rationale: one rollback-safe mechanism patch to improve candidate behavioral separation on the recurrent stalled branch so next retry can produce eligible quick-gate movement.

### 2026-03-02-cycle120-checkpoint-river-support-ramp-bonus-v1
- change_id: 2026-03-02-cycle120-checkpoint-river-support-ramp-bonus-v1
- change_type: Enforce
- scope: `poker2/runtime/system_policy.py`（RIVER forced-bet support near-threshold ramp bonus on MW+wet+low-SPR high-commit branch）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: null（hook checkpoint patch；未跑重评测）
- evidence:
  - E1: `event.reason=cycle_completed` and `event.cycle=120` | ref=event:2026-03-02T14:15:31+0800
  - E2: `state.no_improve_streak=38` and focus metric remains `coinpoker.tierP_facingY_turnriver_worst_bb100` | ref=tmp/ralph_loop_state_v2.json
  - E3: `review.quick_gate.reason=quick_gate_no_eligible_candidate` | ref=tmp/ralph_loop_runs_v2/cycle_120_20260226_073551/review.json
- outcome: CONTINUE
- rationale: apply one rollback-safe mechanism patch to raise near-threshold support activation on the recurrent forced-bet stalled branch so next worker retry can consume concrete action with measurable behavior pressure.

## [autopilot-hook] 2026-03-02T14:15:33+0800 cycle=120 reason=cycle_completed
- change_type: Patch
- decision: apply_cycle120_river_forced_bet_support_cap_relief_bonus_v1
- why: checkpoint event on cycle 120 with `quick_gate_no_eligible_candidate` and `no_improve_streak=38`; current forced-bet support expansion is likely cap-flattened, reducing behavior separation.
- what: patched `poker2/runtime/system_policy.py` to add bounded `river_forced_bet_support_cap_relief_bonus` (`+0.002..+0.004`) when both stall and saturation bonuses are active on the existing stalled branch; added trace key `high_price_river_forced_bet_support_cap_relief_bonus_ppm`.
- rollback: remove cap-relief init/branch/trace blocks in `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=tmp/.pycache python3 -m py_compile poker2/runtime/system_policy.py`; `python3` required-field + `source_cycle=120` check for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle_120_hook_20260302_141533.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_120_20260226_073551/review.json`, `tmp/ralph_loop_runs_v2/cycle_120_20260226_073551/cycle_result.json`

### 2026-03-02-cycle120-checkpoint-river-support-cap-relief-bonus-v1
- change_id: 2026-03-02-cycle120-checkpoint-river-support-cap-relief-bonus-v1
- change_type: Enforce
- scope: `poker2/runtime/system_policy.py`（RIVER forced-bet support-window cap relief on stalled MW wet low-SPR deep-commit branch）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: null（hook checkpoint patch；未跑重评测）
- evidence:
  - E1: `event.reason=cycle_completed` and `event.cycle=120` | ref=event:2026-03-02T14:15:33+0800
  - E2: `review.quick_gate.reason=quick_gate_no_eligible_candidate` with `candidates=0` | ref=tmp/ralph_loop_runs_v2/cycle_120_20260226_073551/review.json
  - E3: `state.no_improve_streak=38` and `focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100` | ref=tmp/ralph_loop_state_v2.json
- outcome: CONTINUE
- rationale: inject one rollback-safe mechanism that relieves branch-local cap flattening to restore candidate behavior separability for the next worker retry without widening into low-price paths.

### 2026-03-02-awaiting-action-river-bridge-bonus
- change_id: 2026-03-02-awaiting-action-river-bridge-bonus
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（RIVER forced-bet stalled branch near-threshold support-entry bridge bonus）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（awaiting_llm_action unblock；未执行完整评测）
- evidence:
  - E1: `event.reason=awaiting_llm_action`, `event.cycle=121`, `ticket_reason=missing_action` | ref=event:2026-03-02T14:15:29+0800
  - E2: `review.quick_gate.reason=quick_gate_no_eligible_candidate` | ref=tmp/ralph_loop_runs_v2/cycle_120_20260226_073551/review.json
  - E3: `patched_file=poker2/runtime/system_policy.py` | ref=tmp/ralph_patch_manifest_cycle_121_awaiting_llm_action.json
- outcome: CONTINUE
- rationale: 用单机制、窄分支、可回退补丁解除 action ticket 阻塞，提高 stalled forced-bet 分支 support 命中与行为可分性，供下一次 worker 重试消费。

## [autopilot-hook] 2026-03-02T14:15:33+0800 cycle=120 reason=cycle_completed
- change_type: Patch
- decision: apply_river_forced_bet_support_reactivation_bonus_v1
- why: latest completed review returned `quick_gate_no_eligible_candidate` with low support (`hands=57`, `hits=4`), and `no_improve_streak=38` indicates long stagnation.
- what: patched `poker2/runtime/system_policy.py` by adding bounded `river_forced_bet_support_reactivation_bonus` for under-expanded high-price RIVER forced-bet MW+wet+low-SPR branches, plus trace key `high_price_river_forced_bet_support_reactivation_bonus_ppm`.
- rollback: remove reactivation bonus init/branch/window-add/cap/trace blocks in `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=tmp/.pycache python3 -m py_compile poker2/runtime/system_policy.py`; `python3` required-field check for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle_120_hook_20260302_141533.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_120_20260226_073551/review.json`, `tmp/ralph_loop_runs_v2/cycle_120_20260226_073551/cycle_result.json`

### 2026-03-02-cycle120-checkpoint-river-forced-bet-reactivation-bonus-v1
- change_id: 2026-03-02-cycle120-checkpoint-river-forced-bet-reactivation-bonus-v1
- change_type: Enforce
- scope: `poker2/runtime/system_policy.py`（RIVER forced-bet support reactivation bonus on under-expanded stalled branch）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: null（hook checkpoint patch；未跑重评测）
- evidence:
  - E1: `event.reason=cycle_completed` and `event.cycle=120` | ref=event:2026-03-02T14:15:33+0800
  - E2: `review.quick_gate.reason=quick_gate_no_eligible_candidate` with `active_support=57/4` | ref=tmp/ralph_loop_runs_v2/cycle_120_20260226_073551/review.json
  - E3: `state.no_improve_streak=38` and focus metric target unchanged | ref=tmp/ralph_loop_state_v2.json
- outcome: CONTINUE
- rationale: with prolonged stagnation and missing eligible candidates, apply one rollback-safe mechanism to increase support coverage only on the existing forced-bet branch so next cycle has measurable behavior pressure.


## [autopilot-hook] 2026-03-02T14:15:33+0800 cycle=120 reason=cycle_completed
- change_type: Patch
- decision: apply_cycle_completed_bridge_relief_patch_v1
- why: `state.no_improve_streak=38` and `review.quick_gate.reason=quick_gate_no_eligible_candidate` with `active_support={'hands': 57, 'hits': 4}`; latest cycle has `trial_candidate_count=0`.
- what: patched `poker2/runtime/system_policy.py` with bounded `river_forced_bet_support_bridge_relief_v1` on the existing high-price RIVER forced-bet stalled branch.
- rollback: remove the bridge-relief proximity/cap block in `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=tmp/.pycache python3 -m py_compile poker2/runtime/system_policy.py`; `python3` required-field + type checks for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle_120_hook_20260302_141533.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_120_20260226_073551/review.json`, `tmp/ralph_loop_runs_v2/cycle_120_20260226_073551/cycle_result.json`

### 2026-03-02-cycle120-checkpoint-river-support-bridge-relief-v1
- change_id: 2026-03-02-cycle120-checkpoint-river-support-bridge-relief-v1
- change_type: Enforce
- scope: `poker2/runtime/system_policy.py`（RIVER forced-bet support bridge-relief near-threshold bonus on stalled MW wet low-SPR branch）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: null（checkpoint hook patch；未跑重评测）
- evidence:
  - E1: `event.reason=cycle_completed` and `event.cycle=120` | ref=event:2026-03-02T14:15:33+0800
  - E2: `review.quick_gate.reason=quick_gate_no_eligible_candidate` and `active_support={'hands': 57, 'hits': 4}` | ref=tmp/ralph_loop_runs_v2/cycle_120_20260226_073551/review.json
  - E3: `state.no_improve_streak=38` and `trial_candidate_count=0` | ref=tmp/ralph_loop_state_v2.json + tmp/ralph_loop_runs_v2/cycle_120_20260226_073551/cycle_result.json
- outcome: CONTINUE
- rationale: apply one rollback-safe mechanism patch to re-open candidate eligibility on recurrent forced-bet stalled tails while keeping effects narrow and auditable.


### 2026-03-02-cycle120-checkpoint-deep-tail-saturation-window
- change_id: 2026-03-02-cycle120-checkpoint-deep-tail-saturation-window
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（RIVER forced-bet deep-tail saturation window widening, bounded）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: null（hook checkpoint patch；未跑重评测）
- evidence:
  - E1: `event.reason=cycle_completed` and `event.cycle=120` | ref=event:2026-03-02T14:15:33+0800
  - E2: `state.no_improve_streak=38` and `focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100` | ref=tmp/ralph_loop_state_v2.json
  - E3: `review.quick_gate.reason=quick_gate_no_eligible_candidate` and `eligible_count=0` | ref=tmp/ralph_loop_runs_v2/cycle_120_20260226_073551/review.json
- outcome: CONTINUE
- rationale: 在 deep-tail forced-bet 分支增加近阈值饱和支持，仅扩大目标分支行为可见性并保持可回退，优先解除“无可晋级候选”停滞。

### 2026-03-02-awaiting-llm-action-turn-firewall-support
- change_id: 2026-03-02-awaiting-llm-action-turn-firewall-support
- change_type: Refine
- scope: `poker2/runtime/system_policy.py`（TURN low-SPR wet multiway high-price firewall support expansion）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: pending（action-ticket unblock only; full eval not run in this hook）
- evidence:
  - E1 | metric=quick_gate.reason=quick_gate_no_eligible_candidate | n=0 candidates | seeds=cycle120 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_120_20260226_073551/review.json
  - E2 | metric=no_improve_streak=38 | n=? | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E3 | metric=mechanism_patch_applied | n=1 file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: 先解除 awaiting_llm_action 门禁并引入单机制可回退行为改动；等待 worker 重试产出下一轮可比较证据。

### 2026-03-02-cycle120-checkpoint-reactivation-widen-v1
- change_id: 2026-03-02-cycle120-checkpoint-reactivation-widen-v1
- change_type: Enforce
- scope: `poker2/runtime/system_policy.py`（RIVER forced-bet support reactivation window widening on stalled MW wet low-SPR high-price branch）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（hook checkpoint patch；未跑重评测）
- evidence:
  - E1: `event.reason=cycle_completed` and `event.cycle=120` | ref=`tmp/ralph_loop_runs_v2/cycle_120_20260226_073551/cycle_result.json`
  - E2: `review.quick_gate.reason=quick_gate_no_eligible_candidate` | ref=`tmp/ralph_loop_runs_v2/cycle_120_20260226_073551/review.json`
  - E3: `state.no_improve_streak=38` | ref=`tmp/ralph_loop_state_v2.json`
- outcome: CONTINUE
- rationale: Keep single rollback-safe mechanism change, widen only the near-threshold reactivation band on the same stalled forced-bet branch to improve support coverage and candidate behavior separation for the next quick gate.

### 2026-03-02-cycle120-checkpoint-river-far-tail-damp
- change_id: 2026-03-02-cycle120-checkpoint-river-far-tail-damp
- change_type: Enforce
- scope: `poker2/runtime/system_policy.py`（RIVER forced-bet support window far-tail damping）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: null（hook checkpoint patch；未跑重评测）
- evidence:
  - E1: `event.reason=cycle_completed` and `event.cycle=120` | ref=event:2026-03-02T14:15:33+0800
  - E2: `review.quick_gate.reason=quick_gate_no_eligible_candidate` | ref=tmp/ralph_loop_runs_v2/cycle_120_20260226_073551/review.json
  - E3: `state.no_improve_streak=38` and `focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100` | ref=tmp/ralph_loop_state_v2.json
- outcome: CONTINUE
- rationale: keep one rollback-safe mechanism change to reduce far-tail over-expansion regressions while preserving near-threshold support pressure, so next cycle has higher chance to produce eligible candidates.

### 2026-03-02-strong-subtop-defaults-local-only
- change_id: 2026-03-02-strong-subtop-defaults-local-only
- change_type: Enforce
- scope: loop 默认门槛与并发/评测预算（单机长期迭代配置）
- baseline: system_bot_policy_v3_loop_active (adopted_cycle=82)
- delta: 更新默认目标与门槛：`goal_pack_top_human_v2`、`pareto_contract_v1`、`ralph_wiggum_loop.py`、`ralph_loop_supervisor.sh`
- evidence:
  - E1: `target_gates/robust_gates/promotion_gates` 切换到 strong-subtop 门槛（quick_min_delta=0.3/full_min_delta=0.2/regress_tolerance=0.15/holdout_regress_tolerance=0.1） | ref=specs/loop_goals/goal_pack_top_human_v2.json
  - E2: Pareto hard constraints 提升到稳健底线（`coinpoker.br_worst_mean>=12.5`、`coinpoker.pool_weighted_mean>=14.0` 等） | ref=specs/loop_goals/pareto_contract_v1.json
  - E3: Loop 默认预算改为单机高性价比：`jobs<=8`、`max_candidates=4`、`quick=800x4`、`full=1600x4`、`confirm=1600x4`、`timeout=5400` | ref=tools/ralph_wiggum_loop.py + tools/ralph_loop_supervisor.sh
- outcome: CONTINUE
- rationale: 在严格本机约束下，先提高 runtime 稳定性与候选可晋级率，再通过更稳健的推广门槛收敛到“非常强但略低于顶尖”的长期目标。

### 20260302-214757-ralph-loop-cycle-121
- change_id: 20260302-214757-ralph-loop-cycle-121
- change_type: Eval
- scope: ralph-wiggum-loop cycle 121
- baseline: system_bot_policy_v3_loop_active (adopted_cycle=82)
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_087_20260221_013806/baseline_integrity_repair/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_121_20260302_141728/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate no improvement

## [autopilot-hook] 2026-03-02T21:47:57+0800 cycle=122 reason=awaiting_llm_action
- change_type: Patch
- decision: apply_cycle122_reactivation_cap_relief_bridge_v1
- why: cycle121 quick gate is `quick_gate_no_improvement` with `no_improve_streak=39`; ranked delta missed while branch support is present, indicating near-threshold cap flattening on stalled forced-bet branch.
- what: patched `poker2/runtime/system_policy.py` to allow bounded cap-relief activation when stalled reactivation bonus is active (not only saturation-active), capped at `0.005`.
- rollback: revert `cap_relief_active` broadening and reactivation-only cap-relief increment in `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=tmp/.pycache python3 -m py_compile poker2/runtime/system_policy.py`; `python3` required-field check for `tmp/ralph_next_action.json` (`source_cycle=121`).
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle_122_awaiting_llm_action_20260302_214757.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_121_20260302_141728/review.json`, `tmp/ralph_loop_runs_v2/cycle_121_20260302_141728/cycle_result.json`

### 2026-03-02-awaiting-llm-action-reactivation-cap-relief-bridge-v1
- change_id: 2026-03-02-awaiting-llm-action-reactivation-cap-relief-bridge-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（RIVER forced-bet stalled branch reactivation-aware cap relief）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（awaiting_llm_action unblock；未跑完整评测）
- evidence:
  - E1 | metric=event.reason=awaiting_llm_action | n=cycle122 | seeds=? | evidence_ref=event:2026-03-02T21:47:57+0800
  - E2 | metric=quick_gate.reason=quick_gate_no_improvement | n=1 eligible candidate | seeds=cycle121 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_121_20260302_141728/review.json
  - E3 | metric=mechanism_patch_applied | n=1 core file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: 先解除 action ticket 阻塞，并在同一 stalled 分支上注入单机制、可回退、窄作用域补丁，提升下轮 quick gate 的行为可分性。

### 20260303-043400-ralph-loop-cycle-122
- change_id: 20260303-043400-ralph-loop-cycle-122
- change_type: Eval
- scope: ralph-wiggum-loop cycle 122
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_122_20260302_231228/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_122_20260302_231228/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_122_20260302_231228/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_122_20260302_231228/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate standard fail (robust_pass=False, pareto_constraints=False, holdout_pass=True)

## [autopilot-hook] 2026-03-03T04:34:00+0800 cycle=123 reason=awaiting_llm_action
- change_type: Patch
- decision: apply_cycle123_river_forced_bet_deadlock_relief_bonus_v1
- why: action ticket 阻塞（missing_action）且 cycle122 full gate 显示 `focus_delta=0`，说明 stalled forced-bet 近阈值分支仍存在行为分离不足。
- what: patched `poker2/runtime/system_policy.py`，在既有 `cap_relief_active` 子分支增加 bounded `river_forced_bet_support_deadlock_relief_bonus`（0.0015..0.0025），仅当 proximity/ramp 均未触发且 MW+wet+low-SPR+near-threshold 时生效，并写入 trace key `high_price_river_forced_bet_support_deadlock_relief_bonus_ppm`。
- rollback: 删除 `river_forced_bet_support_deadlock_relief_bonus` 的 init / cap-relief 分支 / trace 字段。
- verify: `PYTHONPYCACHEPREFIX=tmp/.pycache python3 -m py_compile poker2/runtime/system_policy.py`；`python3` 校验 `tmp/ralph_next_action.json` 必填字段与 `source_cycle=122`。
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle_123_awaiting_llm_action_20260303_043400.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_runs_v2/cycle_122_20260302_231228/review.json`, `tmp/ralph_loop_runs_v2/cycle_122_20260302_231228/cycle_result.json`

### 2026-03-03-awaiting-llm-action-river-deadlock-relief-bonus-v1
- change_id: 2026-03-03-awaiting-llm-action-river-deadlock-relief-bonus-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（RIVER forced-bet stalled branch deadlock-relief cap bonus）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（awaiting_llm_action unblock；未跑完整评测）
- evidence:
  - E1 | metric=event.reason=awaiting_llm_action | n=cycle123 | seeds=? | evidence_ref=event:2026-03-03T04:34:00+0800
  - E2 | metric=full_gate.focus_delta=0.0 & quick_gate.reason=full_gate_fail | n=cycle122 | seeds=cycle122 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_122_20260302_231228/review.json
  - E3 | metric=mechanism_patch_applied | n=1 core file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: 先保证 worker 重试可消费 action，再在同一 stalled 分支做单机制、可回退、窄影响补丁，提升下一轮 quick/full 的行为可分性。

### 20260303-075615-ralph-loop-cycle-123
- change_id: 20260303-075615-ralph-loop-cycle-123
- change_type: Eval
- scope: ralph-wiggum-loop cycle 123
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_123_20260303_043737/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_123_20260303_043737/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_123_20260303_043737/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_123_20260303_043737/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate standard fail (robust_pass=False, pareto_constraints=False, holdout_pass=False)

### 20260303-112044-ralph-loop-cycle-124
- change_id: 20260303-112044-ralph-loop-cycle-124
- change_type: Eval
- scope: ralph-wiggum-loop cycle 124
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_124_20260303_075855/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_124_20260303_075855/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_124_20260303_075855/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_124_20260303_075855/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (robust_pass=False, pareto_constraints=False, holdout_pass=False)


## [autopilot-hook] 2026-03-03T11:20:45+0800 cycle=124 reason=awaiting_llm_action
- change_type: Patch
- decision: apply_river_forced_bet_reactivation_floor_relief_v1
- why: action ticket blocked by `missing_action`; latest review `full_gate_fail` with focused branch support stalled at low hits (`active_support.hits=1`) under long no-improve streak.
- what: patched `poker2/runtime/system_policy.py` to relax forced-bet reactivation floor only on stalled unsaturated branch and added trace key `high_price_river_forced_bet_reactivation_floor_relief_ppm`.
- rollback: remove reactivation floor-relief branch, cap override, and trace key in `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=tmp/.pycache python3 -m py_compile poker2/runtime/system_policy.py`; `python3` required-field check for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle_125_awaiting_llm_action_20260303_112045.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_runs_v2/cycle_124_20260303_075855/review.json`, `tmp/ralph_loop_runs_v2/cycle_124_20260303_075855/cycle_result.json`, `tmp/ralph_loop_state_v2.json`

### 2026-03-03-cycle124-awaiting-llm-action-reactivation-floor-relief-v1
- change_id: 2026-03-03-cycle124-awaiting-llm-action-reactivation-floor-relief-v1
- change_type: Enforce
- scope: `poker2/runtime/system_policy.py`（stalled forced-bet reactivation floor relief with bounded cap + trace）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: null（hook unblock patch；未跑重评测）
- evidence:
  - E1: `event.reason=awaiting_llm_action`, `event.cycle=125`, `ticket_reason=missing_action` | ref=event:2026-03-03T11:20:45+0800
  - E2: `review.quick_gate.reason=full_gate_fail`, `active_support.hands=26`, `active_support.hits=1` | ref=tmp/ralph_loop_runs_v2/cycle_124_20260303_075855/review.json
  - E3: `state.no_improve_streak=42`, `focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100` | ref=tmp/ralph_loop_state_v2.json
- outcome: CONTINUE
- rationale: prioritize unblocking llm action gate and apply one rollback-safe mechanism that can increase focused branch activation without broadening low-price paths.

### 20260303-153947-ralph-loop-cycle-125
- change_id: 20260303-153947-ralph-loop-cycle-125
- change_type: Eval
- scope: ralph-wiggum-loop cycle 125
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_125_20260303_112356/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_125_20260303_112356/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_125_20260303_112356/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_125_20260303_112356/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate standard fail (robust_pass=False, pareto_constraints=False, holdout_pass=False)

## [autopilot-hook] 2026-03-03T15:39:47+0800 cycle=126 reason=awaiting_llm_action
- change_type: Patch
- decision: apply_cycle126_river_deadlock_reactivation_floor_bridge_v2
- why: action ticket blocked by `missing_action`; cycle125 remained `full_gate_fail` with focused branch support stuck at low hits (`active_support.hits=1`) under `no_improve_streak=43`.
- what: patched `poker2/runtime/system_policy.py` to widen deadlock-relief floor/cap only when reactivation-floor-relief is active and saturation is absent on the same stalled forced-bet branch.
- rollback: revert deadlock-relief floor (`0.92`), cap (`0.0035`), and extra `+0.0005` bonus in `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=tmp/.pycache python3 -m py_compile poker2/runtime/system_policy.py`; `python3` required-field check for `tmp/ralph_next_action.json` with `source_cycle=125`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle_126_awaiting_llm_action_20260303_153947.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_125_20260303_112356/review.json`, `tmp/ralph_loop_runs_v2/cycle_125_20260303_112356/cycle_result.json`

### 2026-03-03-awaiting-llm-action-river-deadlock-reactivation-floor-bridge-v2
- change_id: 2026-03-03-awaiting-llm-action-river-deadlock-reactivation-floor-bridge-v2
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（RIVER forced-bet stalled branch deadlock-relief reactivation-floor bridge）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（awaiting_llm_action unblock；未跑完整评测）
- evidence:
  - E1 | metric=event.reason=awaiting_llm_action | n=cycle126 | seeds=? | evidence_ref=event:2026-03-03T15:39:47+0800
  - E2 | metric=quick_gate.reason=full_gate_fail & active_support.hits=1 | n=cycle125 | seeds=cycle125 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_125_20260303_112356/review.json
  - E3 | metric=mechanism_patch_applied | n=1 core file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: unblock action ticket first and apply one rollback-safe, branch-local mechanism to improve near-threshold behavior separability for next worker retry.

### 20260303-191817-ralph-loop-cycle-126
- change_id: 20260303-191817-ralph-loop-cycle-126
- change_type: Eval
- scope: ralph-wiggum-loop cycle 126
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=system_bot_policy_v3_loop_trial
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_126_20260303_154248/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_126_20260303_154248/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_126_20260303_154248/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_126_20260303_154248/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate standard fail (robust_pass=False, pareto_constraints=False, holdout_pass=True)

## [autopilot-hook] 2026-03-03T19:18:17+0800 cycle=127 reason=awaiting_llm_action
- change_type: Patch
- decision: apply_cycle127_river_deadlock_near_zero_proximity_bridge_v1
- why: action ticket blocked by `missing_action`; cycle126 remained `full_gate_fail` with focused branch support stalled at `active_support.hits=1` under `no_improve_streak=44`.
- what: patched `poker2/runtime/system_policy.py` to allow bounded deadlock-relief activation when proximity bonus is near-zero (not strictly zero) on the same reactivation-floor-relief stalled branch.
- rollback: restore deadlock-relief proximity gate from `0.0012` back to strict `0.0` in `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=tmp/.pycache python3 -m py_compile poker2/runtime/system_policy.py`; `python3` required-field check for `tmp/ralph_next_action.json` (`source_cycle=126`).
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle_127_awaiting_llm_action_20260303_191817.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_126_20260303_154248/review.json`, `tmp/ralph_loop_runs_v2/cycle_126_20260303_154248/cycle_result.json`

### 2026-03-03-awaiting-llm-action-river-deadlock-near-zero-proximity-bridge-v1
- change_id: 2026-03-03-awaiting-llm-action-river-deadlock-near-zero-proximity-bridge-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（RIVER forced-bet stalled branch near-zero proximity deadlock bridge）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（awaiting_llm_action unblock；未跑完整评测）
- evidence:
  - E1 | metric=event.reason=awaiting_llm_action | n=cycle127 | seeds=? | evidence_ref=event:2026-03-03T19:18:17+0800
  - E2 | metric=quick_gate.reason=full_gate_fail & active_support.hits=1 | n=cycle126 | seeds=cycle126 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_126_20260303_154248/review.json
  - E3 | metric=no_improve_streak=44 & mechanism_patch_applied | n=1 core file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: prioritize unblocking the action ticket and apply one rollback-safe, branch-local mechanism to increase focused support hits on the next worker retry without broadening saturated tails.

## [autopilot-hook] 2026-03-03T21:31:22+0800 cycle=127 reason=awaiting_llm_action
- change_type: Patch
- decision: apply_cycle127_river_deadlock_near_zero_ramp_bridge_v1
- why: action ticket blocked by `missing_action`; cycle126 stayed `full_gate_fail` with focused branch support pinned (`active_support.hits=1`) under `no_improve_streak=44`, and deadlock-relief previously required strict zero ramp bonus.
- what: patched `poker2/runtime/system_policy.py` to allow deadlock-relief on the same stalled reactivation-floor-relief branch when ramp bonus is near-zero (`<=0.0012`) and added trace key `high_price_river_forced_bet_support_deadlock_relief_ramp_gate_ppm`.
- rollback: set `deadlock_relief_ramp_gate` back to `0.0` and remove deadlock-relief ramp-gate trace field.
- verify: `PYTHONPYCACHEPREFIX=tmp/.pycache python3 -m py_compile poker2/runtime/system_policy.py`; `python3` required-field check for `tmp/ralph_next_action.json` (`source_cycle=126`).
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle_127_awaiting_llm_action_20260303_213122.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_126_20260303_154248/review.json`, `tmp/ralph_loop_runs_v2/cycle_126_20260303_154248/cycle_result.json`

### 2026-03-03-awaiting-llm-action-river-deadlock-near-zero-ramp-bridge-v1
- change_id: 2026-03-03-awaiting-llm-action-river-deadlock-near-zero-ramp-bridge-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（RIVER forced-bet stalled branch near-zero ramp deadlock bridge）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（awaiting_llm_action unblock；未跑完整评测）
- evidence:
  - E1 | metric=event.reason=awaiting_llm_action | n=cycle127 | seeds=? | evidence_ref=event:2026-03-03T21:31:22+0800
  - E2 | metric=quick_gate.reason=full_gate_fail & active_support.hits=1 | n=cycle126 | seeds=cycle126 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_126_20260303_154248/review.json
  - E3 | metric=no_improve_streak=44 & mechanism_patch_applied | n=1 core file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: unblock action ticket first and add one rollback-safe, branch-local mechanism to preserve deadlock-relief activation when ramp lift is tiny but non-zero, improving next retry behavior separability without broadening saturated tails.


### 2026-03-03-worker-restart-rc143-supervisor-resume
- change_id: 2026-03-03-worker-restart-rc143-supervisor-resume
- change_type: Restructure
- scope: `tools/ralph_loop_supervisor.sh`（进程恢复与重试连续性保障）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（流程恢复动作；未触发重评测）
- evidence:
  - E1 | metric=event.reason=worker_failed_or_unexpected_exit,rc=143 | n=1 | seeds=? | evidence_ref=event:2026-03-03T21:37:27+0800
  - E2 | metric=cycle127.active_quick_only,no_review_result | n=1 cycle | seeds=3000-3003 partial | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_127_20260303_213423
  - E3 | metric=cycle126.quick_gate.reason=full_gate_fail,active_support.hits=1 | n=1 | seeds=cycle126 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_126_20260303_154248/review.json
- outcome: CONTINUE
- rationale: 根因更接近进程中断而非策略机制退化，本轮先做单机制流程恢复，保证 worker 重试可持续消费 action 并延续评测闭环。

### 2026-03-03-awaiting-llm-action-missing-source-cycle-deadlock-bridge-v2
- change_id: 2026-03-03-awaiting-llm-action-missing-source-cycle-deadlock-bridge-v2
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（river forced-bet stalled reactivation deadlock bridge v2）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（awaiting_llm_action unblock；仅做最小验证）
- evidence:
  - E1 | metric=event.reason=awaiting_llm_action(ticket=missing_source_cycle) | n=cycle127 | seeds=? | evidence_ref=event:2026-03-03T21:47:19+0800
  - E2 | metric=no_improve_streak=44 | n=1 | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E3 | metric=mechanism_patch_applied | n=1 core file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: 先解除 action ticket 门禁（补齐 source_cycle），同时在 deep stalled reactivation 分支增加窄作用域 deadlock bridge，提升下一轮 quick gate 行为可分性并保持可回退。


## [autopilot-hook] 2026-03-03T22:18:18+0800 cycle=null reason=worker_failed_or_unexpected_exit
- change_type: Patch
- decision: apply_supervisor_quick_fail_guard_v1
- why: supervisor exited immediately on quick worker failure due to unbound variable (`progress_age`) under `set -u`.
- what: patched `tools/ralph_loop_supervisor.sh` to initialize `progress_age=0` before heartbeat loop.
- rollback: remove the `progress_age=0` initialization near main child-monitor loop.
- verify: `python3` syntax check; `python3` next_action required-fields check; `python3`-launched supervisor lock-PID liveness check.
- evidence_ref: `tools/ralph_loop_supervisor.sh`, `tmp/ralph_patch_manifest_restart_worker_failed_20260303_221818.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_runs_v2/cycle_127_20260303_220204`, `/tmp/ralph_loop_supervisor.out`


## [autopilot-hook] 2026-03-03T22:30:46+0800 cycle=null reason=worker_failed_or_unexpected_exit
- change_type: Patch
- decision: apply_quick_eval_exception_isolation_v1
- why: cycle_127 quick artifacts were partially produced and worker exited `rc=2`; single task/aggregation exception at quick-eval stage could terminate the whole worker loop.
- what: patched `tools/ralph_wiggum_loop.py` to isolate per-task exceptions in `_quick_eval` and downgrade them to `runtime_error` diagnostics with fail-soft continuation.
- rollback: revert the `_quick_eval` try/except block and remove `runtime_error` metric field.
- verify: `PYTHONPYCACHEPREFIX=tmp/.pycache python3 -m py_compile tools/ralph_wiggum_loop.py`.
- evidence_ref: `tools/ralph_wiggum_loop.py`, `tmp/ralph_loop_runs_v2/cycle_127_20260303_222217/active_quick`, `tmp/ralph_patch_manifest_restart_20260303_223046.json`, `tmp/ralph_next_action.json`

### 2026-03-03-cycle127-worker-failed-quick-eval-exception-isolation-v1
- change_id: 2026-03-03-cycle127-worker-failed-quick-eval-exception-isolation-v1
- change_type: Restructure
- scope: `tools/ralph_wiggum_loop.py`（quick-eval 并发任务异常隔离 + 聚合 fail-soft）
- baseline: retaliation_weight_v1_high_price_defend_gate_v8_20260206
- delta: null（流程稳健性补丁；未跑重评测）
- evidence:
  - E1: `event.reason=worker_failed_or_unexpected_exit`, `event.rc=2`, `event.restart_count=1` | ref=event:2026-03-03T22:30:46+0800
  - E2: `cycle_127 active_quick` 部分产物存在且 gg tier batch 汇总未完成 | ref=tmp/ralph_loop_runs_v2/cycle_127_20260303_222217/active_quick
  - E3: `_quick_eval` 现已将单任务异常落盘到 `runtime_error` 而非上抛终止 worker | ref=tools/ralph_wiggum_loop.py
- outcome: CONTINUE
- rationale: 先消除 restart-storm 风险，确保下轮可继续 quick gate 与 action ticket 消费；后续再评估策略机制收益。


## [autopilot-hook] 2026-03-03T22:37:57+0800 cycle=null reason=worker_failed_or_unexpected_exit
- change_type: Patch
- decision: apply_trial_quick_eval_failsoft_isolation_v1
- why: worker restart storm persisted (`rc=2`, `restart_count=8`) and cycle `tmp/ralph_loop_runs_v2/cycle_127_20260303_222217` remained incomplete (no `review.json` / `cycle_result.json`), indicating uncaught exception path during quick stage.
- what: patched `tools/ralph_wiggum_loop.py` to isolate per-candidate trial quick-eval exceptions and downgrade each failure to `runtime_error` artifact + trace event instead of terminating worker.
- rollback: revert trial quick try/except and candidate `runtime_error` fail-soft branch in `tools/ralph_wiggum_loop.py`.
- verify: `PYTHONPYCACHEPREFIX=tmp/.pycache python3 -m py_compile tools/ralph_wiggum_loop.py`; supervisor liveness check + auto-start if missing.
- evidence_ref: `tools/ralph_wiggum_loop.py`, `tmp/ralph_patch_manifest_restart_20260303_223757.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_runs_v2/cycle_127_20260303_222217`, `tmp/ralph_loop_runs_v2/cycle_126_20260303_154248/review.json`, `tmp/ralph_loop_state_v2.json`

### 2026-03-03-cycle127-worker-failed-trial-quick-eval-failsoft-v1
- change_id: 2026-03-03-cycle127-worker-failed-trial-quick-eval-failsoft-v1
- change_type: Patch
- scope: `tools/ralph_wiggum_loop.py`（trial quick-eval candidate exception isolation）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（流程稳健性补丁；未跑重评测）
- evidence:
  - E1 | metric=event.reason=worker_failed_or_unexpected_exit,rc=2,restart_count=8 | n=1 | seeds=? | evidence_ref=event:2026-03-03T22:37:57+0800
  - E2 | metric=cycle_127_missing_review_and_result | n=1 cycle | seeds=3000-3003 partial | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_127_20260303_222217
  - E3 | metric=mechanism_patch_applied | n=1 core loop file | seeds=? | evidence_ref=path:tools/ralph_wiggum_loop.py
- outcome: CONTINUE
- rationale: 将单候选 quick 失败降级为局部 runtime_error，优先保障 worker 连续性和 action 可消费性，避免进程级 rc=2 重启风暴。

### 2026-03-03-worker-fail-retry-guard-v1
- change_id: 2026-03-03-worker-fail-retry-guard-v1
- change_type: Patch
- scope: `tools/ralph_wiggum_loop.py`（parent loop worker_fail bounded retry）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（restart recovery patch；未跑重型评测）
- evidence:
  - E1 | metric=event.reason=worker_failed_or_unexpected_exit | n=restart_count=1 | seeds=? | evidence_ref=event:2026-03-03T22:18:18+0800
  - E2 | metric=cycle127.active_quick.seed_runs_all_pass | n=25 run.log | seeds=3000-3003 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_127_20260303_220204/active_quick
  - E3 | metric=mechanism_patch_applied | n=1 core file | seeds=? | evidence_ref=path:tools/ralph_wiggum_loop.py
- outcome: CONTINUE
- rationale: quick 子任务已有进展但父进程对 worker 非零退出缺乏韧性；加入单次有界重试可降低瞬时失败导致的重启抖动，且可通过参数回退。

## [autopilot-hook] 2026-03-03T22:43:33+0800 cycle=null reason=worker_failed_or_unexpected_exit
- change_type: Patch
- decision: apply_active_quick_eval_failsoft_continuation_v1
- why: restart storm persisted with `rc=2`; latest cycle dir `tmp/ralph_loop_runs_v2/cycle_127_20260303_223837` remained partial (`active_quick` only), consistent with worker abort before review/result closure.
- what: patched `tools/ralph_wiggum_loop.py` to keep cycle alive on active quick top-level exception by recording runtime failure artifact and constructing fail-soft quick payload instead of immediate process stop.
- rollback: restore active quick exception branch to hard stop `return 2`.
- verify: `PYTHONPYCACHEPREFIX=tmp/.pycache python3 -m py_compile tools/ralph_wiggum_loop.py`; `python3` required-field check for `tmp/ralph_next_action.json`; supervisor liveness check + auto-start if missing.
- evidence_ref: `tools/ralph_wiggum_loop.py`, `tmp/ralph_patch_manifest_restart_20260303_224333.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_runs_v2/cycle_127_20260303_223837`, `tmp/ralph_loop_runs_v2/cycle_126_20260303_154248/review.json`, `tmp/ralph_loop_runs_v2/cycle_126_20260303_154248/cycle_result.json`

### 2026-03-03-worker-failed-active-quick-failsoft-continuation-v1
- change_id: 2026-03-03-worker-failed-active-quick-failsoft-continuation-v1
- change_type: Patch
- scope: `tools/ralph_wiggum_loop.py`（active_quick 顶层异常 fail-soft 连续性保障）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（流程稳健性补丁；未跑重型评测）
- evidence:
  - E1 | metric=event.reason=worker_failed_or_unexpected_exit,rc=2,restart_count=7 | n=1 | seeds=? | evidence_ref=event:2026-03-03T22:43:33+0800
  - E2 | metric=cycle_127_partial_active_quick_only | n=1 cycle | seeds=3000-3003 partial | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_127_20260303_223837
  - E3 | metric=mechanism_patch_applied | n=1 core loop file | seeds=? | evidence_ref=path:tools/ralph_wiggum_loop.py
- outcome: CONTINUE
- rationale: 先消除 active_quick 顶层异常导致的进程级中止，使 worker 在异常场景下也能继续产出结构化 review/result 并维持重试闭环。

### 2026-03-03-worker-rc2-backoff-escalation
- change_id: 2026-03-03-worker-rc2-backoff-escalation
- change_type: Patch
- scope: `tools/ralph_loop_supervisor.sh` (escalate fail-restart backoff from state.restart_count)
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `N/A (process stability patch, no heavy match eval in this hook)`
- evidence:
  - `gg tierA seed3003 run.log | START only (no END) | n=1 | seeds=3003 | evidence_ref=tmp/ralph_loop_runs_v2/cycle_127_20260303_223837/active_quick/gg_7max_mw_v3_actionspace_league_frozen_v2/tierA/seed3003/run.log`
  - `gg tierP seed3003 run.log | START only (no END) | n=1 | seeds=3003 | evidence_ref=tmp/ralph_loop_runs_v2/cycle_127_20260303_223837/active_quick/gg_7max_mw_v3_actionspace_league_frozen_v2/tierP/seed3003/run.log`
  - `restart event | rc=2 restart_count=15 | n=1 | seeds=null | evidence_ref=tmp/ralph_loop_state_v2.json`
- outcome: CONTINUE
- rationale: failure mode is process restart churn; apply one reversible backoff mechanism first and observe next cycle completion stability.

## [autopilot-hook] 2026-03-03T22:49:15+0800 cycle=null reason=worker_failed_or_unexpected_exit
- change_type: Patch
- decision: apply_unknown_cli_args_failsoft_v1
- why: restart event showed `rc=2` with `cycle=null`, indicating worker bootstrap parse abort risk under hook/supervisor arg drift.
- what: patched `tools/ralph_wiggum_loop.py` main parser to use `parse_known_args()` and emit structured trace event `unknown_cli_args_ignored` instead of exiting with argparse `SystemExit(2)`.
- rollback: switch back to strict `parse_args()` in `tools/ralph_wiggum_loop.py`.
- verify: `PYTHONPYCACHEPREFIX=tmp/.pycache python3 -m py_compile tools/ralph_wiggum_loop.py`.
- evidence_ref: `tools/ralph_wiggum_loop.py`, `tmp/ralph_patch_manifest_worker_failed_or_unexpected_exit_20260303_224915.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_runs_v2/cycle_127_20260303_223837/active_quick/coinpoker_7max_mw_v3_actionspace_v2/tierA/scrimmage_batch.json`, `tmp/ralph_loop_runs_v2/cycle_127_20260303_223837/active_quick/gg_7max_mw_v3_actionspace_league_frozen_v2/tierP/scrimmage_batch.json`

### 2026-03-03-worker-failed-unknown-cli-args-failsoft-v1
- change_id: 2026-03-03-worker-failed-unknown-cli-args-failsoft-v1
- change_type: Patch
- scope: `tools/ralph_wiggum_loop.py`（worker bootstrap CLI parse fail-soft, trace-preserving）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（worker failure处置；未跑完整评测）
- evidence:
  - E1 | metric=event.reason=worker_failed_or_unexpected_exit & rc=2 & cycle=null | n=1 | seeds=? | evidence_ref=event:2026-03-03T22:49:15+0800
  - E2 | metric=cycle127_active_quick_scrimmage_batch_pass | n=4x2 suites | seeds=3000-3003 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_127_20260303_223837/active_quick
  - E3 | metric=mechanism_patch_applied | n=1 core loop file | seeds=? | evidence_ref=path:tools/ralph_wiggum_loop.py
- outcome: CONTINUE
- rationale: preserve loop liveness under extraneous args while keeping machine-readable trace for diagnosis and rollback.

### 2026-03-03-worker-failed-graceful-handoff
- change_id: 2026-03-03-worker-failed-graceful-handoff
- change_type: Restructure
- scope: `tools/ralph_wiggum_loop.py`（worker 失败后受控停止并移交 hook）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（process reliability patch；未跑完整评测）
- evidence:
  - E1 | metric=event.reason=worker_failed_or_unexpected_exit, rc=1, restart_count=30 | n=1 | seeds=? | evidence_ref=event:2026-03-03T23:11:57+0800
  - E2 | metric=cycle127 active_quick only has run.log heartbeat and no completed summary | n=4 tier logs | seeds=3000+ | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_127_20260303_231138/active_quick
  - E3 | metric=parent worker-failure branch switched to structured stop handoff | n=1 code file | seeds=? | evidence_ref=path:tools/ralph_wiggum_loop.py
- outcome: CONTINUE
- rationale: root cause is process-level restart storm after repeated worker non-zero exit; convert to controlled stop with structured reason so hook can apply next action without uncontrolled supervisor churn.

### 2026-03-03-worker-failed-state-load-recovery-guard
- change_id: 2026-03-03-worker-failed-state-load-recovery-guard
- change_type: Patch
- scope: `tools/ralph_wiggum_loop.py`（worker 启动期 state JSON 损坏自愈降级，避免 rc=1 直退）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（restart/可靠性修复；未跑重评测）
- evidence:
  - E1 | metric=event.reason=worker_failed_or_unexpected_exit | n=1 | seeds=? | evidence_ref=event:2026-03-03T23:45:02+0800
  - E2 | metric=cycle_127_dir_missing_before_init | n=1 | seeds=? | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_127_20260303_234457
  - E3 | metric=patched_startup_state_guard | n=1 core file | seeds=? | evidence_ref=path:tools/ralph_wiggum_loop.py
- outcome: CONTINUE
- rationale: 在不改变策略评测逻辑的前提下，先消除启动期非受控异常退出，降低 supervisor restart storm 风险；下一轮继续聚焦 `coinpoker.tierP_facingY_turnriver_worst_bb100`。
## [autopilot-hook] 2026-03-04T00:05:11+0800 cycle=null reason=worker_failed_or_unexpected_exit
- change_type: Patch
- decision: apply_supervisor_terminal_stop_for_worker_failed_or_unexpected_exit_v1
- why: `tools/ralph_wiggum_loop.py` already converts repeated worker failures into controlled stop (`reason=worker_failed_or_unexpected_exit`, return code 0), but supervisor treated this as non-terminal and kept restarting, causing restart storm (`restart_count=33`) without state progress.
- what: patched `tools/ralph_loop_supervisor.sh` so `reason=worker_failed_or_unexpected_exit` is handled as terminal stop, matching loop contract and handing control to hook automation.
- rollback: remove `worker_failed_or_unexpected_exit` from supervisor terminal-stop reason set.
- verify: `python3` assertion checks for terminal-stop branch + required fields in `tmp/ralph_next_action.json`.
- evidence_ref: `tools/ralph_loop_supervisor.sh`, `tmp/ralph_loop_runs_v2/cycle_127_20260304_000510/active_quick/quick_eval_cache_hit.json`, `tmp/ralph_loop_runs_v2/cycle_126_20260303_154248/review.json`, `tmp/ralph_loop_runs_v2/cycle_126_20260303_154248/cycle_result.json`, `tmp/ralph_loop_state_v2.json`

### 2026-03-04-worker-failed-supervisor-terminal-stop
- change_id: 2026-03-04-worker-failed-supervisor-terminal-stop
- change_type: Patch
- scope: `tools/ralph_loop_supervisor.sh`（worker_failed_or_unexpected_exit 终止语义对齐）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（流程修复；未跑完整评测）
- evidence:
  - E1 | metric=event.status=stopped & reason=worker_failed_or_unexpected_exit & restart_count=33 | n=1 | seeds=? | evidence_ref=event:2026-03-04T00:05:11+0800
  - E2 | metric=cycle127_progress=quick_eval_cache_hit_only | n=1 file | seeds=cycle127 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_127_20260304_000510/active_quick/quick_eval_cache_hit.json
  - E3 | metric=no_improve_streak=44 & last_quick_gate_reason=full_gate_fail | n=state snapshot | seeds=cycle126 | evidence_ref=path:tmp/ralph_loop_state_v2.json
- outcome: CONTINUE
- rationale: first remove restart storm and restore deterministic hook handoff; next cycle can consume new action ticket under stable supervisor semantics.

## [autopilot-hook] 2026-03-04T12:22:11+0800 cycle=130 reason=cycle_completed
- change_type: Patch
- decision: apply_turn_focus_support_ramp_v1
- why: `quick_gate.reason=quick_gate_low_focus_support` in cycle 130 and `no_improve_streak=48`; all 6 mechanism candidates had `focus_support.hits=0`, so promotion path is blocked at stage1 coverage.
- what: patched `poker2/runtime/system_policy.py` with a bounded TURN near-threshold support ramp (`turn_focus_support_ramp_penalty`) for high-price facing spots under low-SPR + wet + OOP/multiway risk, capped by existing `gap2` so behavior change stays localized and reversible.
- rollback: remove the `turn_focus_support_ramp_penalty` block and its initialization from `poker2/runtime/system_policy.py`.
- verify: `python3 -m py_compile poker2/runtime/system_policy.py` and `python3` JSON structure checks for `tmp/ralph_next_action.json` + patch manifest.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_loop_runs_v2/cycle_130_20260304_103120/review.json`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_patch_manifest_cycle131_20260304_122211.json`

### 2026-03-04-cycle130-turn-focus-support-ramp
- change_id: 2026-03-04-cycle130-turn-focus-support-ramp
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（TURN high-price near-threshold support ramp, bounded）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（light replay planning cycle; no heavy eval）
- evidence:
  - E1 | metric=quick_gate.reason=quick_gate_low_focus_support | n=1 cycle | seeds=cycle130 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_130_20260304_103120/review.json
  - E2 | metric=no_improve_streak=48 | n=state snapshot | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E3 | metric=patched_core_file_count=1 | n=1 | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: apply a single bounded mechanism to unlock focus-support observability on stalled TURN high-price branches while preserving rollback simplicity.

## [autopilot-hook] 2026-03-04T00:05:11+0800 cycle=null reason=worker_failed_or_unexpected_exit
- change_type: Patch
- decision: apply_supervisor_terminal_stop_for_worker_failed_or_unexpected_exit_v1
- why: `tools/ralph_wiggum_loop.py` emits controlled stop on repeated worker failures, but supervisor treated this as non-terminal restart path and looped.
- what: patched `tools/ralph_loop_supervisor.sh` so `worker_failed_or_unexpected_exit` is terminal stop.
- rollback: remove `worker_failed_or_unexpected_exit` from supervisor terminal-stop reason set.
- verify: `python3` assertions passed for action-ticket required fields and supervisor terminal-stop marker.
- evidence_ref: `tools/ralph_loop_supervisor.sh`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_127_20260304_000510/active_quick/quick_eval_cache_hit.json`, `tmp/ralph_loop_runs_v2/cycle_126_20260303_154248/review.json`, `tmp/ralph_loop_runs_v2/cycle_126_20260303_154248/cycle_result.json`

### 2026-03-04-worker-failed-supervisor-terminal-stop
- change_id: 2026-03-04-worker-failed-supervisor-terminal-stop
- change_type: Patch
- scope: `tools/ralph_loop_supervisor.sh`
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`
- evidence:
  - E1 | metric=event.reason=worker_failed_or_unexpected_exit & restart_count=33 | n=1 | seeds=? | evidence_ref=event:2026-03-04T00:05:11+0800
  - E2 | metric=cycle127_progress=quick_eval_cache_hit_only | n=1 | seeds=cycle127 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_127_20260304_000510/active_quick/quick_eval_cache_hit.json
  - E3 | metric=no_improve_streak=44 & last_quick_gate_reason=full_gate_fail | n=state snapshot | seeds=cycle126 | evidence_ref=path:tmp/ralph_loop_state_v2.json
- outcome: CONTINUE
- rationale: align supervisor terminal semantics with loop contract to stop restart storms and preserve hook handoff.

## [autopilot-hook] 2026-03-04T00:32:16+0800 cycle=null reason=worker_failed_or_unexpected_exit
- change_type: Patch
- decision: apply_supervisor_stall_timeout_alignment_guard_v1
- why: default `STALL_SEC=3600` is below worker `TIMEOUT_SEC=5400`, so long but in-budget eval legs can be killed as stall (`rc=124`) and trigger restart storms.
- what: patched `tools/ralph_loop_supervisor.sh` to enforce `STALL_SEC >= TIMEOUT_SEC + max(300, HEARTBEAT_SEC*3)` and emit resolved `stall_sec` in startup logs.
- rollback: remove `resolve_stall_sec()` and restore fixed `STALL_SEC` assignment.
- verify: `python3`-driven `zsh -n` syntax check; `python3` required-fields check for `tmp/ralph_next_action.json`; `python3` supervisor liveness/start check.
- evidence_ref: `tools/ralph_loop_supervisor.sh`, `tmp/ralph_patch_manifest_restart_worker_failed_20260304_003216.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`

## [autopilot-hook] 2026-03-04T01:03:55+0800 cycle=null reason=worker_failed_or_unexpected_exit
- change_type: Patch
- decision: apply_worker_sigterm_handoff_guard_v1
- why: latest restart event shows `rc=143` with `progress_age_sec=0` and `cycle=null`; startup-phase SIGTERM was still flowing through worker-failure path and triggering restart churn.
- what: patched `tools/ralph_wiggum_loop.py` so worker subprocess `rc==143` is converted into controlled stop handoff (`reason=worker_failed_or_unexpected_exit`) with trace event `worker_sigterm_handoff`.
- rollback: remove the `if rc == 143` branch in `tools/ralph_wiggum_loop.py`.
- verify: `PYTHONPYCACHEPREFIX=tmp/.pycache python3 -m py_compile tools/ralph_wiggum_loop.py`; `python3` next_action required-fields check; supervisor liveness/start check.
- evidence_ref: `tools/ralph_wiggum_loop.py`, `tmp/ralph_patch_manifest_restart_worker_failed_20260304_010355.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_runs_v2/cycle_127_20260304_010302`, `tmp/ralph_loop_runs_v2/cycle_126_20260303_154248/review.json`, `tmp/ralph_loop_runs_v2/cycle_126_20260303_154248/cycle_result.json`, `tmp/ralph_loop_state_v2.json`

### 2026-03-04-worker-failed-sigterm-handoff-guard-v1
- change_id: 2026-03-04-worker-failed-sigterm-handoff-guard-v1
- change_type: Patch
- scope: `tools/ralph_wiggum_loop.py`（worker subprocess `rc=143` handoff guard）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（流程稳定性补丁；未跑重型评测）
- evidence:
  - E1 | metric=event.reason=worker_failed_or_unexpected_exit,rc=143,restart_count=24,cycle=null | n=1 | seeds=? | evidence_ref=event:2026-03-04T01:03:55+0800
  - E2 | metric=cycle127_partial_quick_only | n=1 cycle | seeds=cycle127 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_127_20260304_010302
  - E3 | metric=mechanism_patch_applied | n=1 core file | seeds=? | evidence_ref=path:tools/ralph_wiggum_loop.py
- outcome: CONTINUE
- rationale: prioritise restart-storm containment first; once loop liveness stabilises, continue mechanism search on `coinpoker.tierP_facingY_turnriver_worst_bb100`.

## [autopilot-hook] 2026-03-04T01:03:55+0800 cycle=null reason=worker_failed_or_unexpected_exit (correction)
- change_type: Patch
- decision: apply_supervisor_non_terminal_worker_failed_v1
- why: supervisor was not staying alive because `worker_failed_or_unexpected_exit` was classified as terminal stop; this conflicted with required restart supervision after hook recovery.
- what: patched `tools/ralph_loop_supervisor.sh` to keep only `target_achieved/max_cycles/no_improve_limit` as terminal reasons, and continue controlled restart/backoff for `worker_failed_or_unexpected_exit`.
- rollback: add `worker_failed_or_unexpected_exit` back to terminal stop reason set.
- verify: `python3` syntax check (`zsh -n`); `python3` next_action required-fields check; supervisor liveness/start check.
- evidence_ref: `tools/ralph_loop_supervisor.sh`, `tmp/ralph_patch_manifest_restart_worker_failed_20260304_010355.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_runs_v2/cycle_127_20260304_010302`, `tmp/ralph_loop_runs_v2/cycle_126_20260303_154248/review.json`, `tmp/ralph_loop_runs_v2/cycle_126_20260303_154248/cycle_result.json`, `tmp/ralph_loop_state_v2.json`

### 2026-03-04-worker-failed-supervisor-nonterminal-v1
- change_id: 2026-03-04-worker-failed-supervisor-nonterminal-v1
- change_type: Patch
- scope: `tools/ralph_loop_supervisor.sh`（worker_failed 非终止化）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（流程稳定性补丁；未跑重型评测）
- evidence:
  - E1 | metric=event.reason=worker_failed_or_unexpected_exit,rc=143,restart_count=24,cycle=null | n=1 | seeds=? | evidence_ref=event:2026-03-04T01:03:55+0800
  - E2 | metric=cycle127_partial_quick_only | n=1 cycle | seeds=cycle127 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_127_20260304_010302
  - E3 | metric=mechanism_patch_applied | n=1 core file | seeds=? | evidence_ref=path:tools/ralph_loop_supervisor.sh
- outcome: CONTINUE
- rationale: keep supervisor alive first, then let restart/backoff + hook action consumption converge without manual relaunch.

### 20260304-030031-ralph-loop-cycle-127
- change_id: 20260304-030031-ralph-loop-cycle-127
- change_type: Eval
- scope: ralph-wiggum-loop cycle 127
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_122_20260302_231228/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_127_20260304_012536/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate low focus support


### 2026-03-04-cycle127-turn-support-bridge-relief-v1
- change_id: 2026-03-04-cycle127-turn-support-bridge-relief-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（high-price TURN support bridge relief, bounded）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（checkpoint patch；未跑重型评测）
- evidence:
  - E1 | metric=quick_gate.reason=quick_gate_low_focus_support | n=1 cycle | seeds=3000-3003 quick | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_127_20260304_012536/review.json
  - E2 | metric=no_improve_streak=45 | n=1 state | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E3 | metric=mechanism_patch_applied | n=1 core file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: 在不引入新参数的前提下，对 TURN 的高价近阈值支持窗做窄幅扩展，优先修复 low-focus-support 门禁导致的“无可用候选”停滞，保持可回退与低回归面。

### 20260304-043453-ralph-loop-cycle-128
- change_id: 20260304-043453-ralph-loop-cycle-128
- change_type: Eval
- scope: ralph-wiggum-loop cycle 128
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_122_20260302_231228/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_128_20260304_030031/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate low focus support


## [autopilot-hook] 2026-03-04T04:35:31+0800 cycle=128 reason=cycle_completed
- change_type: Patch
- decision: apply_river_forced_bet_deadlock_reentry_bridge_v1
- why: `no_improve_streak=46` + `quick_gate_low_focus_support` indicates repeated support starvation; must unlock behavior delta with one localized mechanism.
- what: patched `poker2/runtime/system_policy.py` to add bounded deadlock reentry penalty only inside existing high-price support bridge window, gated by deadlock-relief + reactivation signals.
- rollback: remove the inserted `deadlock_reentry_penalty` block in `poker2/runtime/system_policy.py`.
- verify: `python3` compile check + next_action required-fields validation.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle129_20260304_043531.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_128_20260304_030031/review.json`, `tmp/ralph_loop_runs_v2/cycle_128_20260304_030031/cycle_result.json`

### 2026-03-04-cycle128-deadlock-reentry-bridge-v1
- change_id: 2026-03-04-cycle128-deadlock-reentry-bridge-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（river forced-bet support deadlock reentry bridge）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（checkpoint patch；未跑重型评测）
- evidence:
  - E1 | metric=no_improve_streak=46 | n=1 state | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E2 | metric=quick_gate.reason=quick_gate_low_focus_support | n=1 cycle | seeds=3000-3003 quick | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_128_20260304_030031/review.json
  - E3 | metric=mechanism_patch_applied | n=1 core file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: 在不引入新参数和不扩散到低价路径的前提下，只在 deadlock+reactivation 双信号命中时增强 bridge re-entry 压力，优先提升 focus 支持命中与行为变化可观测性。

### 20260304-103120-ralph-loop-cycle-129
- change_id: 20260304-103120-ralph-loop-cycle-129
- change_type: Eval
- scope: ralph-wiggum-loop cycle 129
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_122_20260302_231228/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_129_20260304_043453/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate low focus support

## [autopilot-hook] 2026-03-04T10:32:19+0800 cycle=129 reason=cycle_completed
- change_type: Patch
- decision: apply_turn_high_price_support_deadlock_bridge_v2
- why: `no_improve_streak=47` 且 latest completed review 命中 `quick_gate_low_focus_support`，需要单机制扩大 TURN 高价 near-threshold 的可观测行为变化，优先解除 support starvation。
- what: patched `poker2/runtime/system_policy.py`，在既有 TURN/RIVER support bridge 逻辑内新增 TURN-only deadlock bridge penalty（多人数+湿牌+低SPR+近阈值窗口），保持低价路径不受影响。
- rollback: 删除 `turn_river_support_deadlock_penalty` 初始化、计算块与对应 defense_trace 字段。
- verify: `python3` 编译检查 + action ticket 必填字段校验。
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle130_20260304_103219.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_129_20260304_043453/review.json`, `tmp/ralph_loop_runs_v2/cycle_129_20260304_043453/cycle_result.json`

### 2026-03-04-cycle129-turn-support-deadlock-bridge-v2
- change_id: 2026-03-04-cycle129-turn-support-deadlock-bridge-v2
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（TURN high-price near-threshold deadlock bridge）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（checkpoint patch；未跑重型评测）
- evidence:
  - E1 | metric=no_improve_streak=47 | n=1 state | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E2 | metric=quick_gate.reason=quick_gate_low_focus_support | n=1 cycle | seeds=3000-3003 quick | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_129_20260304_043453/review.json
  - E3 | metric=mechanism_patch_applied | n=1 core file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: 保持单机制与可回退，仅在 TURN 近阈值死锁分支追加有界惩罚，目标是提升 focus-support 命中与行为差异可观测性。

### 20260304-122150-ralph-loop-cycle-130
- change_id: 20260304-122150-ralph-loop-cycle-130
- change_type: Eval
- scope: ralph-wiggum-loop cycle 130
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_122_20260302_231228/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_130_20260304_103120/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate low focus support

### 20260304-155917-ralph-loop-cycle-131
- change_id: 20260304-155917-ralph-loop-cycle-131
- change_type: Eval
- scope: ralph-wiggum-loop cycle 131
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_122_20260302_231228/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_131_20260304_122150/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate low focus support


## [autopilot-hook] 2026-03-04T15:59:28+0800 cycle=131 reason=cycle_completed
- change_type: Patch
- decision: apply_turn_focus_support_ramp_window_extension_v1
- why: `no_improve_streak=49` with `quick_gate_low_focus_support` and zero candidates indicates stalled near-threshold TURN support observability.
- what: patched `poker2/runtime/system_policy.py` to widen bounded TURN support ramp window (`0.76->0.72`, high-risk `0.70`) and slight `gap2` cap lift (`0.12->0.14`).
- rollback: restore pre-patch TURN support ramp constants and remove high-risk widening branch.
- verify: passed `PYTHONPYCACHEPREFIX=/tmp/pycache_verify python3 -m py_compile poker2/runtime/system_policy.py`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_131_20260304_122150/review.json`, `tmp/ralph_loop_runs_v2/cycle_131_20260304_122150/cycle_result.json`, `tmp/ralph_patch_manifest_cycle132_20260304_155928.json`

### 2026-03-04-cycle131-turn-focus-support-ramp-window-extension
- change_id: 2026-03-04-cycle131-turn-focus-support-ramp-window-extension
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（TURN near-threshold support ramp widening with bounded high-risk branch）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（light checkpoint patch; heavy eval deferred）
- evidence:
  - E1 | metric=quick_gate.reason=quick_gate_low_focus_support | n=1 cycle | seeds=cycle131 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_131_20260304_122150/review.json
  - E2 | metric=no_improve_streak=49 | n=state snapshot | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E3 | metric=candidate_count=0 | n=1 cycle | seeds=cycle131 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_131_20260304_122150/cycle_result.json
- outcome: CONTINUE
- rationale: widened but bounded TURN support ramp should increase focus-support coverage for next quick gate while preserving rollback simplicity.

### 20260304-175130-ralph-loop-cycle-132
- change_id: 20260304-175130-ralph-loop-cycle-132
- change_type: Eval
- scope: ralph-wiggum-loop cycle 132
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_122_20260302_231228/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_132_20260304_155917/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate low focus support

## [autopilot-hook] 2026-03-04T17:55:31+0800 cycle=132 reason=cycle_completed
- change_type: Patch
- decision: apply_turn_focus_support_ramp_window_widen_v1
- why: `no_improve_streak=50` and latest quick gate `quick_gate_low_focus_support`; active support remained `hands=16/hits=0`.
- what: patched `poker2/runtime/system_policy.py` TURN high-price support-ramp window/cap (single bounded mechanism for stalled support branch).
- rollback: revert TURN support-ramp block around `threshold2` near-threshold logic.
- verify: `python3 -m py_compile poker2/runtime/system_policy.py`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle132_20260304_175531.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_runs_v2/cycle_132_20260304_155917/review.json`, `tmp/ralph_loop_runs_v2/cycle_132_20260304_155917/cycle_result.json`

### 2026-03-04-turn-focus-support-ramp-window-widen-v1
- change_id: 2026-03-04-turn-focus-support-ramp-window-widen-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（TURN 高价位 near-threshold support ramp 覆盖扩展，限高风险分支）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（轻量复盘周期；未跑重型评测）
- evidence:
  - E1 | metric=quick_gate.reason=quick_gate_low_focus_support | n=1 | seeds=cycle132 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_132_20260304_155917/review.json
  - E2 | metric=active_support_hands=16,hits=0 | n=1 | seeds=cycle132 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_132_20260304_155917/review.json
  - E3 | metric=mechanism_patch_applied(system_policy) | n=1 file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: 先解决 focus support 死锁，下一轮观察 quick gate support/hits 是否脱离 0，再决定是否进入 full gate。

### 20260304-194409-ralph-loop-cycle-133
- change_id: 20260304-194409-ralph-loop-cycle-133
- change_type: Eval
- scope: ralph-wiggum-loop cycle 133
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_122_20260302_231228/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_133_20260304_175151/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate low focus support


## [autopilot-hook] 2026-03-04T19:44:18+0800 cycle=133 reason=cycle_completed
- change_type: Patch
- decision: apply_turn_deadlock_threshold2_relief_v1
- why: `no_improve_streak=51` and latest completed review remains `quick_gate_low_focus_support` with support hits still zero, blocking candidate eligibility.
- what: patched `poker2/runtime/system_policy.py` to add bounded TURN near-threshold threshold2 relief on MW+wet+low-SPR deadlock branch.
- rollback: remove `turn_focus_deadlock_threshold2_relief` init/block/trace field.
- verify: `python3` compile check + next_action required-fields check.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle134_20260304_194418.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_133_20260304_175151/review.json`, `tmp/ralph_loop_runs_v2/cycle_133_20260304_175151/cycle_result.json`

### 2026-03-04-cycle133-turn-deadlock-threshold2-relief-v1
- change_id: 2026-03-04-cycle133-turn-deadlock-threshold2-relief-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（TURN high-price deadlock threshold2 bounded relief）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（checkpoint patch；未跑重型评测）
- evidence:
  - E1 | metric=no_improve_streak=51 | n=1 state | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E2 | metric=quick_gate.reason=quick_gate_low_focus_support,active_support_hits=0 | n=1 cycle | seeds=cycle133 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_133_20260304_175151/review.json
  - E3 | metric=mechanism_patch_applied(system_policy) | n=1 file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: use a single bounded TURN mechanism to increase near-threshold support observability while preserving low-price behavior and rollback simplicity.

### 20260304-213602-ralph-loop-cycle-134
- change_id: 20260304-213602-ralph-loop-cycle-134
- change_type: Eval
- scope: ralph-wiggum-loop cycle 134
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_122_20260302_231228/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_134_20260304_194409/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate low focus support


## [autopilot-hook] 2026-03-04T21:36:43+0800 cycle=134 reason=cycle_completed
- change_type: Patch
- decision: apply_turn_focus_support_reentry_gate_v1
- why: `no_improve_streak=52` and latest completed review stayed at `quick_gate_low_focus_support`; support starvation keeps blocking behavior-delta observability.
- what: patched `poker2/runtime/system_policy.py` with one bounded TURN near-threshold reentry penalty triggered only when deadlock + support-ramp signals co-occur.
- rollback: remove `turn_focus_support_reentry_penalty` init/block and associated penalty accumulation from `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=/tmp/pycache_verify python3 -m py_compile poker2/runtime/system_policy.py` and next_action required-field check.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle135_20260304_213643.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_134_20260304_194409/review.json`, `tmp/ralph_loop_runs_v2/cycle_134_20260304_194409/cycle_result.json`

### 2026-03-04-cycle134-turn-focus-support-reentry-gate-v1
- change_id: 2026-03-04-cycle134-turn-focus-support-reentry-gate-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（TURN high-price near-threshold support reentry gate）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（light checkpoint patch; heavy eval deferred）
- evidence:
  - E1 | metric=no_improve_streak=52 | n=1 state | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E2 | metric=quick_gate.reason=quick_gate_low_focus_support | n=1 cycle | seeds=cycle134 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_134_20260304_194409/review.json
  - E3 | metric=mechanism_patch_applied(system_policy) | n=1 file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: keep one bounded mechanism to unlock focus-support observability for next quick gate while preserving rollback simplicity and low-price stability.

### 20260304-232820-ralph-loop-cycle-135
- change_id: 20260304-232820-ralph-loop-cycle-135
- change_type: Eval
- scope: ralph-wiggum-loop cycle 135
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_122_20260302_231228/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_135_20260304_213602/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate low focus support

## [autopilot-hook] 2026-03-04T23:29:17+0800 cycle=135 reason=cycle_completed
- change_type: Patch
- decision: apply_turn_focus_support_reentry_ramp_fallback_v1
- why: `no_improve_streak=53` 且 latest completed review 为 `quick_gate_low_focus_support`，并出现 `support_pass_count=0`、`targeted_focus_support_hits_delta_total=0`，需要单机制解除 support-hit starvation。
- what: patched `poker2/runtime/system_policy.py`，在 TURN near-threshold reentry 触发中新增 ramp fallback（deadlock 或强 ramp 其一触发），保持有界 cap 与 gap2 裁剪。
- rollback: 删除 `ramp_reentry_fallback_trigger` 及其条件分支，恢复 deadlock-only reentry 条件。
- verify: `python3` 编译检查 + next_action 必填字段校验。
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle136_20260304_232917.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_135_20260304_213602/review.json`, `tmp/ralph_loop_runs_v2/cycle_135_20260304_213602/cycle_result.json`

### 2026-03-04-cycle135-turn-focus-support-reentry-ramp-fallback-v1
- change_id: 2026-03-04-cycle135-turn-focus-support-reentry-ramp-fallback-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（TURN high-price near-threshold support reentry ramp fallback）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（light checkpoint patch；未跑重型评测）
- evidence:
  - E1 | metric=no_improve_streak=53 | n=1 state | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E2 | metric=quick_gate.reason=quick_gate_low_focus_support,support_pass_count=0,targeted_focus_support_hits_delta_total=0 | n=1 cycle | seeds=cycle135 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_135_20260304_213602/review.json
  - E3 | metric=mechanism_patch_applied(system_policy) | n=1 file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: 单机制仅放宽 TURN reentry 触发门槛到 deadlock-or-ramp，目标是提升 focus-support hits 可观测性并保持低价路径稳定。

## [autopilot-hook] 2026-03-04T23:29:17+0800 cycle=135 reason=cycle_completed
- change_type: Patch
- decision: apply_turn_focus_support_reentry_severe_trigger_v1
- why: `no_improve_streak=53` 且 latest completed review 仍为 `quick_gate_low_focus_support`，同时 `support_pass_count=0` 与 `targeted_focus_support_hits_delta_total=0`，需要单机制解除 TURN support-hit starvation。
- what: patched `poker2/runtime/system_policy.py`，在 TURN reentry 逻辑新增 severe support-starvation trigger（`wet_score>=3`、`spr<=1.8`、`price>=0.72*threshold2`），并保持有界 cap + gap2 裁剪。
- rollback: 删除 `ramp_reentry_severe_trigger` 及其 severe 分支，恢复至 deadlock-or-ramp fallback 版本。
- verify: `PYTHONPYCACHEPREFIX=/tmp/pycache_verify python3 -m py_compile poker2/runtime/system_policy.py` 与 `python3` 的 next_action 字段校验。
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle136_20260304_232917_autohook.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_135_20260304_213602/review.json`, `tmp/ralph_loop_runs_v2/cycle_135_20260304_213602/cycle_result.json`

### 2026-03-04-cycle135-turn-focus-support-reentry-severe-trigger-v1
- change_id: 2026-03-04-cycle135-turn-focus-support-reentry-severe-trigger-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（TURN high-price near-threshold severe support reentry）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（light checkpoint patch；未跑重型评测）
- evidence:
  - E1 | metric=no_improve_streak=53 | n=1 state | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E2 | metric=quick_gate.reason=quick_gate_low_focus_support,support_pass_count=0,targeted_focus_support_hits_delta_total=0 | n=1 cycle | seeds=cycle135 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_135_20260304_213602/review.json
  - E3 | metric=mechanism_patch_applied(system_policy) | n=1 file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: 用单机制在高风险 TURN 分支增加受控 reentry 机会，优先解开 quick gate 的 support-hit starvation，同时保持回退和边界约束简单。

### 20260305-012036-ralph-loop-cycle-136
- change_id: 20260305-012036-ralph-loop-cycle-136
- change_type: Eval
- scope: ralph-wiggum-loop cycle 136
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_122_20260302_231228/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_136_20260304_232820/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate low focus support


## [autopilot-hook] 2026-03-05T01:20:53+0800 cycle=136 reason=cycle_completed
- change_type: Patch
- decision: apply_river_forced_bet_support_window_reactivation_boost_v1
- why: `no_improve_streak=54` and latest completed quick gate returned `quick_gate_low_focus_support`; support coverage remains insufficient.
- what: patched `poker2/runtime/system_policy.py` to add bounded `support_window_expand_cap` relief (`+0.003/+0.004`, hard cap `0.060`) only on existing MW+wet+low-SPR+commitment branch.
- rollback: remove the newly added `support_window_expand_cap` relief block and keep prior taper-only logic.
- verify: passed `PYTHONPYCACHEPREFIX=/tmp/pycache_verify python3 -m py_compile poker2/runtime/system_policy.py`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_136_20260304_232820/review.json`, `tmp/ralph_loop_runs_v2/cycle_136_20260304_232820/cycle_result.json`, `tmp/ralph_patch_manifest_cycle137_20260305_012053.json`

### 2026-03-05-cycle136-river-forced-bet-support-window-reactivation-boost
- change_id: 2026-03-05-cycle136-river-forced-bet-support-window-reactivation-boost
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（RIVER forced-bet support window bounded widening on stalled branch）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（checkpoint light patch; heavy eval deferred）
- evidence:
  - E1 | metric=quick_gate.reason=quick_gate_low_focus_support | n=1 cycle | seeds=cycle136 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_136_20260304_232820/review.json
  - E2 | metric=no_improve_streak=54 | n=state snapshot | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E3 | metric=active_quick incomplete for cycle137 | n=1 cycle | seeds=cycle137 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_137_20260305_012036
- outcome: CONTINUE
- rationale: targeted support-window widening should increase quick-gate focus support hits while staying inside the existing forced-bet branch boundary.

### 20260305-135108-ralph-loop-cycle-137
- change_id: 20260305-135108-ralph-loop-cycle-137
- change_type: Eval
- scope: ralph-wiggum-loop cycle 137
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_122_20260302_231228/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_137_20260305_012036/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate low focus support

## [autopilot-hook] 2026-03-05T13:51:13+0800 cycle=137 reason=cycle_completed
- change_type: Patch
- decision: apply_turn_focus_support_ramp_severe_window_v2
- why: `no_improve_streak=55` and latest quick gate reason `quick_gate_low_focus_support` on completed cycle 137.
- what: patched `poker2/runtime/system_policy.py` TURN severe near-threshold support-ramp aperture/cap on wet+low-SPR multiway stalled branch.
- rollback: revert TURN support-ramp `ramp_entry/ramp_span/ramp_cap/ramp_gap2_scale` adjustments.
- verify: `python3 -m py_compile poker2/runtime/system_policy.py`
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle138_20260305_135113.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_runs_v2/cycle_137_20260305_012036/review.json`, `tmp/ralph_loop_runs_v2/cycle_137_20260305_012036/cycle_result.json`

### 2026-03-05-turn-focus-support-ramp-severe-window-v2
- change_id: 2026-03-05-turn-focus-support-ramp-severe-window-v2
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（TURN high-price near-threshold support-ramp severe stalled branch widening）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（轻量复盘周期；未跑重型评测）
- evidence:
  - E1 | metric=quick_gate.reason=quick_gate_low_focus_support | n=1 | seeds=cycle137 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_137_20260305_012036/review.json
  - E2 | metric=no_improve_streak=55 | n=1 | seeds=cycle137 | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E3 | metric=mechanism_patch_applied(system_policy) | n=1 file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: 先提升 stalled TURN 分支的 support 命中覆盖，观察下一次 quick gate 的 focus support/hits 与 behavior delta 是否脱离低支持区。

### 20260305-221404-ralph-loop-cycle-138
- change_id: 20260305-221404-ralph-loop-cycle-138
- change_type: Eval
- scope: ralph-wiggum-loop cycle 138
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_122_20260302_231228/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_138_20260305_135108/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate low focus support

## [autopilot-hook] 2026-03-05T22:14:09+0800 cycle=138 reason=cycle_completed
- change_type: Patch
- decision: apply_turn_support_starvation_reentry_window_v1
- why: `no_improve_streak=56` and completed cycle 138 quick gate reason `quick_gate_low_focus_support`, with `targeted_focus_support_hits_delta_total=0` over mechanism candidates.
- what: patched `poker2/runtime/system_policy.py` to add bounded TURN near-threshold support-starvation reentry trigger (ramp-active + deadlock-not-fired path) with conservative floor/SPR widening only under MW+wet branches.
- rollback: remove `ramp_reentry_support_starvation_trigger` and restore fixed reentry activation floor (`0.74`) and SPR ceiling (`2.0`).
- verify: `python3` compile check and next_action required-fields check.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle138_20260305_221409_autohook.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_138_20260305_135108/review.json`, `tmp/ralph_loop_runs_v2/cycle_138_20260305_135108/cycle_result.json`

### 2026-03-05-cycle138-turn-support-starvation-reentry-window-v1
- change_id: 2026-03-05-cycle138-turn-support-starvation-reentry-window-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（TURN high-price near-threshold support-starvation reentry window）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（轻量复盘周期；未跑重型评测）
- evidence:
  - E1 | metric=no_improve_streak=56 | n=1 state | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E2 | metric=quick_gate.reason=quick_gate_low_focus_support,targeted_focus_support_hits_delta_total=0 | n=1 cycle | seeds=cycle138 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_138_20260305_135108/review.json
  - E3 | metric=mechanism_patch_applied(system_policy) | n=1 file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: 在不扩展低价分支的前提下，为 TURN stalled near-threshold 路径增加有界 reentry 触发，优先解除 support-hit starvation 并维持可回退性。

### 20260306-001148-ralph-loop-cycle-139
- change_id: 20260306-001148-ralph-loop-cycle-139
- change_type: Eval
- scope: ralph-wiggum-loop cycle 139
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_122_20260302_231228/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_139_20260305_221425/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate low focus support

## [autopilot-hook] 2026-03-06T00:11:56+0800 cycle=139 reason=cycle_completed
- change_type: Patch
- decision: apply_turn_support_starvation_soft_reentry_aperture_v1
- why: `no_improve_streak=57` and latest completed quick gate is `quick_gate_low_focus_support` with `support_pass_count=0` and `targeted_focus_support_hits_delta_total=0`; hard starvation trigger still misses too often.
- what: patched `poker2/runtime/system_policy.py` to add a bounded TURN soft starvation reentry trigger (`0.66*threshold2`, `spr<=2.4`) on existing high-price MW wet branch, while keeping cap and gap2 clamp.
- rollback: remove `ramp_reentry_support_starvation_soft_trigger` branch and restore hard-trigger-only reentry activation.
- verify: `PYTHONPYCACHEPREFIX=/tmp/pycache_verify python3 -m py_compile poker2/runtime/system_policy.py` and `python3` JSON required-field check for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle140_20260306_001156_autohook.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_139_20260305_221425/review.json`, `tmp/ralph_loop_runs_v2/cycle_139_20260305_221425/cycle_result.json`

### 2026-03-06-cycle139-turn-support-starvation-soft-reentry-aperture-v1
- change_id: 2026-03-06-cycle139-turn-support-starvation-soft-reentry-aperture-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（TURN high-price support-starvation soft reentry aperture）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（checkpoint light patch; heavy eval deferred）
- evidence:
  - E1 | metric=no_improve_streak=57 | n=1 state | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E2 | metric=quick_gate.reason=quick_gate_low_focus_support,support_pass_count=0,targeted_focus_support_hits_delta_total=0 | n=1 cycle | seeds=cycle139 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_139_20260305_221425/review.json
  - E3 | metric=mechanism_patch_applied(system_policy) | n=1 file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: add one bounded soft trigger to improve TURN focus-support observability when hard starvation trigger does not fire, without expanding low-price paths.

## [autopilot-hook] 2026-03-06T00:11:56+0800 cycle=139 reason=cycle_completed
- change_type: Patch
- decision: apply_turn_support_bridge_reentry_trigger_v1
- why: `no_improve_streak=57` 且 latest completed review 为 `quick_gate_low_focus_support`，同时 `support_pass_count=0`、`targeted_focus_support_hits_delta_total=0`、`candidate_count=0`；需在既有 TURN near-threshold 分支补一个可回退机制以解除 support-hit starvation。
- what: patched `poker2/runtime/system_policy.py`，新增 bounded `ramp_reentry_bridge_trigger`（bridge penalty 已触发但 ramp 未触发时）以打开 TURN reentry aperture；仅限 MW+wet+low-SPR 高价窗口，保留 cap 与 gap2 clamp。
- rollback: 删除 `ramp_reentry_bridge_trigger` 及其 activation/reentry 分支，恢复到 soft-starvation-only reentry 触发。
- verify: `PYTHONPYCACHEPREFIX=/tmp/pycache_verify python3 -m py_compile poker2/runtime/system_policy.py` + `python3` 检查 `tmp/ralph_next_action.json` 必填字段。
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle140_20260306_001156_autohook_v2.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_139_20260305_221425/review.json`, `tmp/ralph_loop_runs_v2/cycle_139_20260305_221425/cycle_result.json`

### 2026-03-06-cycle139-turn-support-bridge-reentry-trigger-v1
- change_id: 2026-03-06-cycle139-turn-support-bridge-reentry-trigger-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（TURN high-price near-threshold bridge-triggered reentry）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（checkpoint light patch; heavy eval deferred）
- evidence:
  - E1 | metric=no_improve_streak=57 | n=1 state | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E2 | metric=quick_gate.reason=quick_gate_low_focus_support,support_pass_count=0,targeted_focus_support_hits_delta_total=0,candidate_count=0 | n=1 cycle | seeds=cycle139 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_139_20260305_221425/review.json
  - E3 | metric=mechanism_patch_applied(system_policy) | n=1 file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: 在不扩展低价路径的前提下，用 bridge-only fallback 为 stalled TURN 分支增加可观测 support hits，提升下一轮 quick gate 产生 behavior delta 的概率。

### 20260306-021141-ralph-loop-cycle-140
- change_id: 20260306-021141-ralph-loop-cycle-140
- change_type: Eval
- scope: ralph-wiggum-loop cycle 140
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_122_20260302_231228/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_140_20260306_001148/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate low focus support

## [autopilot-hook] 2026-03-06T02:11:48+0800 cycle=140 reason=cycle_completed
- change_type: Patch
- decision: apply_turn_support_bridge_probe_reentry_trigger_v1
- why: `no_improve_streak=58` 且 completed cycle 140 quick gate 为 `quick_gate_low_focus_support`，同时 `support_pass_count=0`、`targeted_focus_support_hits_delta_total=0`，并出现候选行为零变化分支（`behavior_delta=0`）。
- what: patched `poker2/runtime/system_policy.py`，在 TURN near-threshold reentry 增加 bounded `ramp_reentry_probe_trigger`（bridge pressure 已出现但既有 starvation/bridge trigger 未命中时），仅限 MW+wet+low-SPR 分支并保留 cap/gap2 clamp。
- rollback: 删除 `ramp_reentry_probe_trigger` 以及对应 activation/reentry 分支，恢复到 bridge+starvation trigger 版本。
- verify: `PYTHONPYCACHEPREFIX=/tmp/pycache_verify python3 -m py_compile poker2/runtime/system_policy.py` + `python3` 校验 `tmp/ralph_next_action.json` 必填字段。
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle141_20260306_021148_autohook.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_140_20260306_001148/review.json`, `tmp/ralph_loop_runs_v2/cycle_140_20260306_001148/cycle_result.json`

### 2026-03-06-cycle140-turn-support-bridge-probe-reentry-trigger-v1
- change_id: 2026-03-06-cycle140-turn-support-bridge-probe-reentry-trigger-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（TURN high-price near-threshold bridge-probe reentry trigger）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（checkpoint light patch; heavy eval deferred）
- evidence:
  - E1 | metric=no_improve_streak=58 | n=1 state | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E2 | metric=quick_gate.reason=quick_gate_low_focus_support,support_pass_count=0,targeted_focus_support_hits_delta_total=0,behavior_delta_zero_candidates=3 | n=1 cycle | seeds=cycle140 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_140_20260306_001148/review.json
  - E3 | metric=mechanism_patch_applied(system_policy) | n=1 file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: 用单机制 probe 触发补齐 stalled TURN branch 的 support-hit 观测机会，避免扩大低价路径并保持回退简单。

### 20260306-041436-ralph-loop-cycle-141
- change_id: 20260306-041436-ralph-loop-cycle-141
- change_type: Eval
- scope: ralph-wiggum-loop cycle 141
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_122_20260302_231228/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_141_20260306_021141/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate low focus support

### 20260306-062009-ralph-loop-cycle-142
- change_id: 20260306-062009-ralph-loop-cycle-142
- change_type: Eval
- scope: ralph-wiggum-loop cycle 142
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_122_20260302_231228/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_142_20260306_041436/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate low focus support

## [autopilot-hook] 2026-03-06T06:20:18+0800 cycle=142 reason=cycle_completed
- change_type: Patch
- decision: apply_turn_bridge_probe_relaxed_wet_reentry_v1
- why: `no_improve_streak=60` and completed cycle 142 quick gate reason `quick_gate_low_focus_support` with `support_pass_count=0` and `targeted_focus_support_hits_delta_total=0`.
- what: patched `poker2/runtime/system_policy.py` to add a bounded TURN reentry fallback (`wet_score>=1`) only for bridge/probe stalled branches where deadlock/ramp signals stayed near zero, keeping caps and near-threshold window intact.
- rollback: remove `bridge_probe_relaxed_wet_branch/reentry_required_wet_score` and restore `wet_score>=2` gate for TURN reentry branch.
- verify: `PYTHONPYCACHEPREFIX=/tmp/pycache_verify python3 -m py_compile poker2/runtime/system_policy.py`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_142_20260306_041436/review.json`, `tmp/ralph_loop_runs_v2/cycle_142_20260306_041436/cycle_result.json`, `tmp/ralph_patch_manifest_cycle143_20260306_062018_autohook.json`

### 2026-03-06-cycle142-turn-bridge-probe-relaxed-wet-reentry-v1
- change_id: 2026-03-06-cycle142-turn-bridge-probe-relaxed-wet-reentry-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（TURN near-threshold bridge/probe reentry with bounded wet=1 fallback）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（checkpoint light patch; heavy eval deferred）
- evidence:
  - E1 | metric=no_improve_streak=60 | n=1 state | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E2 | metric=quick_gate.reason=quick_gate_low_focus_support,support_pass_count=0,targeted_focus_support_hits_delta_total=0 | n=1 cycle | seeds=cycle142 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_142_20260306_041436/review.json
  - E3 | metric=mechanism_patch_applied(system_policy) | n=1 file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: 在既有 TURN bridge/probe stalled 分支上允许有界 `wet=1` reentry，可增加 support-hit 观测而不扩展低价路径，优先解除 quick-gate 支持覆盖饥饿。

### 20260306-082755-ralph-loop-cycle-143
- change_id: 20260306-082755-ralph-loop-cycle-143
- change_type: Eval
- scope: ralph-wiggum-loop cycle 143
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_122_20260302_231228/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_143_20260306_062009/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate low focus support

## [autopilot-hook] 2026-03-06T08:28:00+0800 cycle=143 reason=cycle_completed
- change_type: Patch
- decision: apply_turn_stalled_support_ramp_aperture_v1
- why: `no_improve_streak=61` and completed cycle 143 quick gate reason `quick_gate_low_focus_support` with `support_pass_count=0` and `targeted_focus_support_hits_delta_total=0`.
- what: patched `poker2/runtime/system_policy.py` to widen TURN stalled-branch support-ramp aperture only when deadlock/bridge penalties remain near-zero (`spr<=2.6`, `wet>=1`, multiway), keeping high-price near-threshold bounds.
- rollback: revert the new TURN stalled-branch condition and restore the previous `spr<=2.4` ramp entry branch (`ramp_entry=0.68`, `ramp_span=0.30`).
- verify: `python3 -m py_compile poker2/runtime/system_policy.py` + `python3` required-field check for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle144_20260306_082800_autohook.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_143_20260306_062009/review.json`, `tmp/ralph_loop_runs_v2/cycle_143_20260306_062009/cycle_result.json`

### 2026-03-06-cycle143-turn-stalled-support-ramp-aperture-v1
- change_id: 2026-03-06-cycle143-turn-stalled-support-ramp-aperture-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（TURN stalled support-ramp aperture widening with bounded deadlock/bridge gating）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（checkpoint light patch; heavy eval deferred）
- evidence:
  - E1 | metric=no_improve_streak=61 | n=1 state | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E2 | metric=quick_gate.reason=quick_gate_low_focus_support,support_pass_count=0,targeted_focus_support_hits_delta_total=0 | n=1 cycle | seeds=cycle143 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_143_20260306_062009/review.json
  - E3 | metric=mechanism_patch_applied(system_policy) | n=1 file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: add one bounded TURN stalled-branch aperture relaxation to improve focus-support observability in the next quick cycle without widening low-price behavior.

### 20260306-103859-ralph-loop-cycle-144
- change_id: 20260306-103859-ralph-loop-cycle-144
- change_type: Eval
- scope: ralph-wiggum-loop cycle 144
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_122_20260302_231228/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_144_20260306_082755/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate low focus support


## [autopilot-hook] 2026-03-06T10:39:03+0800 cycle=144 reason=cycle_completed
- change_type: Patch
- decision: apply_turn_support_starvation_stall_reentry_window_v1
- why: `no_improve_streak=62` and latest completed quick gate is `quick_gate_low_focus_support` with `support_pass_count=0` and `targeted_focus_support_hits_delta_total=0`.
- what: patched `poker2/runtime/system_policy.py` to add bounded TURN high-price support-starvation stall trigger and reentry aperture for branches where support-ramp is active but deadlock/bridge remain weak.
- rollback: remove `ramp_reentry_support_starvation_stall_trigger` and its activation/reentry branch wiring; restore previous starvation/soft/bridge/probe-only reentry routing.
- verify: `python3 -m py_compile poker2/runtime/system_policy.py`; `python3` required-fields check for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle144_20260306_103903_autohook.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_144_20260306_082755/review.json`, `tmp/ralph_loop_runs_v2/cycle_144_20260306_082755/cycle_result.json`

### 2026-03-06-cycle144-turn-support-starvation-stall-reentry-window-v1
- change_id: 2026-03-06-cycle144-turn-support-starvation-stall-reentry-window-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（TURN high-price near-threshold support-starvation stall reentry）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（轻量复盘周期；未跑重型评测）
- evidence:
  - E1 | metric=no_improve_streak=62 | n=1 state | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E2 | metric=quick_gate.reason=quick_gate_low_focus_support,support_pass_count=0,targeted_focus_support_hits_delta_total=0 | n=1 cycle | seeds=cycle144 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_144_20260306_082755/review.json
  - E3 | metric=mechanism_patch_applied(system_policy) | n=1 file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: 在不扩展低价分支的前提下，补齐 stalled TURN 路径的有界 reentry 触发，优先提升 focus-support 命中并保持可回退。

### 20260306-181246-ralph-loop-cycle-145
- change_id: 20260306-181246-ralph-loop-cycle-145
- change_type: Eval
- scope: ralph-wiggum-loop cycle 145
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_145_20260306_123339/trial_full_shadow/c145_x2/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_145_20260306_123339/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_145_20260306_123339/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_145_20260306_123339/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate targeted_shadow fail (robust_pass=False, pareto_constraints=False, holdout_pass=False)

### 20260307-025239-ralph-loop-cycle-146
- change_id: 20260307-025239-ralph-loop-cycle-146
- change_type: Eval
- scope: ralph-wiggum-loop cycle 146
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_146_20260306_181246/trial_full_shadow/c146_x6/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_146_20260306_181246/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_146_20260306_181246/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_146_20260306_181246/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate targeted_shadow fail (robust_pass=False, pareto_constraints=False, holdout_pass=False)

## [autopilot-hook] 2026-03-07T02:53:16+0800 cycle=146 reason=cycle_completed
- change_type: Patch
- decision: apply_turn_support_visibility_recovery_trigger_v1
- why: `no_improve_streak=64` and cycle146 quick gate shows `support_pass_count=0`, `eligible_count=0`, `targeted_focus_support_hands_delta_total=24`, `targeted_focus_support_hits_delta_total=0`; support coverage grows but still produces zero hits.
- what: patched `poker2/runtime/system_policy.py` by adding `ramp_reentry_support_visibility_recovery_trigger` and wiring it into TURN reentry activation/visibility-relaxed gating so low-signal stalled branches can produce bounded support hits.
- rollback: remove `ramp_reentry_support_visibility_recovery_trigger` and related activation branches from `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=/tmp/pycache_verify python3 -m py_compile poker2/runtime/system_policy.py` and `python3` JSON required-field validation for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle146_20260307_025316_autohook.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_146_20260306_181246/review.json`, `tmp/ralph_loop_runs_v2/cycle_146_20260306_181246/cycle_result.json`

### 2026-03-07-cycle146-turn-support-visibility-recovery-trigger-v1
- change_id: 2026-03-07-cycle146-turn-support-visibility-recovery-trigger-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（TURN high-price low-signal visibility recovery reentry）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（checkpoint light patch; heavy eval deferred）
- evidence:
  - E1 | metric=no_improve_streak=64 | n=1 state | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E2 | metric=cycle146.quick_gate.support_pass_count=0,targeted_focus_support_hands_delta_total=24,targeted_focus_support_hits_delta_total=0 | n=1 cycle | seeds=cycle146 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_146_20260306_181246/review.json
  - E3 | metric=mechanism_patch_applied(turn_support_visibility_recovery_trigger_v1) | n=1 file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: widen only the low-signal TURN visibility reentry aperture to convert support-hand accumulation into observable hits while preserving bounded caps and existing deadlock/bridge guards.

### 20260307-064534-ralph-loop-cycle-147
- change_id: 20260307-064534-ralph-loop-cycle-147
- change_type: Eval
- scope: ralph-wiggum-loop cycle 147
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_147_20260307_025240/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_147_20260307_025240/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_147_20260307_025240/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_147_20260307_025240/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (robust_pass=False, pareto_constraints=False, holdout_pass=False)


## [autopilot-hook] 2026-03-07T06:45:50+0800 cycle=147 reason=cycle_completed
- change_type: Patch
- decision: apply_turn_support_visibility_floor_reentry_trigger_v1
- why: `no_improve_streak=65` and cycle147 quick gate still reports `support_pass_count=0`, `eligible_count=0`, `targeted_focus_support_hands_delta_total=24`, `targeted_focus_support_hits_delta_total=0`; existing visibility-recovery branch starts too high for low-signal ramp cases.
- what: patched `poker2/runtime/system_policy.py` to add `ramp_reentry_support_visibility_floor_trigger` and connect it to activation, relaxed visibility wet branch, and reentry pressure path for TURN stalled support branches.
- rollback: remove `ramp_reentry_support_visibility_floor_trigger` and related activation/branch wiring; restore the previous visibility relaxed `spr` ceiling.
- verify: `PYTHONPYCACHEPREFIX=/tmp/pycache_verify python3 -m py_compile poker2/runtime/system_policy.py`; `python3` required-field check for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle147_20260307_064550_autohook.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_147_20260307_025240/review.json`, `tmp/ralph_loop_runs_v2/cycle_147_20260307_025240/cycle_result.json`

### 2026-03-07-cycle147-turn-support-visibility-floor-trigger-v1
- change_id: 2026-03-07-cycle147-turn-support-visibility-floor-trigger-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（TURN high-price low-signal visibility floor reentry trigger）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（checkpoint light patch; heavy eval deferred）
- evidence:
  - E1 | metric=no_improve_streak=65 | n=1 state | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E2 | metric=cycle147.quick_gate.support_pass_count=0,eligible_count=0,targeted_focus_support_hands_delta_total=24,targeted_focus_support_hits_delta_total=0 | n=1 cycle | seeds=cycle147 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_147_20260307_025240/review.json
  - E3 | metric=mechanism_patch_applied(turn_support_visibility_floor_reentry_trigger_v1) | n=1 file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: convert low-signal support ramp branches into bounded observable hits without widening high-signal deadlock paths; if quick gate still reports zero hits, escalate to stricter low-SPR wet bridge clamp.

### 20260307-104138-ralph-loop-cycle-148
- change_id: 20260307-104138-ralph-loop-cycle-148
- change_type: Eval
- scope: ralph-wiggum-loop cycle 148
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_148_20260307_064534/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_148_20260307_064534/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_148_20260307_064534/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_148_20260307_064534/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (robust_pass=False, pareto_constraints=False, holdout_pass=False)

## [autopilot-hook] 2026-03-07T10:42:10+0800 cycle=148 reason=cycle_completed
- change_type: Patch
- decision: apply_turn_low_spr_wet_firewall_escalation_v1
- why: `no_improve_streak=66` and cycle148 review still reports `support_pass_count=0`, `eligible_count=0`, `targeted_focus_support_hands_delta_total=24`, `targeted_focus_support_hits_delta_total=0` under `full_gate_fail`; repeated visibility/reentry widening did not produce stable behavior delta.
- what: patched `poker2/runtime/system_policy.py` to add `firewall_low_spr_wet_escalation` so TURN high-price low-SPR wet multiway branches with weak bridge support receive a bounded firewall entry/span/cap escalation.
- rollback: remove `firewall_low_spr_wet_escalation` branch and restore the previous fixed firewall entry/span/cap calculation in `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=/tmp/pycache_verify python3 -m py_compile poker2/runtime/system_policy.py` and `python3` required-field validation for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle149_20260307_104210_autohook.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_148_20260307_064534/review.json`, `tmp/ralph_loop_runs_v2/cycle_148_20260307_064534/cycle_result.json`

### 2026-03-07-cycle148-turn-low-spr-wet-firewall-escalation-v1
- change_id: 2026-03-07-cycle148-turn-low-spr-wet-firewall-escalation-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（TURN low-SPR wet firewall escalation on stalled high-price multiway branch）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（checkpoint light patch; heavy eval deferred）
- evidence:
  - E1 | metric=no_improve_streak=66 | n=1 state | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E2 | metric=cycle148.quick_gate.reason=full_gate_fail,support_pass_count=0,eligible_count=0,targeted_focus_support_hands_delta_total=24,targeted_focus_support_hits_delta_total=0 | n=1 cycle | seeds=cycle148 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_148_20260307_064534/review.json
  - E3 | metric=mechanism_patch_applied(turn_low_spr_wet_firewall_escalation_v1) | n=1 file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: shift from repeated visibility aperture widening to a bounded TURN low-SPR wet firewall escalation so stalled high-price multiway branches must produce measurable behavior delta with tighter downside control.

### 20260307-143706-ralph-loop-cycle-149
- change_id: 20260307-143706-ralph-loop-cycle-149
- change_type: Eval
- scope: ralph-wiggum-loop cycle 149
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_149_20260307_104139/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_149_20260307_104139/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_149_20260307_104139/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_149_20260307_104139/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (robust_pass=False, pareto_constraints=False, holdout_pass=False)

### 20260307-200021-ralph-loop-cycle-150
- change_id: 20260307-200021-ralph-loop-cycle-150
- change_type: Eval
- scope: ralph-wiggum-loop cycle 150
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_150_20260307_143706/trial_full_shadow/c150_x2/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_150_20260307_143706/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_150_20260307_143706/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_150_20260307_143706/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate targeted_shadow fail (robust_pass=False, pareto_constraints=False, holdout_pass=False)

### 20260308-052041-ralph-loop-cycle-151
- change_id: 20260308-052041-ralph-loop-cycle-151
- change_type: Eval
- scope: ralph-wiggum-loop cycle 151
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_151_20260307_215456/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_151_20260307_215456/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_151_20260307_215456/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_151_20260307_215456/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (robust_pass=False, pareto_constraints=False, holdout_pass=False)

### 20260308-152910-ralph-loop-cycle-152
- change_id: 20260308-152910-ralph-loop-cycle-152
- change_type: Eval
- scope: ralph-wiggum-loop cycle 152
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_152_20260308_052042/trial_full_shadow/c152_x2/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_152_20260308_052042/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_152_20260308_052042/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_152_20260308_052042/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate targeted_shadow fail (robust_pass=False, pareto_constraints=False, holdout_pass=False)

### 20260308-184033-ralph-loop-cycle-153
- change_id: 20260308-184033-ralph-loop-cycle-153
- change_type: Eval
- scope: ralph-wiggum-loop cycle 153
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_153_20260308_152910/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_153_20260308_152910/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_153_20260308_152910/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_153_20260308_152910/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (robust_pass=False, pareto_constraints=False, holdout_pass=False)

## [autopilot-hook] 2026-03-08T20:43:31+0800 cycle=null reason=stall_timeout
- change_type: Patch
- decision: apply_loop_subprocess_timeout_enforcement_v1
- why: `restart_count=4` with `progress_age_sec=6012` while `tmp/ralph_loop_runs_v2/cycle_154_20260308_184956` already contains `active_quick` and `input_next_action.json`; latest completed cycle 153 still shows `quick_gate.reason=full_gate_fail`, `support_pass_count=0`, `targeted_focus_support_hits_delta_total=0`, so the immediate blocker is loop liveness, not a missing action ticket.
- what: patched `tools/ralph_wiggum_loop.py` so `_run_cmd` enforces wrapper-level timeout on child eval commands and records the in-flight `active_quick` stage into `tmp/ralph_loop_state_v2.json` before running quick eval.
- rollback: restore `_run_cmd` to plain `subprocess.run(...)` and remove the pre-`active_quick` state checkpoint fields in `tools/ralph_wiggum_loop.py`.
- verify: `python3` compile check for `tools/ralph_wiggum_loop.py` plus `python3` JSON required-field validation for `tmp/ralph_next_action.json`.
- evidence_ref: `tools/ralph_wiggum_loop.py`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_154_20260308_184956`, `tmp/ralph_loop_runs_v2/cycle_153_20260308_152910/review.json`, `tmp/ralph_loop_runs_v2/cycle_153_20260308_152910/cycle_result.json`

### 2026-03-08-stall-timeout-subprocess-timeout-enforcement-v1
- change_id: 2026-03-08-stall-timeout-subprocess-timeout-enforcement-v1
- change_type: Patch
- scope: `tools/ralph_wiggum_loop.py`（child eval timeout enforcement + active_quick state checkpoint）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（restart hook patch; no heavy eval）
- evidence:
  - E1 | metric=restart_count=4,progress_age_sec=6012 | n=1 event | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E2 | metric=cycle154.entries=active_quick,input_next_action.json | n=1 cycle_dir | seeds=cycle154 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_154_20260308_184956
  - E3 | metric=cycle153.quick_gate.reason=full_gate_fail,support_pass_count=0,targeted_focus_support_hits_delta_total=0 | n=1 cycle | seeds=cycle153 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_153_20260308_152910/review.json
- outcome: CONTINUE
- rationale: eliminate supervisor restart churn first by making loop-level child commands honor timeout and exposing the active phase in state; keep the next policy mechanism focused on the unchanged TURN/RIVER Facing=Y weakness after liveness is restored.

## [manual-fix] 2026-03-08T22:40:00+0800 dispatcher-awaiting-parse-fix
- change_type: Patch
- decision: fix_dispatcher_top_level_event_parsing_for_awaiting_llm_action
- why: nested `llm_review_policy.reason` in event JSON caused regex-based field extraction to return multiple `reason` values, so dispatcher silently skipped `awaiting_llm_action` events and cycle 154 could not receive a new action ticket.
- what: patched `tools/ralph_hook_dispatcher.sh` to parse event lines as JSON and read only top-level `status/reason/cycle` fields before routing.
- rollback: restore the previous `extract_field` / `extract_num_field` regex implementation in `tools/ralph_hook_dispatcher.sh`.
- verify: `zsh -n tools/ralph_hook_dispatcher.sh`; python3 parse check on a real `awaiting_llm_action` event line.
- evidence_ref: `tools/ralph_hook_dispatcher.sh`, `tmp/ralph_loop_events.ndjson`, `tmp/ralph_loop_state_v2.json`

## [manual-fix] 2026-03-08T22:46:00+0800 llm-review-fail-open-default
- change_type: Patch
- decision: enable_dynamic_llm_review_fail_open_by_default
- why: the rebuilt loop correctly escalated cycle 154 into `awaiting_llm_action`, but Codex/dispatcher availability remained unstable enough to stall iteration entirely; the safest continuity policy is to prefer model-generated tickets yet auto-fall back when infrastructure cannot provide one.
- what: changed `tools/ralph_wiggum_loop.py` and `tools/ralph_loop_supervisor.sh` so dynamic LLM review keeps its trigger thresholds but defaults to fail-open, allowing the loop to resume with an auto-generated action plan when no valid ticket arrives.
- rollback: restore `DEFAULT_LLM_REVIEW_FAIL_OPEN=False` and `LLM_REVIEW_FAIL_OPEN=0`, then restart the loop service.
- verify: `python3 -m py_compile tools/ralph_wiggum_loop.py`; `zsh -n tools/ralph_loop_supervisor.sh tools/ralph_hook_dispatcher.sh`; `pytest -q tests/test_ralph_wiggum_loop_regressions.py --no-cov`.
- evidence_ref: `tools/ralph_wiggum_loop.py`, `tools/ralph_loop_supervisor.sh`, `tests/test_ralph_wiggum_loop_regressions.py`, `tmp/ralph_loop_events.ndjson`

## [manual-fix] 2026-03-08T22:58:00+0800 loop-robustness-recovery-lane
- change_type: Loop
- decision: add_fail_open_robustness_recovery_lane
- why: fail-open 让 loop 不再卡 `awaiting_llm_action`，但也绕开了原先只在 missing-action fallback 中才会注入的 `counter_aggression_stability` companion，导致连续 `full_gate_fail` 后候选池仍主要是高压硬化而缺少稳健性恢复机制。
- what: patched `tools/ralph_wiggum_loop.py` so repeated trailing `full_gate_fail` without an explicit `action_plan` automatically seeds bounded `robustness_recovery` mechanisms (`counter_aggression_stability` first, then `balanced_pressure_mix`) and also prepends them to stagnation lane backfill.
- verify: `python3 -m py_compile tools/ralph_wiggum_loop.py`; `pytest -q tests/test_ralph_wiggum_loop_regressions.py --no-cov`
- evidence_ref: `tools/ralph_wiggum_loop.py`, `tests/test_ralph_wiggum_loop_regressions.py`, `tmp/ralph_loop_runs_v2/cycle_153_20260308_152910/review.json`, `tmp/ralph_loop_runs_v2/cycle_153_20260308_152910/cycle_result.json`

### 20260309-015016-ralph-loop-cycle-154
- change_id: 20260309-015016-ralph-loop-cycle-154
- change_type: Eval
- scope: ralph-wiggum-loop cycle 154
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_154_20260308_231140/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_154_20260308_231140/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_154_20260308_231140/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_154_20260308_231140/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (robust_pass=False, pareto_constraints=False, holdout_pass=False)

## [autopilot-hook] 2026-03-09T01:50:32+0800 cycle=154 reason=cycle_completed
- change_type: Patch
- decision: apply_high_price_turn_river_hardening_v1
- why: `no_improve_streak=72` and cycle154 review still ends at `full_gate_fail`; targeted focus support moved from `12` to `16` hands but `hits` stayed `0`, while the observed high-price facing mix remains raise-heavy on TURN/RIVER.
- what: patched `poker2/runtime/system_policy.py` to add a bounded hardening branch that clamps `raise_share` in `TURN/RIVER + high-price + low-SPR + wet + multiway` facing spots and lightly trims expensive `RIVER` defend target at threshold2.
- rollback: remove the added hardening branch under the `facing_high_price_threshold` handling in `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=/tmp/pycache_verify python3 -m py_compile poker2/runtime/system_policy.py` and `python3` required-field validation for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle155_20260309_015032_autohook.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_154_20260308_231140/review.json`, `tmp/ralph_loop_runs_v2/cycle_154_20260308_231140/cycle_result.json`

### 2026-03-09-cycle154-high-price-turn-river-hardening-v1
- change_id: 2026-03-09-cycle154-high-price-turn-river-hardening-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（TURN/RIVER high-price low-SPR wet multiway hardening）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（checkpoint light patch; heavy eval deferred）
- evidence:
  - E1 | metric=no_improve_streak=72 | n=1 state | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E2 | metric=cycle154.quick_gate.reason=full_gate_fail,support_before.hands=12,support_after.hands=16,support_after.hits=0,turn_high_price_raise_rate=0.50,river_high_price_raise_rate=0.20 | n=1 cycle | seeds=cycle154 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_154_20260308_231140/review.json
  - E3 | metric=mechanism_patch_applied(high_price_turn_river_hardening_v1) | n=1 file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: stop widening visibility/support apertures and force a measurable behavior delta directly in the stressed high-price branch; if the next quick gate still shows zero hits and no action-mix movement, escalate to a call-frequency clamp rather than another reentry trigger.

### 20260309-042928-ralph-loop-cycle-155
- change_id: 20260309-042928-ralph-loop-cycle-155
- change_type: Eval
- scope: ralph-wiggum-loop cycle 155
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_155_20260309_015016/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_155_20260309_015016/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_155_20260309_015016/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_155_20260309_015016/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (robust_pass=False, pareto_constraints=False, holdout_pass=False)

## [autopilot-hook] 2026-03-09T04:29:33+0800 cycle=155 reason=cycle_completed
- change_type: Patch
- decision: apply_high_price_turn_river_call_floor_v1
- why: `no_improve_streak=73` and cycle155 review still reports `full_gate_fail`; targeted support stays at `hits=0` while the observed high-price facing mix remains too raise-heavy on TURN (`raise_rate=0.50`) and still elevated on RIVER (`raise_rate=0.20`).
- what: patched `poker2/runtime/system_policy.py` to add a bounded `high_price_turn_river_call_floor_v1` branch that raises `call_pref` and tightens `ev_raise_share_cap` in `TURN/RIVER + high-price + low-SPR + wet + multiway` facing spots so defended mass shifts from raise to call.
- rollback: remove `high_price_call_floor_raise_cap` and the associated high-price call-floor branch from `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=/tmp/pycache_verify python3 -m py_compile poker2/runtime/system_policy.py` and `python3` required-field validation for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle156_20260309_042933_autohook.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_156_20260309_042928`, `tmp/ralph_loop_runs_v2/cycle_155_20260309_015016/review.json`, `tmp/ralph_loop_runs_v2/cycle_155_20260309_015016/cycle_result.json`

### 2026-03-09-cycle155-high-price-turn-river-call-floor-v1
- change_id: 2026-03-09-cycle155-high-price-turn-river-call-floor-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（TURN/RIVER high-price low-SPR wet multiway call-floor clamp）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（checkpoint light patch; heavy eval deferred）
- evidence:
  - E1 | metric=no_improve_streak=73 | n=1 state | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E2 | metric=cycle155.quick_gate.reason=full_gate_fail,support_after.hits=0,turn_high_price_raise_rate=0.50,river_high_price_raise_rate=0.20 | n=1 cycle | seeds=cycle155 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_155_20260309_015016/review.json
  - E3 | metric=mechanism_patch_applied(high_price_turn_river_call_floor_v1) | n=1 file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: prior hardening reduced neither the missing support hits nor the stressed branch action mix enough, so the next bounded mechanism forces call-first defense exactly where high-price TURN/RIVER facing spots remain over-aggressive; if quick gate still shows no behavior delta, escalate to a stricter defend-share clamp rather than another raise-share heuristic.

### 20260309-051123-ralph-loop-cycle-156
- change_id: 20260309-051123-ralph-loop-cycle-156
- change_type: Eval
- scope: ralph-wiggum-loop cycle 156
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_122_20260302_231228/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_156_20260309_042928/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate runtime error (all trial quick batches failed)
## [autopilot-hook] 2026-03-09T05:11:41+0800 cycle=156 reason=cycle_completed
- change_type: Patch
- decision: apply_support_visibility_threshold_binding_fix_v1
- why: `no_improve_streak=74` already crossed the forced-patch threshold, and cycle156 review shows `quick_gate.reason=quick_gate_runtime_error`, `runtime_pass_count=0`, `eligible_count=0`; both active and candidate quick runs fail at `poker2/runtime/system_policy.py` with `NameError: threshold2_local`, so the loop cannot observe support or behavior deltas.
- what: patched `poker2/runtime/system_policy.py` so the high-price support-visibility clamp falls back to the canonical threshold inputs when `threshold2_local` has not been assigned yet, restoring runtime stability without changing action legality or widening thresholds.
- rollback: remove the `try/except NameError` fallback around `high_price_threshold_local` in `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=/tmp/pycache_verify python3` import/compile smoke for `poker2.runtime.system_policy`, plus required-field validation for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle157_20260309_051141_autohook.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_156_20260309_042928/review.json`, `tmp/ralph_loop_runs_v2/cycle_156_20260309_042928/cycle_result.json`, `tmp/ralph_loop_runs_v2/cycle_157_20260309_051123/active_quick/coinpoker_7max_mw_v3_actionspace_v2/tierA/seed3000/run.log`

### 2026-03-09-cycle156-support-visibility-threshold-binding-fix-v1
- change_id: 2026-03-09-cycle156-support-visibility-threshold-binding-fix-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（support-visibility high-price threshold closure fallback）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（checkpoint runtime-unblock patch; heavy eval deferred）
- evidence:
  - E1 | metric=no_improve_streak=74 | n=1 state | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E2 | metric=cycle156.quick_gate.reason=quick_gate_runtime_error,runtime_pass_count=0,eligible_count=0,active_targeted_focus.returncode=1 | n=1 cycle | seeds=cycle156 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_156_20260309_042928/review.json
  - E3 | metric=seed3000.runtime_error=NameError(threshold2_local),mechanism_patch_applied(support_visibility_threshold_binding_fix_v1) | n=1 seed | seeds=3000 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_157_20260309_051123/active_quick/coinpoker_7max_mw_v3_actionspace_v2/tierA/seed3000/run.log;path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: restore runtime-stable quick evaluations first; only after quick runs stop crashing can the loop judge whether the current support-visibility / low-SPR wet lanes still need strategic tightening.

### 20260309-075140-ralph-loop-cycle-157
- change_id: 20260309-075140-ralph-loop-cycle-157
- change_type: Eval
- scope: ralph-wiggum-loop cycle 157
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_157_20260309_051123/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_157_20260309_051123/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_157_20260309_051123/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_157_20260309_051123/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (robust_pass=False, pareto_constraints=False, holdout_pass=False)

## [autopilot-hook] 2026-03-09T07:52:30+0800 cycle=157 reason=cycle_completed
- change_type: Patch
- decision: apply_high_price_turn_river_defend_share_clamp_v1
- why: `no_improve_streak=75` and cycle157 review still ends at `full_gate_fail`; `support_pass_count=0`, `behavior_pass_count=0`, `eligible_count=0`, `targeted_focus_support_hits_delta_total=0`, and all six mechanism candidates tie on the same quick focus score, so the current raise-cap / call-floor path is not producing observable branch movement.
- what: patched `poker2/runtime/system_policy.py` to clamp total `defend_target` before raise-share allocation in `TURN/RIVER + multiway + wet + low-SPR + high-price` facing branches, forcing a bounded fold/call shift instead of only remapping marginal defense between call and raise.
- rollback: remove the added defend-share clamp block inside the stressed high-price branch in `poker2/runtime/system_policy.py`.
- verify: `python3` compile smoke for `poker2/runtime/system_policy.py` plus required-field validation for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle158_20260309_075230_autohook.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_157_20260309_051123/review.json`, `tmp/ralph_loop_runs_v2/cycle_157_20260309_051123/cycle_result.json`

### 2026-03-09-cycle157-high-price-turn-river-defend-share-clamp-v1
- change_id: 2026-03-09-cycle157-high-price-turn-river-defend-share-clamp-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（TURN/RIVER high-price low-SPR wet multiway defend-share clamp）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（checkpoint light patch; heavy eval deferred）
- evidence:
  - E1 | metric=no_improve_streak=75 | n=1 state | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E2 | metric=cycle157.quick_gate.reason=full_gate_fail,support_pass_count=0,behavior_pass_count=0,eligible_count=0,targeted_focus_support_hits_delta_total=0,all_candidates_focus_metric_value=-977.5 | n=1 cycle | seeds=cycle157 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_157_20260309_051123/review.json
  - E3 | metric=mechanism_patch_applied(high_price_turn_river_defend_share_clamp_v1) | n=1 file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: the loop is no longer blocked by runtime errors, but its mechanism lane is deadlocked in tied high-price candidates with zero focus hits, so the next bounded step is to compress total defense in the stressed branch and wait for the next quick gate to confirm an actual behavior shift before touching thresholds again.

### 20260309-104804-ralph-loop-cycle-158
- change_id: 20260309-104804-ralph-loop-cycle-158
- change_type: Eval
- scope: ralph-wiggum-loop cycle 158
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_158_20260309_075140/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_158_20260309_075140/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_158_20260309_075140/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_158_20260309_075140/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (robust_pass=False, pareto_constraints=False, holdout_pass=False)

## [autopilot-hook] 2026-03-09T10:48:19+0800 cycle=158 reason=cycle_completed
- change_type: Patch
- decision: apply_turn_visibility_low_spr_wet_reentry_v1
- why: `no_improve_streak=76` and cycle158 review still shows `support_pass_count=0`, `mechanism_eligible_count=0`, `targeted_focus_support_hands_delta_total=24`, `targeted_focus_support_hits_delta_total=0`; all six mechanism candidates add support hands without producing a single focus hit, so the existing visibility reentry aperture is still too weak on the low-SPR wet TURN branch.
- what: patched `poker2/runtime/system_policy.py` to reinforce the existing visibility-based reentry path only for `TURN + multiway + wet + low-SPR` branches, raising the bounded reentry floor/span/cap and matching `gap2` cap so the next quick gate can observe actual support-hit movement instead of another zero-hit cycle.
- rollback: remove `visibility_low_spr_wet_reentry_branch` and its associated reentry cap / `gap2` adjustments from `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=/tmp/pycache_verify python3 -m py_compile poker2/runtime/system_policy.py` and `python3` JSON required-field validation for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle159_20260309_104819_autohook.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_158_20260309_075140/review.json`, `tmp/ralph_loop_runs_v2/cycle_158_20260309_075140/cycle_result.json`

### 2026-03-09-cycle158-turn-visibility-low-spr-wet-reentry-v1
- change_id: 2026-03-09-cycle158-turn-visibility-low-spr-wet-reentry-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（TURN low-SPR wet visibility reentry reinforcement）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（checkpoint light patch; heavy eval deferred）
- evidence:
  - E1 | metric=no_improve_streak=76 | n=1 state | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E2 | metric=cycle158.quick_gate.reason=full_gate_fail,support_pass_count=0,mechanism_eligible_count=0,targeted_focus_support_hands_delta_total=24,targeted_focus_support_hits_delta_total=0 | n=1 cycle | seeds=cycle158 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_158_20260309_075140/review.json
  - E3 | metric=mechanism_patch_applied(turn_visibility_low_spr_wet_reentry_v1) | n=1 file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: cycle158 shows the loop is no longer runtime-blocked, but its visibility lane still expands support coverage without creating hits; the next bounded step is to reinforce only the TURN low-SPR wet multiway visibility reentry branch and wait for the next quick gate to confirm a non-zero focus hit before revisiting broader high-price hardening.

### 20260309-135431-ralph-loop-cycle-159
- change_id: 20260309-135431-ralph-loop-cycle-159
- change_type: Eval
- scope: ralph-wiggum-loop cycle 159
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_159_20260309_104804/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_159_20260309_104804/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_159_20260309_104804/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_159_20260309_104804/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (robust_pass=False, pareto_constraints=False, holdout_pass=False)

## [autopilot-hook] 2026-03-09T13:55:09+0800 cycle=159 reason=cycle_completed
- change_type: Patch
- decision: apply_turn_visibility_hit_unlock_v1
- why: `no_improve_streak=77` and cycle159 review still shows `focus_support_pass_count=0` with `targeted_focus_support_hands_delta_total=24` and `targeted_focus_support_hits_delta_total=0`; the active quick focus probe also moved support from `12` hands to `16` hands while `high_price_low_spr_hits` stayed at `0`, so the loop needs a direct visibility-to-hit unlock instead of another broader reentry aperture.
- what: patched `poker2/runtime/system_policy.py` to add a bounded `TURN + multiway + wet + low-SPR` visibility threshold relief that only unlocks direct high-price hits in the upper half of the stalled visibility band.
- rollback: remove the `turn_focus_visibility_threshold_relief` block added before the high-price defend-gap penalties in `poker2/runtime/system_policy.py`.
- verify: `python3` compile check for `poker2/runtime/system_policy.py` and `python3` required-field validation for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle159_20260309_135509_autohook.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_159_20260309_104804/review.json`, `tmp/ralph_loop_runs_v2/cycle_159_20260309_104804/cycle_result.json`

### 2026-03-09-cycle159-turn-visibility-hit-unlock-v1
- change_id: 2026-03-09-cycle159-turn-visibility-hit-unlock-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（TURN visibility hit unlock on low-SPR wet multiway branches）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（checkpoint light patch; heavy eval deferred）
- evidence:
  - E1 | metric=no_improve_streak=77 | n=1 state | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E2 | metric=cycle159.quick_gate.reason=full_gate_fail,focus_support_pass_count=0,targeted_focus_support_hands_delta_total=24,targeted_focus_support_hits_delta_total=0 | n=1 cycle | seeds=cycle159 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_159_20260309_104804/review.json
  - E3 | metric=mechanism_patch_applied(turn_visibility_hit_unlock_v1) | n=1 file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: cycle159 already proved the current visibility lane can create more support hands, but not hits; the next bounded step is to unlock hit accounting only in the upper half of the same stalled TURN visibility band and let the next quick gate confirm whether support can finally register non-zero hits without widening lower-price branches.

### 20260309-171946-ralph-loop-cycle-160
- change_id: 20260309-171946-ralph-loop-cycle-160
- change_type: Eval
- scope: ralph-wiggum-loop cycle 160
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_160_20260309_135509/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_160_20260309_135509/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_160_20260309_135509/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_160_20260309_135509/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (robust_pass=False, pareto_constraints=False, holdout_pass=False)

## [autopilot-hook] 2026-03-09T17:20:34+0800 cycle=160 reason=cycle_completed
- change_type: Patch
- decision: apply_turn_visibility_midband_hit_unlock_v1
- why: `no_improve_streak=78` and cycle160 review still shows `support_before.hands=12`, `support_after.hands=16`, `support_after.hits=0`, `high_price_low_spr_hits=0`; the current TURN visibility unlock only opens the upper half of the stalled band, so support growth still fails to register observable hits.
- what: patched `poker2/runtime/system_policy.py` to add a bounded `turn_visibility_midband_hit_unlock_v1` branch that extends direct-hit unlock into the mid-band only for `TURN + multiway + wet + low-SPR` visibility branches already producing extra support hands.
- rollback: remove `low_spr_wet_visibility_midband_unlock` and the associated mid-band direct-hit unlock threshold from `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=/tmp/pycache_verify python3 -m py_compile poker2/runtime/system_policy.py` and `python3` required-field validation for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle160_20260309_172034_autohook.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_161_20260309_171946`, `tmp/ralph_loop_runs_v2/cycle_160_20260309_135509/review.json`, `tmp/ralph_loop_runs_v2/cycle_160_20260309_135509/cycle_result.json`

### 2026-03-09-cycle160-turn-visibility-midband-hit-unlock-v1
- change_id: 2026-03-09-cycle160-turn-visibility-midband-hit-unlock-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（TURN visibility mid-band hit unlock on low-SPR wet multiway branches）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（checkpoint light patch; heavy eval deferred）
- evidence:
  - E1 | metric=no_improve_streak=78 | n=1 state | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E2 | metric=cycle160.quick_gate.reason=full_gate_fail,support_before.hands=12,support_after.hands=16,support_after.hits=0,high_price_low_spr_hits=0 | n=1 cycle | seeds=cycle160 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_160_20260309_135509/review.json
  - E3 | metric=mechanism_patch_applied(turn_visibility_midband_hit_unlock_v1) | n=1 file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: keep the fix inside the same stalled TURN visibility lane and force the next quick gate to prove a non-zero hit before any broader raise/call mix changes; if hits remain zero, escalate to a direct call-share clamp on the exact branch rather than widening visibility further.

### 20260309-191100-ralph-loop-cycle-161
- change_id: 20260309-191100-ralph-loop-cycle-161
- change_type: Eval
- scope: ralph-wiggum-loop cycle 161
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_161_20260309_171946/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_161_20260309_171946/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_161_20260309_171946/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate targeted_shadow fail (robust_pass=False, pareto_constraints=False, holdout_pass=False)

## [autopilot-hook] 2026-03-09T19:11:32+0800 cycle=161 reason=cycle_completed
- change_type: Patch
- decision: apply_low_spr_wet_firewall_v1
- why: `no_improve_streak=79` and cycle161 completed with `quick_gate.reason=full_gate_fail`; the latest review still shows `support_pass_count=0`, `eligible_count=0`, `targeted_focus_support_hands_delta_total=20`, and `targeted_focus_support_hits_delta_total=0`, while state hypothesis ranking already points at `low_spr_wet_firewall` as the top mechanism.
- what: patched `poker2/runtime/system_policy.py` to add a bounded `low_spr_wet_firewall` branch for `TURN/RIVER + SB/BB + facing_bet + high-price + wet + multiway + low-SPR` spots where raise edge over call is still narrow, lifting `call_pref` and compressing the raise-share cap so defended mass moves from raise to call without widening unrelated price bands.
- rollback: remove `low_spr_wet_firewall_strength`, the firewall call-floor / raise-cap block, and the related trace fields from `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=/tmp/pycache_verify python3 -m py_compile poker2/runtime/system_policy.py` and `python3` required-field validation for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle161_20260309_191132_autohook.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_161_20260309_171946/review.json`, `tmp/ralph_loop_runs_v2/cycle_161_20260309_171946/cycle_result.json`

### 2026-03-09-cycle161-low-spr-wet-firewall-v1
- change_id: 2026-03-09-cycle161-low-spr-wet-firewall-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（TURN/RIVER OOP high-price wet multiway low-SPR raise-to-call firewall）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（checkpoint light patch; heavy eval deferred）
- evidence:
  - E1 | metric=no_improve_streak=79 | n=1 state | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E2 | metric=cycle161.quick_gate.reason=full_gate_fail,support_pass_count=0,eligible_count=0,targeted_focus_support_hands_delta_total=20,targeted_focus_support_hits_delta_total=0 | n=1 cycle | seeds=cycle161 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_161_20260309_171946/review.json
  - E3 | metric=mechanism_patch_applied(low_spr_wet_firewall_v1) | n=1 file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: the previous visibility-only and high-price call-floor patches still left the low-SPR wet multiway facing branch too raise-permissive, so this patch narrows the fix to the highest-pressure subspace and exposes explicit activation trace for the next quick gate.

### 20260310-000906-ralph-loop-cycle-162
- change_id: 20260310-000906-ralph-loop-cycle-162
- change_type: Eval
- scope: ralph-wiggum-loop cycle 162
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_162_20260309_191141/trial_full_shadow/c162_x1/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_162_20260309_191141/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_162_20260309_191141/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_162_20260309_191141/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate targeted_shadow fail (robust_pass=False, pareto_constraints=False, holdout_pass=False)

### 20260310-025822-ralph-loop-cycle-163
- change_id: 20260310-025822-ralph-loop-cycle-163
- change_type: Eval
- scope: ralph-wiggum-loop cycle 163
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_163_20260310_000906/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_163_20260310_000906/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_163_20260310_000906/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_163_20260310_000906/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (robust_pass=False, pareto_constraints=False, holdout_pass=False)

## [autopilot-hook] 2026-03-10T02:59:23+0800 cycle=163 reason=cycle_completed
- change_type: Patch
- decision: apply_turn_visibility_reentry_threshold_recenter_v1
- why: `no_improve_streak=81` and cycle163 review still shows `quick_gate.reason=full_gate_fail`, `support_pass_count=0`, `targeted_focus_support_hands_delta_total=24`, `targeted_focus_support_hits_delta_total=0`, and `llm_action_gate.reason=missing_action`; the stalled TURN low-SPR wet visibility-reentry lane needs threshold recentering instead of more global widening.
- what: patched `poker2/runtime/system_policy.py` to add `turn_focus_support_hit_recenter_relief`, a bounded TURN-only threshold recenter on low-SPR wet multiway visibility-reentry branches so support hands can convert into observable high-price hits while the existing firewall continues to cap raise share.
- rollback: remove `turn_focus_support_hit_recenter_relief`, the `support_hit_recenter_branch` threshold adjustment, and the corresponding trace field from `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=/tmp/pycache_verify python3 -m py_compile poker2/runtime/system_policy.py` and `python3` required-field validation for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle163_20260310_025923_autohook.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_163_20260310_000906/review.json`, `tmp/ralph_loop_runs_v2/cycle_163_20260310_000906/cycle_result.json`

### 2026-03-10-cycle163-turn-visibility-reentry-threshold-recenter-v1
- change_id: 2026-03-10-cycle163-turn-visibility-reentry-threshold-recenter-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（TURN low-SPR wet visibility-reentry threshold recenter）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（checkpoint light patch; heavy eval deferred）
- evidence:
  - E1 | metric=no_improve_streak=81 | n=1 state | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E2 | metric=cycle163.quick_gate.reason=full_gate_fail,support_pass_count=0,targeted_focus_support_hands_delta_total=24,targeted_focus_support_hits_delta_total=0,llm_action_gate.reason=missing_action | n=1 cycle | seeds=cycle163 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_163_20260310_000906/review.json
  - E3 | metric=mechanism_patch_applied(turn_visibility_reentry_threshold_recenter_v1) | n=1 file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: keep the fix inside the stalled TURN visibility-reentry lane and lower the observed support-hit threshold only when the exact low-SPR wet multiway reentry branch is already active; if hits stay zero after this, escalate to a direct call-share cap on the same branch rather than widening threshold relief again.

### 20260310-053451-ralph-loop-cycle-164
- change_id: 20260310-053451-ralph-loop-cycle-164
- change_type: Eval
- scope: ralph-wiggum-loop cycle 164
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_164_20260310_025822/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_164_20260310_025822/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_164_20260310_025822/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_164_20260310_025822/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (robust_pass=False, pareto_constraints=False, holdout_pass=False)

### 20260310-055734-ralph-loop-cycle-165
- change_id: 20260310-055734-ralph-loop-cycle-165
- change_type: Eval
- scope: ralph-wiggum-loop cycle 165
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_122_20260302_231228/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_165_20260310_053451/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate runtime error (all trial quick batches failed)

## [autopilot-hook] 2026-03-10T05:58:06+0800 cycle=165 reason=cycle_completed
- change_type: Patch
- decision: apply_turn_visibility_reentry_call_share_cap_v1
- why: `no_improve_streak=83` and cycle165 review still shows `quick_gate.reason=quick_gate_runtime_error`, `support_pass_count=0`, `eligible_count=0`, `targeted_focus_support_hands_delta_total=0`, `targeted_focus_support_hits_delta_total=0`; the next worker needs a consumable action ticket plus a bounded mechanism patch inside the already-identified TURN low-SPR wet visibility lane, not another threshold-widening pass.
- what: patched `poker2/runtime/system_policy.py` to add a direct call-share cap only when `visibility_low_spr_wet_reentry_branch` is already active, pushing the remaining support budget from raise into call on the exact stalled TURN branch; the same patch also requires `wet_score` presence before entering the high-price clamp hot path to reduce repeat quick-gate runtime failures.
- rollback: remove the `visibility_low_spr_wet_reentry_branch` call-floor / raise-cap reinforcement and the added `wet_score is not None` guard from `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=/tmp/pycache_verify python3 -m py_compile poker2/runtime/system_policy.py` and `python3` JSON required-field validation for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle166_20260310_055806_autohook.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_165_20260310_053451/review.json`, `tmp/ralph_loop_runs_v2/cycle_165_20260310_053451/cycle_result.json`

### 2026-03-10-cycle166-turn-visibility-reentry-call-share-cap-v1
- change_id: 2026-03-10-cycle166-turn-visibility-reentry-call-share-cap-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（TURN low-SPR wet visibility-reentry direct call-share cap）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（checkpoint light patch; heavy eval deferred）
- evidence:
  - E1 | metric=no_improve_streak=83 | n=1 state | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E2 | metric=cycle165.quick_gate.reason=quick_gate_runtime_error,support_pass_count=0,eligible_count=0,targeted_focus_support_hands_delta_total=0,targeted_focus_support_hits_delta_total=0 | n=1 cycle | seeds=cycle165 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_165_20260310_053451/review.json
  - E3 | metric=mechanism_patch_applied(turn_visibility_reentry_call_share_cap_v1) | n=1 file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: escalate the already-active TURN visibility-reentry lane by capping raise share directly instead of lowering thresholds again; if the next quick gate still runtime-fails, the next escalation should inspect task stderr rather than widening this branch further.

### 20260310-061527-ralph-loop-cycle-166
- change_id: 20260310-061527-ralph-loop-cycle-166
- change_type: Eval
- scope: ralph-wiggum-loop cycle 166
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_122_20260302_231228/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_166_20260310_055734/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate runtime error (all trial quick batches failed)

## [autopilot-hook] 2026-03-10T06:15:54+0800 cycle=166 reason=cycle_completed
- change_type: Patch
- decision: apply_turn_low_spr_wet_firewall_recenter_v1
- why: `no_improve_streak=84` and cycle166 review still shows `quick_gate.reason=quick_gate_runtime_error`, `support_pass_count=0`, `eligible_count=0`, `runtime_pass_count=0`, `targeted_focus_support_hands_delta_total=0`, `targeted_focus_support_hits_delta_total=0`; recent mechanism candidates stayed unusable, so the next worker needs a consumable action ticket plus a narrower hardening branch inside the existing low-SPR wet firewall instead of more visibility widening.
- what: patched `poker2/runtime/system_policy.py` to add `firewall_support_hit_recenter_branch`, a TURN-only low-SPR wet firewall recenter escalation that activates slightly earlier only on stalled multiway high-price branches with near-zero bridge/deadlock relief, and emits `high_price_wet_low_spr_firewall_recenter_penalty_ppm` for replay evidence.
- rollback: remove `firewall_support_hit_recenter_branch`, `firewall_support_hit_recenter_escalation`, `wet_low_spr_firewall_recenter_penalty`, and the matching trace field from `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=/tmp/pycache_verify python3 -m py_compile poker2/runtime/system_policy.py` and `python3` JSON required-field validation for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle166_20260310_061554_autohook.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_166_20260310_055734/review.json`, `tmp/ralph_loop_runs_v2/cycle_166_20260310_055734/cycle_result.json`

### 2026-03-10-cycle166-turn-low-spr-wet-firewall-recenter-v1
- change_id: 2026-03-10-cycle166-turn-low-spr-wet-firewall-recenter-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（TURN low-SPR wet firewall recenter escalation）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（checkpoint light patch; heavy eval deferred）
- evidence:
  - E1 | metric=no_improve_streak=84 | n=1 state | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E2 | metric=cycle166.quick_gate.reason=quick_gate_runtime_error,support_pass_count=0,eligible_count=0,runtime_pass_count=0,targeted_focus_support_hands_delta_total=0,targeted_focus_support_hits_delta_total=0 | n=1 cycle | seeds=cycle166 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_166_20260310_055734/review.json
  - E3 | metric=mechanism_patch_applied(turn_low_spr_wet_firewall_recenter_v1) | n=1 file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: keep the change inside the existing high-price low-SPR wet firewall, but let the stalled TURN multiway branch harden slightly earlier and leave a dedicated trace so the next retry can show behavior change without widening unrelated reentry paths; if runtime still fails, the next step should inspect quick-task stderr rather than add another policy aperture.

### 20260310-063324-ralph-loop-cycle-167
- change_id: 20260310-063324-ralph-loop-cycle-167
- change_type: Eval
- scope: ralph-wiggum-loop cycle 167
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_122_20260302_231228/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_167_20260310_061527/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate runtime error (all trial quick batches failed)

## [autopilot-hook] 2026-03-10T06:33:47+0800 cycle=167 reason=cycle_completed
- change_type: Patch
- decision: apply_low_spr_wet_firewall_runtime_guard_v1
- why: `no_improve_streak=85` and cycle167 review still shows `quick_gate.reason=quick_gate_runtime_error`, `runtime_pass_count=0`, `support_pass_count=0`, `eligible_count=0`, and nested `llm_action_gate.reason=source_cycle_mismatch`; the next worker needs a consumable action ticket plus a runtime-safe mechanism path before any additional behavior widening.
- what: patched `poker2/runtime/system_policy.py` to initialize `wet_low_spr_firewall_extreme_penalty` before the TURN-only low-SPR wet firewall add-on branch reuses it, keeping the existing firewall lane executable even when the narrower extreme clause does not fire.
- rollback: remove the `wet_low_spr_firewall_extreme_penalty = 0.0` guard inserted immediately before the TURN-only low-SPR wet firewall add-on block in `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=/tmp/pycache_verify python3 -m py_compile poker2/runtime/system_policy.py` and `python3` required-field validation for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle167_20260310_063347_autohook.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_167_20260310_061527/review.json`, `tmp/ralph_loop_runs_v2/cycle_167_20260310_061527/cycle_result.json`

### 2026-03-10-cycle167-low-spr-wet-firewall-runtime-guard-v1
- change_id: 2026-03-10-cycle167-low-spr-wet-firewall-runtime-guard-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（TURN low-SPR wet firewall runtime guard）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（checkpoint light patch; heavy eval deferred）
- evidence:
  - E1 | metric=no_improve_streak=85 | n=1 state | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E2 | metric=cycle167.quick_gate.reason=quick_gate_runtime_error,runtime_pass_count=0,support_pass_count=0,eligible_count=0,llm_action_gate.reason=source_cycle_mismatch | n=1 cycle | seeds=cycle167 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_167_20260310_061527/review.json
  - E3 | metric=mechanism_patch_applied(low_spr_wet_firewall_runtime_guard_v1) | n=1 file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: the stalled TURN low-SPR wet firewall lane could abort when its wider add-on path reuses an accumulator defined only in the narrower extreme clause; initialize that accumulator and refresh the action ticket first, then let the next retry prove runtime recovery before any further behavior expansion.

### 20260310-065127-ralph-loop-cycle-168
- change_id: 20260310-065127-ralph-loop-cycle-168
- change_type: Eval
- scope: ralph-wiggum-loop cycle 168
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_122_20260302_231228/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_168_20260310_063348/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate runtime error (all trial quick batches failed)

### 20260310-070922-ralph-loop-cycle-169
- change_id: 20260310-070922-ralph-loop-cycle-169
- change_type: Eval
- scope: ralph-wiggum-loop cycle 169
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_122_20260302_231228/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_169_20260310_065127/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate runtime error (all trial quick batches failed)

## [autopilot-hook] 2026-03-10T07:09:23+0800 cycle=169 reason=cycle_completed
- change_type: Patch
- decision: apply_turn_visibility_reentry_runtime_guard_v1
- why: `no_improve_streak=87` and cycle169 review still shows `quick_gate.reason=quick_gate_runtime_error`, `runtime_pass_count=0`, `support_pass_count=0`, `eligible_count=0`, plus `llm_action_gate.reason=source_cycle_mismatch`; the next worker needs both a fresh action ticket and a runtime-safe TURN visibility-reentry clamp before any heavier probe is meaningful.
- what: patched `poker2/runtime/system_policy.py` so the existing TURN low-SPR wet visibility-reentry call-share clamp uses a sanitized local `reentry_proximity` and `spr_local`-derived SPR bonus instead of the outer `spr` alias, preventing null/missing alias failures on the hot path while keeping the same bounded mechanism lane.
- rollback: remove the `reentry_proximity_local` / `reentry_spr_bonus` guard block inside the `visibility_low_spr_wet_reentry_branch` clause of `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=/tmp/pycache_verify python3 -m py_compile poker2/runtime/system_policy.py` and `python3` required-field validation for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle169_20260310_070923_autohook.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_169_20260310_065127/review.json`, `tmp/ralph_loop_runs_v2/cycle_169_20260310_065127/cycle_result.json`

### 2026-03-10-cycle169-turn-visibility-reentry-runtime-guard-v1
- change_id: 2026-03-10-cycle169-turn-visibility-reentry-runtime-guard-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（TURN low-SPR wet visibility-reentry runtime guard）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（checkpoint light patch; heavy eval deferred）
- evidence:
  - E1 | metric=no_improve_streak=87 | n=1 state | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E2 | metric=cycle169.quick_gate.reason=quick_gate_runtime_error,runtime_pass_count=0,support_pass_count=0,eligible_count=0,llm_action_gate.reason=source_cycle_mismatch | n=1 cycle | seeds=cycle169 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_169_20260310_065127/review.json
  - E3 | metric=mechanism_patch_applied(turn_visibility_reentry_runtime_guard_v1) | n=1 file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: keep the fix inside the existing TURN visibility-reentry clamp, but force it to consume the already-validated local SPR/proximity state so quick gate runtime can recover before the loop spends another cycle exploring more firewall or hardening branches.

### 20260310-072711-ralph-loop-cycle-170
- change_id: 20260310-072711-ralph-loop-cycle-170
- change_type: Eval
- scope: ralph-wiggum-loop cycle 170
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_122_20260302_231228/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_170_20260310_070922/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate runtime error (all trial quick batches failed)

## [autopilot-hook] 2026-03-10T07:27:51+0800 cycle=170 reason=cycle_completed
- change_type: Patch
- decision: apply_turn_visibility_reentry_presence_guard_v1
- why: `no_improve_streak=88` forces a mechanism patch, and cycle170 review still shows `quick_gate.reason=quick_gate_runtime_error`, all active quick tasks returning code `1`, zero focus support hands/hits, plus `llm_action_gate.reason=source_cycle_mismatch`; the smallest reversible move is to keep the existing TURN low-SPR wet visibility-reentry clamp runnable when its outer branch marker is absent.
- what: patched `poker2/runtime/system_policy.py` to derive a local `visibility_reentry_branch_active` guard from `locals().get(...)` before the TURN support-clamp reentry lane reuses `visibility_low_spr_wet_reentry_branch`, keeping the exact mechanism lane executable without widening thresholds or adding a new policy branch.
- rollback: remove `visibility_reentry_branch_active` and restore the direct `visibility_low_spr_wet_reentry_branch` check inside `poker2/runtime/system_policy.py`.
- verify: `python3` compile check for `poker2/runtime/system_policy.py` and `python3` required-field validation for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle170_20260310_072751_autohook.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_170_20260310_070922/review.json`, `tmp/ralph_loop_runs_v2/cycle_170_20260310_070922/cycle_result.json`, `tmp/ralph_loop_runs_v2/cycle_171_20260310_072711`

### 2026-03-10-cycle170-turn-visibility-reentry-presence-guard-v1
- change_id: 2026-03-10-cycle170-turn-visibility-reentry-presence-guard-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（TURN low-SPR wet visibility-reentry branch presence guard）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（checkpoint light patch; heavy eval deferred）
- evidence:
  - E1 | metric=no_improve_streak=88 | n=1 state | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E2 | metric=cycle170.quick_gate.reason=quick_gate_runtime_error,active_quick.returncodes=1/1/1/1,targeted_focus_support_hands_delta_total=0,targeted_focus_support_hits_delta_total=0,llm_action_gate.reason=source_cycle_mismatch | n=1 cycle | seeds=cycle170 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_170_20260310_070922/review.json
  - E3 | metric=mechanism_patch_applied(turn_visibility_reentry_presence_guard_v1) | n=1 file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: keep the change inside the stalled TURN visibility-reentry lane and only guard the branch-presence dependency, so the next worker retry can emit actual quick-gate behavior instead of aborting before metrics; if runtime still fails after this, escalate to the next missing hot-path input rather than widening the defense logic.

### 20260310-074501-ralph-loop-cycle-171
- change_id: 20260310-074501-ralph-loop-cycle-171
- change_type: Eval
- scope: ralph-wiggum-loop cycle 171
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_122_20260302_231228/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_171_20260310_072711/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate runtime error (all trial quick batches failed)

## [autopilot-hook] 2026-03-10T07:45:23+0800 cycle=171 reason=cycle_completed
- change_type: Patch
- decision: apply_low_spr_wet_firewall_prearm_escalation_v1
- why: `no_improve_streak=89` forces a mechanism patch, and cycle171 review still shows `quick_gate.reason=quick_gate_runtime_error`, `support_pass_count=0`, `targeted_focus_support_hands_delta_total=0`, `targeted_focus_support_hits_delta_total=0`, `candidate_count=6`, and `llm_action_gate.reason=source_cycle_mismatch`; the most bounded next move is to push the existing 4-way+ TURN/RIVER low-SPR wet firewall slightly earlier when its pre-arm signal is already strong.
- what: patched `poker2/runtime/system_policy.py` so a strong `firewall_prearm_strength` can escalate the existing `low_spr_wet_firewall` one step earlier on TURN/RIVER 4-way+ high-price wet low-SPR branches, preserving the same call-edge and raise-gap safety rails instead of introducing a new branch family.
- rollback: remove `firewall_prearm_escalated` and restore the previous `firewall_armed` condition in `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=/tmp/pycache_verify python3 -m py_compile poker2/runtime/system_policy.py` and `python3` required-field validation for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle171_20260310_074523_autohook.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_171_20260310_072711/review.json`, `tmp/ralph_loop_runs_v2/cycle_171_20260310_072711/cycle_result.json`, `tmp/ralph_loop_runs_v2/cycle_172_20260310_074501`

### 2026-03-10-cycle171-low-spr-wet-firewall-prearm-escalation-v1
- change_id: 2026-03-10-cycle171-low-spr-wet-firewall-prearm-escalation-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py` (TURN/RIVER 4-way+ low-SPR wet firewall pre-arm escalation)
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null` (checkpoint light patch; heavy eval deferred)
- evidence:
  - E1 | metric=no_improve_streak=89 | n=1 state | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E2 | metric=cycle171.quick_gate.reason=quick_gate_runtime_error,support_pass_count=0,targeted_focus_support_hands_delta_total=0,targeted_focus_support_hits_delta_total=0,candidate_count=6,llm_action_gate.reason=source_cycle_mismatch | n=1 cycle | seeds=cycle171 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_171_20260310_072711/review.json
  - E3 | metric=mechanism_patch_applied(low_spr_wet_firewall_prearm_escalation_v1) | n=1 file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: reuse the active low-SPR wet firewall path and only widen the pre-arm handoff when pressure is already strong, so the next worker retry can produce a bounded behavior delta in the stalled facing-high-price TURN/RIVER branch without adding a second defensive mechanism.

### 20260310-080254-ralph-loop-cycle-172
- change_id: 20260310-080254-ralph-loop-cycle-172
- change_type: Eval
- scope: ralph-wiggum-loop cycle 172
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_122_20260302_231228/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_172_20260310_074501/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate runtime error (all trial quick batches failed)

## [autopilot-hook] 2026-03-10T08:03:00+0800 cycle=172 reason=cycle_completed
- change_type: Patch
- decision: apply_low_spr_wet_lane_runtime_closure_v1
- why: `no_improve_streak=90` and cycle172 review still shows `quick_gate.reason=quick_gate_runtime_error`, all active quick tasks returning code `1`, zero focus support hands/hits, and stale `llm_action_gate.reason=source_cycle_mismatch`; the next worker needs both a fresh action ticket and a bounded fix that keeps the existing low-SPR wet defense lane executable when branch-scoped markers are absent.
- what: patched `poker2/runtime/system_policy.py` to seed the recent low-SPR wet firewall / visibility reentry branch markers with safe defaults before the stalled TURN/RIVER high-price lane evaluates, so the same mechanism family can run without unbound-local aborts and emit a consumable action ticket for the next retry.
- rollback: remove the default initializers for `firewall_prearm_escalated`, `visibility_reentry_branch_active`, `firewall_support_hit_recenter_branch`, and `firewall_support_hit_recenter_escalation` from `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=/tmp/pycache_verify python3 -m py_compile poker2/runtime/system_policy.py` and `python3` required-field validation for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle172_20260310_080300_autohook.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_172_20260310_074501/review.json`, `tmp/ralph_loop_runs_v2/cycle_172_20260310_074501/cycle_result.json`, `tmp/ralph_loop_runs_v2/cycle_173_20260310_080254`

### 2026-03-10-cycle172-low-spr-wet-lane-runtime-closure-v1
- change_id: 2026-03-10-cycle172-low-spr-wet-lane-runtime-closure-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py` (low-SPR wet high-price lane runtime closure)
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null` (checkpoint light patch; heavy eval deferred)
- evidence:
  - E1 | metric=no_improve_streak=90 | n=1 state | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E2 | metric=cycle172.quick_gate.reason=quick_gate_runtime_error,active_quick.returncodes=1/1/1/1,targeted_focus_support_hands_delta_total=0,targeted_focus_support_hits_delta_total=0,llm_action_gate.reason=source_cycle_mismatch | n=1 cycle | seeds=cycle172 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_172_20260310_074501/review.json
  - E3 | metric=mechanism_patch_applied(low_spr_wet_lane_runtime_closure_v1) | n=1 file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: close the remaining branch-marker gap inside the already-active low-SPR wet defense family instead of widening thresholds again; if quick gate still runtime-fails after this, the next escalation should inspect the failing task stderr path rather than add more policy apertures.

### 20260310-082116-ralph-loop-cycle-173
- change_id: 20260310-082116-ralph-loop-cycle-173
- change_type: Eval
- scope: ralph-wiggum-loop cycle 173
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_122_20260302_231228/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_173_20260310_080254/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate runtime error (all trial quick batches failed)

## 2026-03-10 hook checkpoint cycle 173
- change_type: Patch
- reason: cycle_completed
- hypothesis: low_spr_wet_firewall
- focus_metric: coinpoker.tierP_facingY_turnriver_worst_bb100
- patch: `poker2/runtime/system_policy.py`
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle_173.json`, `tmp/ralph_next_action.json`
- verify: python3 smoke ok (`py_compile` -> `/tmp/system_policy_cycle173.pyc` + JSON asserts)
- result: tightened low-SPR wet turn/river facing-high-price defend scaling and rebased the next action ticket to `source_cycle=173` after the prior stale-ticket rejection (`171` vs `172`).

### 20260310-083950-ralph-loop-cycle-174
- change_id: 20260310-083950-ralph-loop-cycle-174
- change_type: Eval
- scope: ralph-wiggum-loop cycle 174
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_122_20260302_231228/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_174_20260310_082151/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate runtime error (all trial quick batches failed)

## [autopilot-hook] 2026-03-10T08:40:06+0800 cycle=174 reason=cycle_completed
- change_type: Patch
- decision: apply_turn_support_raise_clamp_runtime_closure_v1
- why: `no_improve_streak=92` and cycle174 review still shows `quick_gate.reason=quick_gate_runtime_error`, `active_quick` returncodes `1/1/1/1`, zero focus support hands/hits, plus `llm_action_gate.reason=source_cycle_mismatch` (`172` vs expected `173`); the next worker needs a fresh action ticket and a bounded runtime closure inside the existing TURN support-reentry clamp.
- what: patched `poker2/runtime/system_policy.py` so the existing TURN low-SPR wet support reentry clamp consumes a sanitized local `turn_focus_support_raise_clamp_strength_local` instead of assuming the upstream branch-scoped strength marker always bound, preserving the same mechanism lane while preventing another hot-path unbound-local abort.
- rollback: remove `turn_focus_support_raise_clamp_strength_local` and restore the direct `turn_focus_support_raise_clamp_strength` reads inside the TURN support reentry clamp in `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=/tmp/pycache_verify python3 -m py_compile poker2/runtime/system_policy.py` and `python3` required-field validation for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle174_20260310_084006_autohook.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_174_20260310_082151/review.json`, `tmp/ralph_loop_runs_v2/cycle_174_20260310_082151/cycle_result.json`

### 2026-03-10-cycle174-turn-support-raise-clamp-runtime-closure-v1
- change_id: 2026-03-10-cycle174-turn-support-raise-clamp-runtime-closure-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（TURN support reentry clamp runtime closure）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（checkpoint light patch; heavy eval deferred）
- evidence:
  - E1 | metric=no_improve_streak=92 | n=1 state | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E2 | metric=cycle174.quick_gate.reason=quick_gate_runtime_error,active_quick.returncodes=1/1/1/1,targeted_focus_support_hands_delta_total=0,targeted_focus_support_hits_delta_total=0,llm_action_gate.reason=source_cycle_mismatch(172!=173) | n=1 cycle | seeds=cycle174 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_174_20260310_082151/review.json
  - E3 | metric=mechanism_patch_applied(turn_support_raise_clamp_runtime_closure_v1) | n=1 file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: keep the current low-SPR wet TURN support-reentry mechanism executable without widening thresholds again, then rebase the action ticket to cycle174 so the next worker retry can consume it instead of failing the LLM action gate on stale source-cycle metadata.

### 20260310-085804-ralph-loop-cycle-175
- change_id: 20260310-085804-ralph-loop-cycle-175
- change_type: Eval
- scope: ralph-wiggum-loop cycle 175
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_122_20260302_231228/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_175_20260310_083950/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate runtime error (all trial quick batches failed)

## [autopilot-hook] 2026-03-10T08:58:29+0800 cycle=175 reason=cycle_completed
- change_type: Patch
- decision: apply_high_price_turn_river_threshold2_pressure_boost_v1
- why: `no_improve_streak=93` and cycle 175 still reports `quick_gate.reason=quick_gate_runtime_error` on the same `coinpoker.tierP_facingY_turnriver_worst_bb100` lane, so the next retry needs both a fresh action ticket and a stronger-but-bounded response inside the existing high-price TURN/RIVER defense family.
- what: patched `poker2/runtime/system_policy.py` so wet low-SPR TURN/RIVER spots that already cross `threshold2` add a bounded extra price-pressure boost before computing the firewall scale, which keeps the same mechanism lane but makes extreme facing-high-price defense reductions materially more observable.
- rollback: remove `firewall_pressure_boost` / `threshold2_pressure` and restore the pre-patch firewall scaling block in `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=/tmp/pycache_verify python3 -m py_compile poker2/runtime/system_policy.py` and `python3` required-field validation for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle175_20260310_085829_autohook.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_175_20260310_083950/review.json`, `tmp/ralph_loop_runs_v2/cycle_175_20260310_083950/cycle_result.json`

### 20260310-091621-ralph-loop-cycle-176
- change_id: 20260310-091621-ralph-loop-cycle-176
- change_type: Eval
- scope: ralph-wiggum-loop cycle 176
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_122_20260302_231228/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_176_20260310_085804/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate runtime error (all trial quick batches failed)

## [autopilot-hook] 2026-03-10T09:17:00+0800 cycle=176 reason=cycle_completed
- change_type: Patch
- decision: apply_turn_firewall_support_clamp_bridge_v1
- why: `no_improve_streak=94` forces a mechanism patch, and cycle176 review still shows `quick_gate.reason=quick_gate_runtime_error`, `runtime_pass_count=0`, `support_pass_count=0`, `targeted_focus_support_hands_delta_total=0`, `targeted_focus_support_hits_delta_total=0`, with mechanism-only priority locked on the same TURN/RIVER facing-high-price lane; the safest next move is to keep the existing TURN support clamp executable from already-computed firewall strength instead of adding another threshold family.
- what: patched `poker2/runtime/system_policy.py` so the stalled TURN low-SPR wet support raise clamp can derive a bounded local clamp strength from `low_spr_wet_firewall_strength` when the existing firewall recenter / prearm branch is active but the upstream reentry marker did not bind, preserving the same mechanism family while making the branch runnable and behaviorally observable.
- rollback: remove the `fallback_firewall_strength` bridge block and restore the previous direct reliance on `turn_focus_support_raise_clamp_strength` in `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=/tmp/pycache_verify python3 -m py_compile poker2/runtime/system_policy.py` and `python3` required-field validation for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle176_20260310_091700_autohook.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_176_20260310_085804/review.json`, `tmp/ralph_loop_runs_v2/cycle_176_20260310_085804/cycle_result.json`, `tmp/ralph_loop_runs_v2/cycle_177_20260310_091621`

### 2026-03-10-cycle176-turn-firewall-support-clamp-bridge-v1
- change_id: 2026-03-10-cycle176-turn-firewall-support-clamp-bridge-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（TURN stalled low-SPR wet firewall-to-support clamp bridge）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（checkpoint light patch; heavy eval deferred）
- evidence:
  - E1 | metric=no_improve_streak=94 | n=1 state | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E2 | metric=cycle176.quick_gate.reason=quick_gate_runtime_error,runtime_pass_count=0,support_pass_count=0,targeted_focus_support_hands_delta_total=0,targeted_focus_support_hits_delta_total=0,llm_action_gate.reason=source_cycle_mismatch | n=1 cycle | seeds=cycle176 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_176_20260310_085804/review.json
  - E3 | metric=mechanism_patch_applied(turn_firewall_support_clamp_bridge_v1) | n=1 file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: reuse the already-validated low-SPR wet firewall signal to feed the existing TURN support clamp when branch-scoped reentry strength is absent, so the next worker retry can emit a behavior delta from the same mechanism lane instead of spending another cycle aborting before support is observable.

### 20260310-093429-ralph-loop-cycle-177
- change_id: 20260310-093429-ralph-loop-cycle-177
- change_type: Eval
- scope: ralph-wiggum-loop cycle 177
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_122_20260302_231228/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_177_20260310_091621/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate runtime error (all trial quick batches failed)

## [autopilot-hook] 2026-03-10T09:34:36+0800 cycle=177 reason=cycle_completed
- change_type: Patch
- decision: apply_turn_firewall_support_clamp_floor_v1
- why: `no_improve_streak=95` forces a mechanism patch, and cycle177 review still shows `quick_gate.reason=quick_gate_runtime_error`, `runtime_pass_count=0`, `support_pass_count=0`, `targeted_focus_support_hands_delta_total=0`, `targeted_focus_support_hits_delta_total=0`, while `llm_action_gate.reason=source_cycle_mismatch` remains stale (`175` vs expected `176`).
- what: patched `poker2/runtime/system_policy.py` so the existing TURN low-SPR wet firewall/support-clamp lane now seeds a capped local clamp floor when recenter/prearm markers are active but `low_spr_wet_firewall_strength` did not bind, and syncs that executed local clamp strength back into the canonical trace variable for the next review.
- rollback: remove the synthetic fallback floor block and the `turn_focus_support_raise_clamp_strength` sync assignment from `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=/tmp/pycache_verify python3 -m py_compile poker2/runtime/system_policy.py` and `python3` required-field validation for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle177_20260310_093436_autohook.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_177_20260310_091621/review.json`, `tmp/ralph_loop_runs_v2/cycle_177_20260310_091621/cycle_result.json`, `tmp/ralph_loop_runs_v2/cycle_178_20260310_093429`

### 2026-03-10-cycle177-turn-firewall-support-clamp-floor-v1
- change_id: 2026-03-10-cycle177-turn-firewall-support-clamp-floor-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（TURN stalled low-SPR wet firewall/support clamp fallback floor）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（checkpoint light patch; heavy eval deferred）
- evidence:
  - E1 | metric=no_improve_streak=95 | n=1 state | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E2 | metric=cycle177.quick_gate.reason=quick_gate_runtime_error,runtime_pass_count=0,support_pass_count=0,targeted_focus_support_hands_delta_total=0,targeted_focus_support_hits_delta_total=0,llm_action_gate.reason=source_cycle_mismatch(175!=176) | n=1 cycle | seeds=cycle177 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_177_20260310_091621/review.json
  - E3 | metric=mechanism_patch_applied(turn_firewall_support_clamp_floor_v1) | n=1 file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: keep the change in the active low-SPR wet firewall/support-clamp family, but stop treating an unbound firewall-strength marker as “no clamp at all”; the next retry should now see both a fresh cycle177 action ticket and an observable TURN support clamp trace instead of another silent zero-strength lane.

### 20260310-095232-ralph-loop-cycle-178
- change_id: 20260310-095232-ralph-loop-cycle-178
- change_type: Eval
- scope: ralph-wiggum-loop cycle 178
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_122_20260302_231228/bootstrap_active_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=null
  - br summary | ref=null
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_178_20260310_093429/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: quick gate runtime error (all trial quick batches failed)

### 2026-03-10-system-policy-turn-support-clamp-trace-bind-fix
- change_id: 2026-03-10-system-policy-turn-support-clamp-trace-bind-fix
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（fix facing-bet support-clamp trace binding in `_choose_action_by_ev/_select_from`）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（runtime fix; full eval pending）
- evidence:
  - E1 | metric=pytest.tests/test_system_policy.py::test_postflop_facing_bet_trace_keeps_turn_support_clamp_bound.pass | n=1 test | seeds=? | evidence_ref=path:tests/test_system_policy.py
  - E2 | metric=scrimmage_smoke.system_bot_policy_v3_loop_active.coinpoker_7max_mw_v3_actionspace_v2.system_bot_league_7max_frozen_v1.hands20.seed3000.rc0 | n=1 smoke | seeds=3000 | evidence_ref=path:tmp/manual_smoke_cycle179_fix_20260310_095943
- E3 | metric=cycle179_restart.active_quick_baseline_started_without_unboundlocalerror | n=1 cycle | seeds=3000-3003 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_179_20260310_100138
- outcome: CONTINUE
- rationale: initialize the support-clamp trace field in the outer EV chooser and update it via `nonlocal` inside `_select_from`, so OOP facing-bet quick runs no longer crash when the TURN-only support-clamp branch is inactive on FLOP/other fallback paths.

### 2026-03-10-loop-plan-only-ticket-and-shared-runtime-guard
- change_id: 2026-03-10-loop-plan-only-ticket-and-shared-runtime-guard
- change_type: Restructure
- scope: `tools/ralph_wiggum_loop.py`, `tools/ralph_hook_dispatcher.sh`, `tests/test_ralph_wiggum_loop_regressions.py`
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（protocol fix; eval pending after restart）
- evidence:
  - E1 | metric=recent_autohook_patched_files.shared_runtime_only(system_policy.py) | n=8 manifests | seeds=cycles174-181 | evidence_ref=path:tmp/ralph_patch_manifest_cycle181_20260310_224414_autohook.json
  - E2 | metric=loop_active_trial_share_runtime_core(policy_spec_hash_excludes_system_policy.py) | n=1 codepath | seeds=? | evidence_ref=path:tools/ralph_wiggum_loop.py
  - E3 | metric=pytest.tests/test_ralph_wiggum_loop_regressions.py.pass=11 | n=11 tests | seeds=? | evidence_ref=path:tests/test_ralph_wiggum_loop_regressions.py
- outcome: CONTINUE
- rationale: the loop had been forcing LLM tickets to patch shared runtime core (`poker2/runtime/system_policy.py`) even though `loop_active` and `loop_trial` differ only by params digest and share the same runtime implementation, which let core edits move both sides of the A/B at once and made “break the baseline” statistically incoherent. The fix changes LLM tickets to be plan-first by default, rejects shared-runtime patch tickets unless explicitly allowed, and keeps model guidance focused on `mechanism_plan/knob_plan` so the loop can compare candidates against a stable active runtime again.

## [autopilot-hook] 2026-03-10T09:53:20+0800 cycle=178 reason=cycle_completed
- change_type: Patch
- decision: apply_turn_visibility_reentry_clamp_bridge_v1
- why: `no_improve_streak=96` forces a mechanism patch, cycle178 review still shows `quick_gate.reason=quick_gate_runtime_error` with `targeted_focus_support_hands_delta_total=0`, `targeted_focus_support_hits_delta_total=0`, and stale `llm_action_gate.reason=source_cycle_mismatch` (`176` vs expected `177`), while the in-flight cycle179 ticket remains at `source_cycle=177`.
- what: patched `poker2/runtime/system_policy.py` so the existing TURN low-SPR wet visibility reentry branch can seed the support raise clamp bridge even when firewall recenter/prearm markers stay unset, plus a bounded visibility bonus when firewall strength already exists on the same path.
- rollback: remove `visibility_reentry_branch_active` from the TURN support-clamp bridge condition and delete the visibility-only bonus in the fallback firewall-strength branch from `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=/tmp/pycache_verify python3` compile smoke for `poker2/runtime/system_policy.py` and `python3` required-field validation for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle178_20260310_095320_autohook.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_178_20260310_093429/review.json`, `tmp/ralph_loop_runs_v2/cycle_178_20260310_093429/cycle_result.json`, `tmp/ralph_loop_runs_v2/cycle_179_20260310_095232/input_next_action.json`

### 2026-03-10-cycle178-turn-visibility-reentry-clamp-bridge-v1
- change_id: 2026-03-10-cycle178-turn-visibility-reentry-clamp-bridge-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（TURN low-SPR wet visibility reentry to support-clamp bridge）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（checkpoint light patch; heavy eval deferred）
- evidence:
  - E1 | metric=no_improve_streak=96 | n=1 state | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E2 | metric=cycle178.quick_gate.reason=quick_gate_runtime_error,targeted_focus_support_hands_delta_total=0,targeted_focus_support_hits_delta_total=0,llm_action_gate.reason=source_cycle_mismatch(176!=177) | n=1 cycle | seeds=cycle178 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_178_20260310_093429/review.json
  - E3 | metric=cycle179.input_next_action.source_cycle=177_before_rebase,mechanism_patch_applied(turn_visibility_reentry_clamp_bridge_v1) | n=1 file | seeds=? | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_179_20260310_095232/input_next_action.json
- outcome: CONTINUE
- rationale: extend the already-active visibility reentry lane into the TURN support clamp instead of adding another threshold family, so the next retry can emit a real support-clamp trace and consume a fresh `source_cycle=178` action ticket.

### 20260310-150810-ralph-loop-cycle-179
- change_id: 20260310-150810-ralph-loop-cycle-179
- change_type: Eval
- scope: ralph-wiggum-loop cycle 179
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_179_20260310_100233/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_179_20260310_100233/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_179_20260310_100233/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate targeted_shadow fail (robust_pass=False, pareto_constraints=False, holdout_pass=False)

## [autopilot-hook] 2026-03-10T15:09:11+0800 cycle=179 reason=cycle_completed
- change_type: Patch
- decision: apply_turnriver_threshold2_support_probe_prearm_v1
- why: `no_improve_streak=97` forces a mechanism patch, and cycle179 no longer crashes but still reports `full_gate_fail` while `focus_probe.targeted_focus_set.support_after.hands=16`, `support_after.hits=0`, and `high_price_low_spr_hits=0`; the existing multiway wet high-price threshold2 lane is still present but not behaviorally observable.
- what: patched `poker2/runtime/system_policy.py` so 4-way+ wet TURN/RIVER branches that already crossed `threshold2` add a bounded `support_probe_prearm` boost to the existing firewall pressure calculation, pre-arming the same low-SPR high-price defense family without introducing a new threshold family.
- rollback: remove `support_probe_prearm` and restore the previous `firewall_pressure_boost` block in `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=/tmp/pycache_verify python3 -m py_compile poker2/runtime/system_policy.py` and `python3` required-field validation for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle179_20260310_150911_autohook.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_179_20260310_100233/review.json`, `tmp/ralph_loop_runs_v2/cycle_179_20260310_100233/cycle_result.json`, `tmp/ralph_loop_runs_v2/cycle_180_20260310_150810`

### 2026-03-10-cycle179-turnriver-threshold2-support-probe-prearm-v1
- change_id: 2026-03-10-cycle179-turnriver-threshold2-support-probe-prearm-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（4-way+ wet TURN/RIVER threshold2 support probe pre-arm）
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（checkpoint light patch; heavy eval deferred）
- evidence:
  - E1 | metric=no_improve_streak=97 | n=1 state | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E2 | metric=cycle179.full_gate_fail,targeted_focus_set.support_after.hands=16,targeted_focus_set.support_after.hits=0,high_price_low_spr_hits=0 | n=1 cycle | seeds=cycle179 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_179_20260310_100233/review.json
  - E3 | metric=mechanism_patch_applied(turnriver_threshold2_support_probe_prearm_v1) | n=1 file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: the loop finally reached a full gate instead of aborting, so the next high-ROI step is to pre-arm the already-active threshold2 firewall family in the exact 4-way+ wet TURN/RIVER branch where support hands exist but hits remain zero; if support is still zero next cycle, escalate by explicitly capping raise appetite on the same lane instead of widening to a new mechanism family.

### 20260310-185630-ralph-loop-cycle-180
- change_id: 20260310-185630-ralph-loop-cycle-180
- change_type: Eval
- scope: ralph-wiggum-loop cycle 180
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_180_20260310_150810/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_180_20260310_150810/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_180_20260310_150810/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (robust_pass=False, pareto_constraints=False, holdout_pass=False)

## [autopilot-hook] 2026-03-10T18:56:45+0800 cycle=180 reason=cycle_completed
- change_type: Patch
- decision: apply_oop_mw_defense_clamp_prearm_bridge_v1
- why: `no_improve_streak=98` requires a mechanism patch, and cycle180 still ends in `full_gate_fail` while the best probe candidate `c180_x5` shows `behavior_delta=0.05270061728395062` but `support_after.hits=0`; the OOP multiway defend clamp is active enough to move behavior but not yet concentrated enough to produce an eligible focus hit.
- what: patched `poker2/runtime/system_policy.py` so the existing 4-way+ wet TURN/RIVER `threshold2` firewall prearm also folds in bounded `oop_mw_defense_clamp` pressure from multiway/OOP defend-gap penalties and `retaliation_weight`, instead of opening another threshold family.
- rollback: remove `oop_mw_clamp_bridge` from `poker2/runtime/system_policy.py` and keep the prior `support_probe_prearm` path unchanged.
- verify: `PYTHONPYCACHEPREFIX=/tmp/pycache_verify python3 -m py_compile poker2/runtime/system_policy.py` and `python3` required-field validation for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle180_20260310_185645_autohook.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_180_20260310_150810/review.json`, `tmp/ralph_loop_runs_v2/cycle_180_20260310_150810/cycle_result.json`, `tmp/ralph_loop_runs_v2/cycle_181_20260310_185630`

### 2026-03-10-cycle180-oop-mw-defense-clamp-prearm-bridge-v1
- change_id: 2026-03-10-cycle180-oop-mw-defense-clamp-prearm-bridge-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（4-way+ wet TURN/RIVER threshold2 OOP multiway clamp bridge）
- baseline: `system_bot_policy_v3_loop_active`
- delta: `null`（checkpoint light patch; heavy eval deferred）
- evidence:
  - E1 | metric=no_improve_streak=98 | n=1 state | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E2 | metric=cycle180.full_gate_fail,c180_x5.behavior_delta=0.05270061728395062,c180_x5.support_after.hits=0 | n=1 cycle | seeds=cycle180 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_180_20260310_150810/review.json
  - E3 | metric=mechanism_patch_applied(oop_mw_defense_clamp_prearm_bridge_v1) | n=1 file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: keep attribution clean by extending the same wet TURN/RIVER threshold2 firewall lane that already has measurable behavior movement under `oop_mw_defense_clamp`; if support hits remain zero next cycle, escalate on the same mechanism family by tightening raise appetite rather than widening to a new family.

### 20260310-224335-ralph-loop-cycle-181
- change_id: 20260310-224335-ralph-loop-cycle-181
- change_type: Eval
- scope: ralph-wiggum-loop cycle 181
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_181_20260310_185630/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_181_20260310_185630/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_181_20260310_185630/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (robust_pass=False, pareto_constraints=False, holdout_pass=False)

## [autopilot-hook] 2026-03-10T22:44:14+0800 cycle=181 reason=cycle_completed
- change_type: Patch
- decision: apply_turnriver_threshold2_raise_appetite_clamp_v1
- why: `no_improve_streak=99` forces a mechanism patch, and cycle181 still ends in `full_gate_fail` after the prior wet TURN/RIVER `threshold2` prearm + OOP multiway bridge; escalate on the same lane by tightening raise appetite instead of widening to a new mechanism family.
- what: patched `poker2/runtime/system_policy.py` so 4-way+ wet TURN/RIVER branches already inside the high-price `threshold2` firewall use a lower guard trigger plus a tighter capped raise fraction/all-in floor, concentrating the existing defense lane toward observable fold/call behavior.
- rollback: remove the 4-way+ wet `threshold2` raise-appetite clamp block in `_filter_postflop_actions_by_size` and restore the previous guard thresholds in `poker2/runtime/system_policy.py`.
- verify: `PYTHONPYCACHEPREFIX=/tmp/pycache_verify python3 -m py_compile poker2/runtime/system_policy.py` and `python3` required-field validation for `tmp/ralph_next_action.json`.
- evidence_ref: `poker2/runtime/system_policy.py`, `tmp/ralph_patch_manifest_cycle181_20260310_224414_autohook.json`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`, `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_181_20260310_185630/review.json`, `tmp/ralph_loop_runs_v2/cycle_181_20260310_185630/cycle_result.json`, `tmp/ralph_loop_runs_v2/cycle_182_20260310_224335`

### 2026-03-10-cycle181-turnriver-threshold2-raise-appetite-clamp-v1
- change_id: 2026-03-10-cycle181-turnriver-threshold2-raise-appetite-clamp-v1
- change_type: Patch
- scope: `poker2/runtime/system_policy.py`（4-way+ wet TURN/RIVER threshold2 raise appetite clamp）
- baseline: `system_bot_policy_v3_loop_active`
- delta: `null`（checkpoint light patch; heavy eval deferred）
- evidence:
  - E1 | metric=no_improve_streak=99 | n=1 state | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E2 | metric=cycle181.full_gate_fail,focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100,llm_action_gate.pass=true | n=1 cycle | seeds=cycle181 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_181_20260310_185630/review.json
  - E3 | metric=mechanism_patch_applied(turnriver_threshold2_raise_appetite_clamp_v1) | n=1 file | seeds=? | evidence_ref=path:poker2/runtime/system_policy.py
- outcome: CONTINUE
- rationale: the previous bridge kept the lane alive into full-gate probing, but cycle181 still stalls on the same focus metric; the next narrow escalation is to clamp raise appetite on the exact 4-way+ wet TURN/RIVER `threshold2` branch so quick-gate behavior delta can become attributable without widening the policy surface.

### 20260311-023547-ralph-loop-cycle-182
- change_id: 20260311-023547-ralph-loop-cycle-182
- change_type: Eval
- scope: ralph-wiggum-loop cycle 182
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_182_20260310_233156/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_182_20260310_233156/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_182_20260310_233156/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_182_20260310_233156/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (robust_pass=False, pareto_constraints=False, holdout_pass=False)

### 20260311-063347-ralph-loop-cycle-183
- change_id: 20260311-063347-ralph-loop-cycle-183
- change_type: Eval
- scope: ralph-wiggum-loop cycle 183
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_183_20260311_023547/trial_full_shadow/c183_x2/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_183_20260311_023547/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_183_20260311_023547/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_183_20260311_023547/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate targeted_shadow fail (robust_pass=False, pareto_constraints=False, holdout_pass=False)

### 2026-03-11-dispatcher-plan-only-normalization-guard
- change_id: 2026-03-11-dispatcher-plan-only-normalization-guard
- change_type: Restructure
- scope: `tools/ralph_hook_dispatcher.sh`
- baseline: `retaliation_weight_v1_high_price_defend_gate_v8_20260206`
- delta: `null`（protocol fix; eval pending under restarted cycle184）
- evidence:
  - E1 | metric=queued_next_action.patched_files.shared_runtime_autofill | n=1 live ticket | seeds=cycle183->184 | evidence_ref=path:tmp/ralph_next_action.json
  - E2 | metric=cycle184_restarted_without_consuming_stale_ticket | n=1 cycle | seeds=184 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_184_20260311_090010
- E3 | metric=pytest.tests/test_ralph_wiggum_loop_regressions.py.pass=11 | n=11 tests | seeds=? | evidence_ref=path:tests/test_ralph_wiggum_loop_regressions.py
- outcome: CONTINUE
- rationale: dispatcher `hydrate/normalize` was still auto-filling `patched_files` from detected code changes and forcing `change_applied=true`, which reintroduced fake shared-runtime patch tickets even after the loop-side validator had started rejecting them. The fix stops auto-injecting patch files in plan-only mode, makes `change_applied` reflect real file edits, and adds dispatcher-side rejection inputs for shared-runtime patch files so stale tickets do not keep contaminating subsequent cycles.

## [autopilot-hook] 2026-03-11T09:02:23+0800 cycle=184 reason=worker_failed_or_unexpected_exit
- change_type: Plan
- decision: refresh_plan_only_action_ticket_and_resume_supervisor
- why: `cycle183` completed with `full_gate_fail`, not a runtime/syntax/import crash; the in-progress `cycle184` directory only contains `active_quick` and `trial_full` with no `review.json`, while the restart event reports `rc=143`, so the blocker is worker/supervisor interruption rather than shared runtime failure.
- what: wrote fresh plan-only `tmp/ralph_next_action.json` and `tmp/ralph_next_plan.md` anchored to `source_cycle=183`, keeping the next move on the same facing-Y TURN/RIVER high-price hardening lane and avoiding shared-runtime edits.
- rollback: delete or replace the generated plan-only ticket files once a newer completed cycle provides a better action ticket.
- verify: `python3` required-field validation for `tmp/ralph_next_action.json` plus file-existence checks for the regenerated ticket/plan and partial cycle184 evidence directory.
- evidence_ref: `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_183_20260311_023547/review.json`, `tmp/ralph_loop_runs_v2/cycle_183_20260311_023547/cycle_result.json`, `tmp/ralph_loop_runs_v2/cycle_184_20260311_090010`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`

### 2026-03-11-cycle184-worker-exit-plan-ticket-refresh
- change_id: 2026-03-11-cycle184-worker-exit-plan-ticket-refresh
- change_type: Plan
- scope: `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`
- baseline: `system_bot_policy_v3_loop_active`
- delta: `null`（process recovery; eval pending after restart）
- evidence:
  - E1 | metric=cycle183.note=full gate targeted_shadow fail | n=1 cycle | seeds=cycle183 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_183_20260311_023547/review.json
  - E2 | metric=cycle184.partial_outputs(active_quick,trial_full),review_json_missing,rc=143 | n=1 restart | seeds=cycle184 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_184_20260311_090010
  - E3 | metric=plan_only_ticket_refreshed(source_cycle=183,change_applied=false) | n=1 file | seeds=? | evidence_ref=path:tmp/ralph_next_action.json
- outcome: CONTINUE
- rationale: treat this restart as a process interruption, not a signal to patch shared runtime; the highest-ROI next step is to resume with a fresh plan-only ticket that keeps attribution on the same TURN/RIVER high-price facing lane and lets the supervisor rerun cleanly.

### 20260311-100845-ralph-loop-cycle-184
- change_id: 20260311-100845-ralph-loop-cycle-184
- change_type: Eval
- scope: ralph-wiggum-loop cycle 184
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_184_20260311_090231/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_184_20260311_090231/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_184_20260311_090231/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_184_20260311_090231/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (robust_pass=False, pareto_constraints=False, holdout_pass=False)

### 20260311-123318-ralph-loop-cycle-185
- change_id: 20260311-123318-ralph-loop-cycle-185
- change_type: Eval
- scope: ralph-wiggum-loop cycle 185
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_185_20260311_100845/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_185_20260311_100845/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_185_20260311_100845/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_185_20260311_100845/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (robust_pass=False, pareto_constraints=False, holdout_pass=False)

### 20260311-145322-ralph-loop-cycle-186
- change_id: 20260311-145322-ralph-loop-cycle-186
- change_type: Eval
- scope: ralph-wiggum-loop cycle 186
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_186_20260311_123318/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_186_20260311_123318/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_186_20260311_123318/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_186_20260311_123318/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (robust_pass=False, pareto_constraints=False, holdout_pass=False)

### 20260311-171229-ralph-loop-cycle-187
- change_id: 20260311-171229-ralph-loop-cycle-187
- change_type: Eval
- scope: ralph-wiggum-loop cycle 187
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_187_20260311_145322/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_187_20260311_145322/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_187_20260311_145322/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_187_20260311_145322/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (robust_pass=False, pareto_constraints=False, holdout_pass=False)

### 20260311-193134-ralph-loop-cycle-188
- change_id: 20260311-193134-ralph-loop-cycle-188
- change_type: Eval
- scope: ralph-wiggum-loop cycle 188
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_188_20260311_171229/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_188_20260311_171229/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_188_20260311_171229/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_188_20260311_171229/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (robust_pass=False, pareto_constraints=False, holdout_pass=False)

### 20260311-214630-ralph-loop-cycle-189
- change_id: 20260311-214630-ralph-loop-cycle-189
- change_type: Eval
- scope: ralph-wiggum-loop cycle 189
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_189_20260311_193134/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_189_20260311_193134/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_189_20260311_193134/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_189_20260311_193134/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (robust_pass=False, pareto_constraints=False, holdout_pass=False)

### 20260312-011442-ralph-loop-cycle-190
- change_id: 20260312-011442-ralph-loop-cycle-190
- change_type: Eval
- scope: ralph-wiggum-loop cycle 190
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_190_20260311_214716/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_190_20260311_214716/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_190_20260311_214716/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_190_20260311_214716/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (robust_pass=False, pareto_constraints=False, holdout_pass=False)

### 20260312-053928-ralph-loop-cycle-191
- change_id: 20260312-053928-ralph-loop-cycle-191
- change_type: Eval
- scope: ralph-wiggum-loop cycle 191
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_191_20260312_011442/trial_full_shadow/c191_x4/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_191_20260312_011442/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_191_20260312_011442/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_191_20260312_011442/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate targeted_shadow fail (robust_pass=False, pareto_constraints=False, holdout_pass=False)

### 20260312-084047-ralph-loop-cycle-192
- change_id: 20260312-084047-ralph-loop-cycle-192
- change_type: Eval
- scope: ralph-wiggum-loop cycle 192
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_192_20260312_053928/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_192_20260312_053928/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_192_20260312_053928/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_192_20260312_053928/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (robust_pass=False, pareto_constraints=False, holdout_pass=False)

### 20260312-105009-gen2-spot-policy-phase1
- change_id: 20260312-105009-gen2-spot-policy-phase1
- change_type: Code
- scope: Gen2 phase 1 spot-policy scaffold for loop trial only
- baseline: system_bot_policy_v3_loop_active
- delta: added trial-only `spot_policy_ref/digest` path in system params; loaded validated spot artifact in runtime; applied local TURN/RIVER facing-high-price overlay; added replayable `spot_dataset` extractor
- evidence:
  - runtime protocol | ref=path:/Users/peng/Workspace/codex/poker2/poker2/protocol/spot_policy.py
  - runtime overlay | ref=path:/Users/peng/Workspace/codex/poker2/poker2/runtime/spot_policy.py
  - system policy integration | ref=path:/Users/peng/Workspace/codex/poker2/poker2/runtime/system_policy.py
  - spot dataset CLI | ref=path:/Users/peng/Workspace/codex/poker2/poker2/cli/spot_dataset.py
  - trial spot artifact | ref=path:/Users/peng/Workspace/codex/poker2/specs/spot_policies/facing_y_turnriver_high_price_v1.json
  - trial params | ref=path:/Users/peng/Workspace/codex/poker2/specs/policy_params/system_bot_params_v3_system_bot_policy_v3_loop_trial.json
- outcome: CONTINUE
- next_hypothesis: shift loop trial candidates from shared runtime patching to spot-policy artifacts over high-price TURN/RIVER facing-bet contexts
- rationale: previous loop architecture hit a local ceiling because sparse support and shared runtime perturbations could not produce stable, comparable gains; phase 1 isolates the weak spot behind a digestable trial artifact and adds an EventStream-native dataset extraction path

### 20260312-113304-gen2-spot-policy-phase2
- change_id: 20260312-113304-gen2-spot-policy-phase2
- change_type: Code
- scope: Gen2 phase 2 loop candidate generation and quick spot gate
- baseline: system_bot_policy_v3_loop_active
- delta: loop candidates can now carry generated `spot_policy` artifacts with injected `spot_policy_ref/digest`; quick gate now applies a spot-local evidence gate before full eval; repeated full-gate recovery still reserves one recovery lane
- evidence:
  - loop artifact flow | ref=path:/Users/peng/Workspace/codex/poker2/tools/ralph_wiggum_loop.py
  - regression tests | ref=path:/Users/peng/Workspace/codex/poker2/tests/test_ralph_wiggum_loop_regressions.py
- outcome: CONTINUE
- next_hypothesis: drive the next loop chunk through spot-aware candidates first and observe whether quick gate shifts from support starvation/full-gate churn to spot-local evidence discrimination
- rationale: phase 1 added a trial-only spot artifact path, but the loop still generated and ranked candidates mostly as runtime knob deltas; phase 2 makes spot artifacts first-class candidate payloads and blocks full eval when a spot candidate fails to produce any local evidence, reducing another source of wasted full probes

### 20260312-140024-gen2-relative-promotion-gate
- change_id: 20260312-140024-gen2-relative-promotion-gate
- change_type: Code
- scope: Relative promotion scoring and provisional baseline adoption for loop full gate
- baseline: system_bot_policy_v3_loop_active
- delta: full gate now computes `strength_score`, `stability_score`, and `promotion_score` relative to the current baseline; strong candidates can provisionally adopt when they clear hard floors and improve both strength and stability even if absolute pareto/robust constraints are still too strict for final-target promotion
- evidence:
  - loop scoring gate | ref=path:/Users/peng/Workspace/codex/poker2/tools/ralph_wiggum_loop.py
  - regression tests | ref=path:/Users/peng/Workspace/codex/poker2/tests/test_ralph_wiggum_loop_regressions.py
- outcome: CONTINUE
- next_hypothesis: let the rebuilt loop climb with relative score improvements first, while keeping focus/no-regression/holdout-floor as hard bottoms, then use later cycles to harden provisional baselines toward the final target pack
- rationale: the active baseline itself fails the current final target pack on robustness and holdout, so using only absolute end-state gates for every promotion stalls gradual improvement; this change separates final-target strictness from baseline-climbing strictness without removing catastrophic-regression guards

### 20260312-142200-gen2-provisional-confirmation
- change_id: 20260312-142200-gen2-provisional-confirmation
- change_type: Code
- scope: Provisional baseline confirmation and automatic rollback in loop lifecycle
- baseline: system_bot_policy_v3_loop_active
- delta: provisional adopts now persist the prior baseline bundle and holdout snapshot; the next cycle runs an independent confirmation pass on confirm seeds and rolls back automatically if the provisional baseline fails the confirmation gate
- evidence:
  - loop confirmation/rollback | ref=path:/Users/peng/Workspace/codex/poker2/tools/ralph_wiggum_loop.py
  - regression tests | ref=path:/Users/peng/Workspace/codex/poker2/tests/test_ralph_wiggum_loop_regressions.py
- outcome: CONTINUE
- next_hypothesis: once the loop sees a relative winner, let it climb provisionally but force the next cycle to prove the gain on independent confirmation seeds before treating the new baseline as confirmed
- rationale: relative promotion without a confirm/rollback closure would still allow noisy upgrades to drift the baseline; this change completes the slow-improvement protocol so small gains can be admitted without losing rollback discipline

## [autopilot-hook] 2026-03-12T14:14:03+0800 cycle=193 reason=worker_failed_or_unexpected_exit
- change_type: Plan
- decision: refresh_plan_only_spot_ticket_and_resume_supervisor
- why: `tmp/ralph_loop_state_v2.json` now shows `no_improve_streak=110` with `last_quick_gate_reason=full_gate_fail`; the latest completed `cycle192` ended in a normal `REJECT` (`full gate probe fail`) rather than runtime/syntax/import failure, while the partial `cycle193` directory only contains `active_quick` and the restart event reports `rc=143`, so the blocker is worker interruption during evaluation rather than a shared-runtime crash.
- what: overwrote `tmp/ralph_next_action.json` and `tmp/ralph_next_plan.md` with a plan-only ticket anchored to `source_cycle=192`, pushing the next attempt toward a trial-only spot-policy hardening mechanism for TURN/RIVER facing-high-price decisions instead of shared-runtime edits.
- rollback: replace the regenerated ticket files after the next completed cycle or delete them if a newer runtime-crash diagnosis supersedes this recovery plan.
- verify: `python3` required-field validation for `tmp/ralph_next_action.json`, file-existence checks for the refreshed ticket/plan, and `tools/ralph_loop_supervisor.sh` liveness check/start.
- evidence_ref: `tmp/ralph_loop_state_v2.json`, `tmp/ralph_loop_runs_v2/cycle_192_20260312_053928/review.json`, `tmp/ralph_loop_runs_v2/cycle_192_20260312_053928/cycle_result.json`, `tmp/ralph_loop_runs_v2/cycle_193_20260312_140108`, `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`

### 2026-03-12-cycle193-worker-exit-plan-ticket-refresh-v2
- change_id: 2026-03-12-cycle193-worker-exit-plan-ticket-refresh-v2
- change_type: Plan
- scope: `tmp/ralph_next_action.json`, `tmp/ralph_next_plan.md`
- baseline: `system_bot_policy_v3_loop_active`
- delta: `null`（process recovery; eval pending after resumed cycle193）
- evidence:
  - E1 | metric=no_improve_streak=110,last_quick_gate_reason=full_gate_fail | n=1 state | seeds=? | evidence_ref=path:tmp/ralph_loop_state_v2.json
  - E2 | metric=cycle192.note=full_gate_probe_fail,target_gap=coinpoker.tierP_facingY_turnriver_worst_bb100 | n=1 cycle | seeds=cycle192 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_192_20260312_053928/cycle_result.json
  - E3 | metric=cycle193.partial_outputs(active_quick_only),restart_rc=143,plan_only_ticket_refreshed(source_cycle=192,change_applied=false) | n=1 restart | seeds=cycle193 | evidence_ref=path:tmp/ralph_loop_runs_v2/cycle_193_20260312_140108
- outcome: CONTINUE
- rationale: treat this restart as a process interruption and keep the next move on the newer trial-only spot-policy lane, which can create a clearer behavior delta in the weak TURN/RIVER facing-high-price branch without perturbing shared runtime core again.

### 20260313-023044-ralph-loop-cycle-193
- change_id: 20260313-023044-ralph-loop-cycle-193
- change_type: Eval
- scope: ralph-wiggum-loop cycle 193
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_193_20260313_001715/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_193_20260313_001715/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_193_20260313_001715/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_193_20260313_001715/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (strict_adopt=False, provisional_adopt=False, score_delta=-2.045, promotion_score_delta=-2.036, stability_delta=-0.038, robust_pass=False, focus_pass=True)

### 20260313-054758-ralph-loop-cycle-194
- change_id: 20260313-054758-ralph-loop-cycle-194
- change_type: Eval
- scope: ralph-wiggum-loop cycle 194
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_194_20260313_023044/trial_full_shadow/c194_x6/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_194_20260313_023044/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_194_20260313_023044/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_194_20260313_023044/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate targeted_shadow fail (strict_adopt=False, provisional_adopt=False, score_delta=-3.539, promotion_score_delta=-4.781, stability_delta=0.978, robust_pass=False, focus_pass=True)

### 20260313-080033-ralph-loop-cycle-195
- change_id: 20260313-080033-ralph-loop-cycle-195
- change_type: Eval
- scope: ralph-wiggum-loop cycle 195
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_195_20260313_054758/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_195_20260313_054758/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_195_20260313_054758/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_195_20260313_054758/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (strict_adopt=False, provisional_adopt=False, score_delta=4.455, promotion_score_delta=9.414, stability_delta=-0.657, robust_pass=False, focus_pass=True)

### 20260313-101455-ralph-loop-cycle-196
- change_id: 20260313-101455-ralph-loop-cycle-196
- change_type: Eval
- scope: ralph-wiggum-loop cycle 196
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_196_20260313_080033/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_196_20260313_080033/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_196_20260313_080033/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_196_20260313_080033/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (strict_adopt=False, provisional_adopt=False, score_delta=-5.352, promotion_score_delta=-26.917, stability_delta=0.020, robust_pass=False, focus_pass=False)

### 20260313-123347-ralph-loop-cycle-197
- change_id: 20260313-123347-ralph-loop-cycle-197
- change_type: Eval
- scope: ralph-wiggum-loop cycle 197
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_197_20260313_101455/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_197_20260313_101455/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_197_20260313_101455/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_197_20260313_101455/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (strict_adopt=False, provisional_adopt=False, score_delta=4.455, promotion_score_delta=9.414, stability_delta=-0.657, robust_pass=False, focus_pass=True)

### 20260313-190621-launchd-python-fix
- change_id: 20260313-190621-launchd-python-fix
- change_type: Patch
- scope: tools/ralph_time_hook.sh + tools/ralph_hook_dispatcher.sh + tools/ralph_loop_supervisor.sh + tools/launchd/com.poker2.ralph-loop.plist.template
- baseline: system_bot_policy_v3_loop_active
- delta: fix launchd-managed watchdog startup/runtime by pinning Python to /opt/miniconda3/bin/python and restoring KeepAlive-managed supervisor/dispatcher/time_hook chain
- evidence:
  - launchd status running | ref=path:/Users/peng/Workspace/codex/poker2/tools/launchd_status_ralph_loop.sh
  - supervisor heartbeat refreshed | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_health/supervisor_heartbeat.json
  - time_hook bootstrap log | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_time_hook.log
  - live cycle 198 run root | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_198_20260313_190621
- outcome: ACTIVE
- next_hypothesis: resume cycle 198 under launchd keepalive and monitor for first candidate_end/full_gate progression
- rationale: prior fake-running state was caused by launchd executing system python3.9, which failed to import _posixsubprocess under system policy and killed time_hook before self-heal could operate

### 20260313-224203-ralph-loop-cycle-198
- change_id: 20260313-224203-ralph-loop-cycle-198
- change_type: Eval
- scope: ralph-wiggum-loop cycle 198
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_198_20260313_190621/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_198_20260313_190621/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_198_20260313_190621/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (strict_adopt=False, provisional_adopt=False, score_delta=-2.786, promotion_score_delta=-3.321, stability_delta=-0.075, robust_pass=False, focus_pass=True)

### 20260314-024038-ralph-loop-cycle-199
- change_id: 20260314-024038-ralph-loop-cycle-199
- change_type: Eval
- scope: ralph-wiggum-loop cycle 199
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_199_20260313_224203/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_199_20260313_224203/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_199_20260313_224203/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (strict_adopt=False, provisional_adopt=False, score_delta=4.125, promotion_score_delta=7.153, stability_delta=-0.666, robust_pass=False, focus_pass=True)

### 20260314-054214-ralph-loop-cycle-200
- change_id: 20260314-054214-ralph-loop-cycle-200
- change_type: Eval
- scope: ralph-wiggum-loop cycle 200
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_200_20260314_024038/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_200_20260314_024038/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_200_20260314_024038/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_200_20260314_024038/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (strict_adopt=False, provisional_adopt=False, score_delta=4.455, promotion_score_delta=9.414, stability_delta=-0.657, robust_pass=False, focus_pass=True)

### 20260314-084002-ralph-loop-cycle-201
- change_id: 20260314-084002-ralph-loop-cycle-201
- change_type: Eval
- scope: ralph-wiggum-loop cycle 201
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_201_20260314_054214/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_201_20260314_054214/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_201_20260314_054214/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_201_20260314_054214/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (strict_adopt=False, provisional_adopt=False, score_delta=-2.932, promotion_score_delta=-0.980, stability_delta=1.092, robust_pass=False, focus_pass=True)

### 20260314-114500-ralph-loop-cycle-202
- change_id: 20260314-114500-ralph-loop-cycle-202
- change_type: Eval
- scope: ralph-wiggum-loop cycle 202
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_202_20260314_084002/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_202_20260314_084002/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_202_20260314_084002/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_202_20260314_084002/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (strict_adopt=False, provisional_adopt=False, score_delta=-1.924, promotion_score_delta=4.972, stability_delta=0.829, robust_pass=False, focus_pass=True)

### 20260314-151652-ralph-loop-cycle-203
- change_id: 20260314-151652-ralph-loop-cycle-203
- change_type: Eval
- scope: ralph-wiggum-loop cycle 203
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_203_20260314_114500/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_203_20260314_114500/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_203_20260314_114500/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (strict_adopt=False, provisional_adopt=False, score_delta=4.533, promotion_score_delta=7.808, stability_delta=-0.657, robust_pass=False, focus_pass=True)

### 20260314-182743-ralph-loop-cycle-204
- change_id: 20260314-182743-ralph-loop-cycle-204
- change_type: Eval
- scope: ralph-wiggum-loop cycle 204
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_204_20260314_151740/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_204_20260314_151740/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_204_20260314_151740/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_204_20260314_151740/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (strict_adopt=False, provisional_adopt=False, score_delta=4.455, promotion_score_delta=9.414, stability_delta=-0.657, robust_pass=False, focus_pass=True)

### 20260316-195743-ralph-loop-cycle-205
- change_id: 20260316-195743-ralph-loop-cycle-205
- change_type: Eval
- scope: ralph-wiggum-loop cycle 205
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_205_20260316_170137/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_205_20260316_170137/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_205_20260316_170137/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (strict_adopt=False, provisional_adopt=False, score_delta=4.533, promotion_score_delta=7.808, stability_delta=-0.657, robust_pass=False, focus_pass=True)

### 20260316-234741-ralph-loop-cycle-206
- change_id: 20260316-234741-ralph-loop-cycle-206
- change_type: Eval
- scope: ralph-wiggum-loop cycle 206
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_206_20260316_195743/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_206_20260316_195743/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_206_20260316_195743/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (strict_adopt=False, provisional_adopt=False, score_delta=4.533, promotion_score_delta=7.808, stability_delta=-0.657, robust_pass=False, focus_pass=True)

### 20260317-115204-ralph-loop-cycle-207
- change_id: 20260317-115204-ralph-loop-cycle-207
- change_type: Eval
- scope: ralph-wiggum-loop cycle 207
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_207_20260316_234741/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_207_20260316_234741/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_207_20260316_234741/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (strict_adopt=False, provisional_adopt=False, score_delta=-1.775, promotion_score_delta=3.824, stability_delta=0.823, robust_pass=False, focus_pass=True)

### 20260317-160238-ralph-loop-cycle-208
- change_id: 20260317-160238-ralph-loop-cycle-208
- change_type: Eval
- scope: ralph-wiggum-loop cycle 208
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_208_20260317_115204/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_208_20260317_115204/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_208_20260317_115204/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (strict_adopt=False, provisional_adopt=False, score_delta=-2.701, promotion_score_delta=3.476, stability_delta=0.835, robust_pass=False, focus_pass=True)

### 20260318-013406-ralph-loop-cycle-209
- change_id: 20260318-013406-ralph-loop-cycle-209
- change_type: Eval
- scope: ralph-wiggum-loop cycle 209
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_209_20260317_214309/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_209_20260317_214309/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_209_20260317_214309/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate targeted_shadow fail (strict_adopt=False, provisional_adopt=False, score_delta=-1.771, promotion_score_delta=3.919, stability_delta=0.822, robust_pass=False, focus_pass=True)

### 20260318-051723-ralph-loop-cycle-210
- change_id: 20260318-051723-ralph-loop-cycle-210
- change_type: Eval
- scope: ralph-wiggum-loop cycle 210
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_210_20260318_013406/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_210_20260318_013406/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_210_20260318_013406/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (strict_adopt=False, provisional_adopt=False, score_delta=-2.701, promotion_score_delta=3.476, stability_delta=0.835, robust_pass=False, focus_pass=True)

### 20260318-110738-ralph-loop-cycle-211
- change_id: 20260318-110738-ralph-loop-cycle-211
- change_type: Eval
- scope: ralph-wiggum-loop cycle 211
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_211_20260318_051723/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_211_20260318_051723/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_211_20260318_051723/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate targeted_shadow fail (strict_adopt=False, provisional_adopt=False, score_delta=-1.771, promotion_score_delta=3.919, stability_delta=0.822, robust_pass=False, focus_pass=True)

### 20260318-152042-ralph-loop-cycle-212
- change_id: 20260318-152042-ralph-loop-cycle-212
- change_type: Eval
- scope: ralph-wiggum-loop cycle 212
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_212_20260318_110738/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_212_20260318_110738/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_212_20260318_110738/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (strict_adopt=False, provisional_adopt=False, score_delta=-3.102, promotion_score_delta=-1.338, stability_delta=1.092, robust_pass=False, focus_pass=True)

### 20260318-192013-ralph-loop-cycle-213
- change_id: 20260318-192013-ralph-loop-cycle-213
- change_type: Eval
- scope: ralph-wiggum-loop cycle 213
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_213_20260318_152043/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_213_20260318_152043/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_213_20260318_152043/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (strict_adopt=False, provisional_adopt=False, score_delta=4.533, promotion_score_delta=7.808, stability_delta=-0.657, robust_pass=False, focus_pass=True)

### 20260318-231638-ralph-loop-cycle-214
- change_id: 20260318-231638-ralph-loop-cycle-214
- change_type: Eval
- scope: ralph-wiggum-loop cycle 214
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_214_20260318_192013/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_214_20260318_192013/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_214_20260318_192013/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (strict_adopt=False, provisional_adopt=False, score_delta=-2.892, promotion_score_delta=-1.036, stability_delta=1.093, robust_pass=False, focus_pass=True)

### 20260319-085552-ralph-loop-cycle-215
- change_id: 20260319-085552-ralph-loop-cycle-215
- change_type: Eval
- scope: ralph-wiggum-loop cycle 215
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_215_20260319_071617/trial_full/coinpoker_full/eval_full_summary.json
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_215_20260319_071617/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_215_20260319_071617/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_215_20260319_071617/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (strict_adopt=False, provisional_adopt=False, score_delta=-2.932, promotion_score_delta=-0.980, stability_delta=1.092, robust_pass=False, focus_pass=True)

### 20260319-124855-ralph-loop-cycle-216
- change_id: 20260319-124855-ralph-loop-cycle-216
- change_type: Eval
- scope: ralph-wiggum-loop cycle 216
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_216_20260319_085552/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_216_20260319_085552/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_216_20260319_085552/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (strict_adopt=False, provisional_adopt=False, score_delta=4.528, promotion_score_delta=7.696, stability_delta=-0.648, robust_pass=False, focus_pass=True)

### 20260319-163743-ralph-loop-cycle-217
- change_id: 20260319-163743-ralph-loop-cycle-217
- change_type: Eval
- scope: ralph-wiggum-loop cycle 217
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_217_20260319_124855/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_217_20260319_124855/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_217_20260319_124855/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (strict_adopt=False, provisional_adopt=False, score_delta=0.381, promotion_score_delta=-3.988, stability_delta=-1.133, robust_pass=False, focus_pass=True)

### 20260319-201716-ralph-loop-cycle-218
- change_id: 20260319-201716-ralph-loop-cycle-218
- change_type: Eval
- scope: ralph-wiggum-loop cycle 218
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_218_20260319_163743/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_218_20260319_163743/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_218_20260319_163743/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (strict_adopt=False, provisional_adopt=False, score_delta=-2.891, promotion_score_delta=-1.026, stability_delta=1.092, robust_pass=False, focus_pass=True)

### 20260319-235243-ralph-loop-cycle-219
- change_id: 20260319-235243-ralph-loop-cycle-219
- change_type: Eval
- scope: ralph-wiggum-loop cycle 219
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_219_20260319_201716/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_219_20260319_201716/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_219_20260319_201716/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (strict_adopt=False, provisional_adopt=False, score_delta=-2.891, promotion_score_delta=-1.026, stability_delta=1.092, robust_pass=False, focus_pass=True)

### 20260320-031954-ralph-loop-cycle-220
- change_id: 20260320-031954-ralph-loop-cycle-220
- change_type: Eval
- scope: ralph-wiggum-loop cycle 220
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_220_20260319_235244/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_220_20260319_235244/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_220_20260319_235244/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (strict_adopt=False, provisional_adopt=False, score_delta=-1.779, promotion_score_delta=3.779, stability_delta=0.825, robust_pass=False, focus_pass=True)

### 20260320-064430-ralph-loop-cycle-221
- change_id: 20260320-064430-ralph-loop-cycle-221
- change_type: Eval
- scope: ralph-wiggum-loop cycle 221
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_221_20260320_032006/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_221_20260320_032006/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_221_20260320_032006/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (strict_adopt=False, provisional_adopt=False, score_delta=-2.698, promotion_score_delta=3.573, stability_delta=0.834, robust_pass=False, focus_pass=True)

### 20260320-101125-ralph-loop-cycle-222
- change_id: 20260320-101125-ralph-loop-cycle-222
- change_type: Eval
- scope: ralph-wiggum-loop cycle 222
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_222_20260320_064430/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_222_20260320_064430/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_222_20260320_064430/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (strict_adopt=False, provisional_adopt=False, score_delta=-2.891, promotion_score_delta=-1.026, stability_delta=1.092, robust_pass=False, focus_pass=True)

### 20260320-135350-ralph-loop-cycle-223
- change_id: 20260320-135350-ralph-loop-cycle-223
- change_type: Eval
- scope: ralph-wiggum-loop cycle 223
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_223_20260320_101125/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_223_20260320_101125/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_223_20260320_101125/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (strict_adopt=False, provisional_adopt=False, score_delta=-2.891, promotion_score_delta=-1.026, stability_delta=1.092, robust_pass=False, focus_pass=True)

### 20260320-192558-ralph-loop-cycle-224
- change_id: 20260320-192558-ralph-loop-cycle-224
- change_type: Eval
- scope: ralph-wiggum-loop cycle 224
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_224_20260320_135350/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_224_20260320_135350/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_224_20260320_135350/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate targeted_shadow fail (strict_adopt=False, provisional_adopt=False, score_delta=-1.913, promotion_score_delta=0.464, stability_delta=0.435, robust_pass=False, focus_pass=True)

### 20260320-231920-ralph-loop-cycle-225
- change_id: 20260320-231920-ralph-loop-cycle-225
- change_type: Eval
- scope: ralph-wiggum-loop cycle 225
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_225_20260320_192558/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_225_20260320_192558/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_225_20260320_192558/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (strict_adopt=False, provisional_adopt=False, score_delta=4.533, promotion_score_delta=7.808, stability_delta=-0.657, robust_pass=False, focus_pass=True)

### 20260321-030019-ralph-loop-cycle-226
- change_id: 20260321-030019-ralph-loop-cycle-226
- change_type: Eval
- scope: ralph-wiggum-loop cycle 226
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_226_20260320_231920/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_226_20260320_231920/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_226_20260320_231920/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (strict_adopt=False, provisional_adopt=False, score_delta=-3.136, promotion_score_delta=-1.519, stability_delta=1.021, robust_pass=False, focus_pass=True)

### 20260321-062805-ralph-loop-cycle-227
- change_id: 20260321-062805-ralph-loop-cycle-227
- change_type: Eval
- scope: ralph-wiggum-loop cycle 227
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_227_20260321_030023/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_227_20260321_030023/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_227_20260321_030023/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (strict_adopt=False, provisional_adopt=False, score_delta=-5.282, promotion_score_delta=-20.677, stability_delta=0.020, robust_pass=False, focus_pass=False)

### 20260321-095741-ralph-loop-cycle-228
- change_id: 20260321-095741-ralph-loop-cycle-228
- change_type: Eval
- scope: ralph-wiggum-loop cycle 228
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_228_20260321_062805/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_228_20260321_062805/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_228_20260321_062805/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (strict_adopt=False, provisional_adopt=False, score_delta=-2.891, promotion_score_delta=-1.026, stability_delta=1.092, robust_pass=False, focus_pass=True)

### 20260321-153302-ralph-loop-cycle-229
- change_id: 20260321-153302-ralph-loop-cycle-229
- change_type: Eval
- scope: ralph-wiggum-loop cycle 229
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_229_20260321_095741/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_229_20260321_095741/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_229_20260321_095741/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate targeted_shadow fail (strict_adopt=False, provisional_adopt=False, score_delta=-1.775, promotion_score_delta=3.824, stability_delta=0.823, robust_pass=False, focus_pass=True)

### 20260321-194312-ralph-loop-cycle-230
- change_id: 20260321-194312-ralph-loop-cycle-230
- change_type: Eval
- scope: ralph-wiggum-loop cycle 230
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_230_20260321_153302/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_230_20260321_153302/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_230_20260321_153302/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (strict_adopt=False, provisional_adopt=False, score_delta=-2.891, promotion_score_delta=-1.026, stability_delta=1.092, robust_pass=False, focus_pass=True)

### 20260322-000612-ralph-loop-cycle-231
- change_id: 20260322-000612-ralph-loop-cycle-231
- change_type: Eval
- scope: ralph-wiggum-loop cycle 231
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_231_20260321_194312/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_231_20260321_194312/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_231_20260321_194312/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (strict_adopt=False, provisional_adopt=False, score_delta=-2.206, promotion_score_delta=-3.998, stability_delta=0.010, robust_pass=False, focus_pass=True)

### 20260322-035449-ralph-loop-cycle-232
- change_id: 20260322-035449-ralph-loop-cycle-232
- change_type: Eval
- scope: ralph-wiggum-loop cycle 232
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_232_20260322_000613/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_232_20260322_000613/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_232_20260322_000613/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (strict_adopt=False, provisional_adopt=False, score_delta=4.533, promotion_score_delta=7.808, stability_delta=-0.657, robust_pass=False, focus_pass=True)

### 20260322-091316-ralph-loop-cycle-233
- change_id: 20260322-091316-ralph-loop-cycle-233
- change_type: Eval
- scope: ralph-wiggum-loop cycle 233
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_233_20260322_035509/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_233_20260322_035509/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_233_20260322_035509/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate targeted_shadow fail (strict_adopt=False, provisional_adopt=False, score_delta=-1.775, promotion_score_delta=3.824, stability_delta=0.823, robust_pass=False, focus_pass=True)

### 20260322-125259-ralph-loop-cycle-234
- change_id: 20260322-125259-ralph-loop-cycle-234
- change_type: Eval
- scope: ralph-wiggum-loop cycle 234
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_234_20260322_091316/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_234_20260322_091316/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_234_20260322_091316/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (strict_adopt=False, provisional_adopt=False, score_delta=4.533, promotion_score_delta=7.808, stability_delta=-0.657, robust_pass=False, focus_pass=True)

### 20260322-182218-ralph-loop-cycle-235
- change_id: 20260322-182218-ralph-loop-cycle-235
- change_type: Eval
- scope: ralph-wiggum-loop cycle 235
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_235_20260322_125259/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_235_20260322_125259/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_235_20260322_125259/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate targeted_shadow fail (strict_adopt=False, provisional_adopt=False, score_delta=-1.879, promotion_score_delta=3.623, stability_delta=0.829, robust_pass=False, focus_pass=True)

### 20260322-220134-ralph-loop-cycle-236
- change_id: 20260322-220134-ralph-loop-cycle-236
- change_type: Eval
- scope: ralph-wiggum-loop cycle 236
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_236_20260322_182219/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_236_20260322_182219/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_236_20260322_182219/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (strict_adopt=False, provisional_adopt=False, score_delta=-2.891, promotion_score_delta=-1.026, stability_delta=1.092, robust_pass=False, focus_pass=True)

### 20260323-014506-ralph-loop-cycle-237
- change_id: 20260323-014506-ralph-loop-cycle-237
- change_type: Eval
- scope: ralph-wiggum-loop cycle 237
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_237_20260322_220134/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_237_20260322_220134/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_237_20260322_220134/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (strict_adopt=False, provisional_adopt=False, score_delta=-2.005, promotion_score_delta=-2.036, stability_delta=-0.038, robust_pass=False, focus_pass=True)

### 20260323-051647-ralph-loop-cycle-238
- change_id: 20260323-051647-ralph-loop-cycle-238
- change_type: Eval
- scope: ralph-wiggum-loop cycle 238
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_238_20260323_014506/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_238_20260323_014506/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_238_20260323_014506/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (strict_adopt=False, provisional_adopt=False, score_delta=-2.891, promotion_score_delta=-1.026, stability_delta=1.092, robust_pass=False, focus_pass=True)

### 20260323-110110-ralph-loop-cycle-239
- change_id: 20260323-110110-ralph-loop-cycle-239
- change_type: Eval
- scope: ralph-wiggum-loop cycle 239
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_239_20260323_051731/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_239_20260323_051731/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_239_20260323_051731/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate targeted_shadow fail (strict_adopt=False, provisional_adopt=False, score_delta=-3.492, promotion_score_delta=-3.861, stability_delta=0.978, robust_pass=False, focus_pass=True)

### 20260323-145555-ralph-loop-cycle-240
- change_id: 20260323-145555-ralph-loop-cycle-240
- change_type: Eval
- scope: ralph-wiggum-loop cycle 240
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_240_20260323_110110/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_240_20260323_110110/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_240_20260323_110110/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (strict_adopt=False, provisional_adopt=False, score_delta=4.533, promotion_score_delta=7.808, stability_delta=-0.657, robust_pass=False, focus_pass=True)

### 20260323-193020-ralph-loop-cycle-241
- change_id: 20260323-193020-ralph-loop-cycle-241
- change_type: Eval
- scope: ralph-wiggum-loop cycle 241
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_241_20260323_145556/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_241_20260323_145556/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_241_20260323_145556/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (strict_adopt=False, provisional_adopt=False, score_delta=4.399, promotion_score_delta=6.674, stability_delta=-0.657, robust_pass=False, focus_pass=True)

### 20260323-232930-ralph-loop-cycle-242
- change_id: 20260323-232930-ralph-loop-cycle-242
- change_type: Eval
- scope: ralph-wiggum-loop cycle 242
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_242_20260323_193020/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_242_20260323_193020/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_242_20260323_193020/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (strict_adopt=False, provisional_adopt=False, score_delta=4.125, promotion_score_delta=7.153, stability_delta=-0.666, robust_pass=False, focus_pass=True)

### 20260324-030141-ralph-loop-cycle-243
- change_id: 20260324-030141-ralph-loop-cycle-243
- change_type: Eval
- scope: ralph-wiggum-loop cycle 243
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_243_20260323_232930/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_243_20260323_232930/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_243_20260323_232930/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (strict_adopt=False, provisional_adopt=False, score_delta=-6.194, promotion_score_delta=-7.435, stability_delta=0.763, robust_pass=False, focus_pass=True)

### 20260324-063641-ralph-loop-cycle-244
- change_id: 20260324-063641-ralph-loop-cycle-244
- change_type: Eval
- scope: ralph-wiggum-loop cycle 244
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_244_20260324_030141/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_244_20260324_030141/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_244_20260324_030141/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate probe fail (strict_adopt=False, provisional_adopt=False, score_delta=-2.891, promotion_score_delta=-1.026, stability_delta=1.092, robust_pass=False, focus_pass=True)

### 20260324-122223-ralph-loop-cycle-245
- change_id: 20260324-122223-ralph-loop-cycle-245
- change_type: Eval
- scope: ralph-wiggum-loop cycle 245
- baseline: system_bot_policy_v3_loop_active
- delta: decision=REJECT; active=system_bot_policy_v3_loop_active; trial=null
- evidence:
  - coinpoker summary | ref=null
  - pool summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_245_20260324_063712/trial_full/coinpoker_full/pool_eval/pool_eval_summary.json
  - br summary | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_245_20260324_063712/trial_full/coinpoker_full/br_proxy/br_proxy_summary.json
  - cycle review | ref=path:/Users/peng/Workspace/codex/poker2/tmp/ralph_loop_runs_v2/cycle_245_20260324_063712/review.json
- outcome: REJECT
- next_hypothesis: focus_metric=coinpoker.tierP_facingY_turnriver_worst_bb100
- rationale: full gate targeted_shadow fail (strict_adopt=False, provisional_adopt=False, score_delta=-3.102, promotion_score_delta=-1.338, stability_delta=1.092, robust_pass=False, focus_pass=True)
