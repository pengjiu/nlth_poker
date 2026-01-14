# AGENTS.md （给 Codex/AI 编程工具）

> 目标：用**最少**规则把实现落到“可运行 + 可回放 + 可门禁”的状态，并避免后续反复修基础一致性。
>
> 唯一规范来源：`ARCHIETECTURE.md.md` 的 **Normative 区（第 3–7 章 + 0.3 权威锚点表）**。

---

## 1) 硬规则（必须遵守）

### 单一真相
- **MUST** 任何口径/结构/枚举/哈希构造只允许来自权威锚点（0.3 表）。实现中不得出现第二套“等价定义”。
- **MUST** 所有 `*_id/*_hash/*_digest`：`sha256` 小写 hex（64）。
- **MUST** “无/未启用/不适用”统一用 **JSON null**；不得出现字符串 `"none"`。

### 金额与换算
- **MUST** 所有金额事实单位为 `chips(int)`。
- **MUST** 任何 `float/比例/ppm → chips(int)`、`pot_frac/uid/bins/raise_add → target_total_commit_chips` 的换算只能出现在：
  - `ActionAdapter (3.12)` / `TreePathMappingSpec (3.13)` / `Environment canonicalize→legalize (3.1.1)`。
- **MUST NOT** 其他模块/脚本/评测器出现同类换算逻辑（必须加 CI gate：lint/grep/AST 规则）。

### 证据链与可回放
- **MUST** 统计/评估只能读 `EventStream`（5.1/5.1.1）。
- **MUST** 每个 DecisionPoint 必须可回放定位：`hand_selector + decision_id + state_hash`。
- **MUST** 任何降级/替换必须同时满足：
  - `ActionChosen` 记录 proposed→executed + `mapping_trace`（3.13.1）；
  - `Stage Evidence` 标记 `degraded=true` + `degraded_reason` + `evidence_ref`（3.19.1）；
  - strict_mode 下直接 fail。

---

## 2) 实施顺序（最短落地路径）

> 原则：先把“契约/哈希/门禁/事件流”做对，再做策略与性能。

### Step A — Contract Kit（3.4.1）
交付：单一 schema 源 → 生成 Python/Rust/TS 的：
- validator（严格校验 null/受控枚举/缺字段）
- canonicalizer（3.5.1）
- hasher（所有 `*_id/*_hash/*_digest`）
- **跨语言 Test Vectors**：同输入 → 同 canonical bytes → 同 sha256

✅ Done 标准：CI 里三语言跑同一组 vectors 全一致；re-generate 后无 diff。

### Step B — Protocol 核心类型与哈希
交付（最小集即可跑通）：
- CanonicalAction（3.1）
- RuleSet + ruleset_id（3.2）
- CompatTriad（3.3）
- SchemaContract + schema_hash（3.4）
- Provenance（3.5）
- ScenarioID/Package + PathsConfig/ResolvedPaths（3.6/3.6.1）
- CacheKey（3.7）
- Snapshot（3.11）
- ActionAdapter（3.12） + TreePathMappingSpec（3.13）

✅ Done 标准：任一对象都能：validate → canonicalize → id/hash；字段缺失/枚举越界 strict_mode 下 Fail-Fast。

### Step C — Environment（唯一执行 + 唯一账本）
交付：
- DecisionPoint Snapshot 生成（3.11.1）
- legal_actions_digest 生成（3.11.2）
- canonicalize→legalize（3.1.1）
- derived_action 输出（3.9.1）
- Ledger invariants（6.1/6.1.1）

✅ Done 标准：strict_mode 下任一不变量失败立刻拒绝，并输出最小证据闭包（6.2）。

### Step D — EventStream（5.1/5.1.1）
交付：
- NDJSON 写入（LF 结尾；每行 canonicalize）
- event_model_id / event_stream_digest 计算
- replay 入口（按 hand_selector 定位）

✅ Done 标准：同 seed+options_hash 在 Tier‑A 场景下能稳定产出同 digest（3.5.2）。

### Step E — Gates/Doctor/Stats（第 7 章）
交付：
- Triad Gate（7.1）
- Schema Gate（7.2）
- Provenance Gate（7.3）
- Scenario Gate（7.4）
- Cache Correctness Gate（7.5）
- Leakage Gate（7.6）
- MW Guard（7.7）/ Opponent Suite Gate（7.8）

✅ Done 标准：每个 gate 失败都有结构化输出 + evidence_ref（6.2）。

### Step F — Golden Fixtures（5.1.2）
交付：冻结 fixtures（至少覆盖：button_rotation / forced_bets / min_raise / allin_reopen / no_flop_no_drop / rake / ledger_conservation + sidepot/all‑in runout）。

✅ Done 标准：CI 强制 replay+doctor+stats：任何 digest/报告失败拒绝合并。

---

## 3) AI 编程工作方式（让实现可控、不膨胀）

- **MUST** 小步提交：每步只引入一个“闭环”（对象闭包→gate→vector/fixture）。
- **MUST** 遇到不明确处：
  - 先在实现里选择最保守（Fail‑Fast / null / 不自动推断）；
  - 同时用 TODO/DR（0.5）标记需要在规范文档 Refine 的点；不要在代码里悄悄引入新口径。
- **MUST** 所有 `*_label/_alias/latest/path` 只进 `resolution_trace`，不得进 gate/cache/options_hash。

---

## 4) 最小验收清单（实现是否“落地”）

### 必须通过的自动化检查
- Contract Kit：三语言 Test Vectors 全一致。
- EventStream：digest 计算稳定；LF 行分隔；无 CRLF/空白行。
- Environment：
  - legal_actions_digest 与 Snapshot 约束一致（3.11.3）；
  - ledger 守恒：`sum(stack_deltas)+total_rake==0`；pot 闭环成立。
- Gate：任一 mismatch 都 Fail‑Fast + evidence_ref。
- Golden Fixtures：replay+doctor+stats 全绿。

### 必须存在的结构化字段
- ActionChosen：proposed_action / executed_action / mapping_trace / derived_action / routing(多人)/belief(可选)/mw_risk(可选)
- Run Manifest：Stage Evidence（inputs/outputs digest+counts；degraded 规则满足 3.19.1）

---

## 5) 禁止事项（最常见“返工源头”）

- 禁止在 evaluation/metrics/report 里自算：raise/all‑in/min‑raise/rake/sidepot。
- 禁止在任何地方用 float 进入 hash 输入。
- 禁止“为了跑通先给默认值”绕过 triad/schema/scenario gate。
- 禁止把 CLI 变成第二配置系统（CLI 只挑选 scenario/profile/policy/opponents + seed/strict）。

---

## 6) 输出格式约定（便于工具链与 CI）

- 所有失败：输出 machine‑readable JSON（含 gate_id/invariant_id、reason、evidence_ref）。
- 所有产物：`artifact_ref + digest + provenance_ref` 三件套齐全（3.19.1/3.5）。

---

## 7) 迭代心得必读（每次改动前先读、改完后更新）
- 路径：`notes/iteration_journal.md`
- 作用：记录当前最强基线（v5v）、近期退化原因、必守的改动流程守则、以及每次评测后的总结。所有改动前必须先阅读；每次评测后把结论追加进去，形成可追溯经验库。

> 只要严格按本文件 + 架构指南的权威锚点实现，系统就能做到：**一致性可执法、回归不可退化、跨语言不漂移**。

---

## 7) 迭代改进记录协议（轻量必做）

> 用**最小成本**保证“可复现、可定位、可执法、可回归”，避免补丁式改动。

### Baseline（必须）

```
policy_id: <commit_hash 或 policy_hash>
scenario_id: <ruleset_hash / env_hash / scenario_id>
opponent_suite_id: <opp_suite_hash>
actionspace_id: <bins_hash>
run_id: <timestamp+seed+git_short>
options_hash: <options_hash>
event_stream_digest: <event_stream_digest>
report_ref: <artifact_ref 或 report 路径>
```

要求：上述字段必须能在日志/报告/manifest 中查到，或由 `options_hash` 反推；否则视为不可复现。

### Evidence（只写 3 条，必须可定位）

每条使用同一格式：
```
bucket_key | metric=value | n=? | seed=? | evidence_ref=?
```

E1：位置×街×Facing 的最差桶  
E2：SPR 最差桶（可带 `oop_multi_street=Y/N`）  
E3：人数桶最差（2p/3p/4p…）

规则：
- 只用报告/回放统计口径（不允许推测）
- 必须带 `n` 与 `seed`
- `evidence_ref` 必须能在 report/eventstream 中 `rg` 到（结构化 key 优先）

### Change（最多 2 个提案）

每个提案结构：
```
change_1:
  type: Define | Refine | Enforce | Restructure
  objects: [<契约对象1>, <契约对象2>]  # 最多 2 个
  principle: <一句第一性原理描述：EV/信息价值/约束一致性/多人风险折价等>
  expected_generalization: <为何跨平台/跨对手仍成立，1–2 句>
  implementation_notes: <最多 5 行，只写机制，不写调参>
```

禁止：为了某个桶修复而写“如果 X 就禁止 Y”这类补丁式策略。

### Gate / Invariant（只允许 1 条，必须是“机制不变量” Fail‑Fast）

```
gate_id: CONTRACT_<ONE_THING>
scope: <preflop | postflop | settlement | solver_io | options>
condition: <纯契约条件，不含策略阈值>
on_fail_output: {gate_id, reason_code, evidence_ref, snapshot_keys[]}
```

允许的 Gate 类型（只选一种）：
- CONTRACT_ACTION_LEGALITY
- CONTRACT_LEDGER_CONSISTENCY
- CONTRACT_STRATEGY_DISTRIBUTION
- CONTRACT_RULESET_CLOSURE
- CONTRACT_SOLVER_IO

明确禁止：`raise_edge<=0 就不许 raise` 等策略禁令式 Gate。

### Regression（最小矩阵，但必须 2 seeds）

```
matrix: seed(2000,2001) × opp(<oppA>,<oppB>) × rules(<rake0>,<rakeX 或 anteX>)
hands_per_cell: 300–500
pass_criteria:
  invariant: all gates PASS
  stability: 不出现方向性崩溃（bb/100 由正转负且 |Δ|>=50，
            或 non_showdown_bb/100 / showdown_bb/100 单项恶化 >=100）
  comparators: 与 baseline 同矩阵对比（必须同 *_id）
```

### Result（只写 2 行）

```
fix: PASS | FAIL
side_effect: <若有，指向 bucket_key + n + seed；无则写 “none observed under regression matrix”>
```
