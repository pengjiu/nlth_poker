# 德州扑克AI架构指南

> 目的：为新系统提供**稳定、可长期迭代**的架构方向与边界约束。足够强约束，足够简约，可演进不膨胀，符合文档契约, 设计遵循奥卡姆剃刀 / KISS 原则。
>
> 范围：只描述“如何组织系统”与“哪些机制保证一致性”。不包含实现代码、工程细节、参数调优。

---

## 导航（Informative）

- **读哪里算“规范”**：第 **3–7 章**默认是 **Normative（规范性）**；它们定义唯一真相锚点（0.3）与可机器执法机制（门控/不变量/证据链）。其余章节默认是 Informative/Operational（0.1）。
- **第一次读的最短路径**：
  1) 先读 **0.1–0.4**（真相类型/ID-Hash-Null 约定/变更流程）；
  2) 再读 **2**（分层与依赖方向）；
  3) 重点通读 **3.1（动作口径）→ 3.11（Snapshot/合法动作）→ 5.1（事件流）→ 6（账本不变量）→ 7（门控）**。
- **落地/实施看哪里**：第 **10 章**给出阶段路线与最小退出证据（DoD）；第 **9 章**给出高 ROI 的扩展建议，但不引入新口径。
- **做变更怎么走流程**：任何变更必须先在 **0.4** 归类（Define/Refine/Enforce/Restructure），并明确落点锚点（0.3）与验证方式（回放 + 门控/不变量 + fixture/vector）。

## 0. 文档元契约

> 本节规定“唯一真相如何被定义、被引用、被修改”。
>
> 规范词：本文档仅使用 MUST / SHOULD / MAY / MUST NOT。

### 0.1 真相类型系统

- MUST 本文档内容仅允许属于三类真相类型：
  - Normative（规范性）：契约、口径、不变量、门控、ID/Hash 构造、失败证据要求。
  - Informative（解释性）：动机、背景、直觉、示例。
  - Operational（操作性）：迁移路线、验证清单、演进策略。
- MUST 只有 Normative 能产生“唯一真相”；Informative/Operational MUST NOT 引入新定义/新口径；只能引用 Normative 的权威锚点与 ID/Hash。
- MUST 默认第 3–7 章为 Normative 区；其他章节默认 Informative/Operational（除非被 0.3 标注为权威定义区）。
- MUST 第 1–2 章仅陈述目标/分层/依赖方向，不得引入任何可执行语义；任何可执行语义必须落在 0.3 指向的权威锚点（第 3–7 章）。

### 0.1.1 契约对象与权威锚点

- MUST 本文档仅允许以“契约对象（Contract Object）”引入可复用抽象（例如 RunSpec、Schema、Scenario、CacheKey、Provenance、PolicySpec、MetricsSpec、ReportSchema、AssumptionSpec 等）。
- MUST 每个契约对象具备：唯一名称 + 唯一权威锚点（0.3）+ 可版本化/可哈希标识（*_id / *_hash / *_digest）。
- MUST 除权威锚点外，任何位置 MUST NOT 重新定义对象语义；只能引用锚点与 ID/Hash。
- MUST 任何临时规则/隐式默认/口径推导若无法落入既有契约对象，必须走 0.4 的 Define。

- MUST *_hash / *_digest / *_id 仅作为不可逆指纹用于“等值比对/门控/缓存键”；若需要还原内容，必须同时提供对应契约对象或 artifact_ref 并做 digest 校验（见 3.19.1/5.1.1）。
- MUST 当 *_id 非内容哈希（例如需要人为命名）时，必须同时提供对应的 *_hash，并声明映射关系；否则视为歧义并 Fail-Fast。

### 0.1.2 ID/Hash/Label 命名与使用约定（Identifier Naming）

- MUST 任一会进入 gate/cache/options_hash 的 `*_id` 默认语义为：`hash(canonicalized <对应契约对象的内容闭包>)`；若某 `*_id` 需要人为命名（非内容哈希），则 MUST 同时提供对应的 `*_hash`（内容哈希）并声明二者映射；否则视为歧义并 Fail-Fast。
- MUST `*_id` / `*_hash` / `*_digest` 的值在未显式声明例外时一律为 **sha256 小写 hex 字符串（长度 64）**；strict_mode 下若出现大小写不一致、长度不匹配、或非 hex 字符，MUST Fail-Fast。
- MUST `*_label` / `*_alias` / `latest` 仅用于展示与人类交互：
  - MUST NOT 进入任何 *_hash 输入、options_hash、cache key 或门控判定；
  - MUST 在进入门控/缓存/执行之前被确定性解析为 `*_id`（解析过程仅允许写入 resolution_trace）。
- MUST 任一 `*_ref`（artifact_ref/path_ref 等）只表示“可定位入口”，不得被当作语义真相：
  - 需要使用其内容语义时，必须同时携带 digest（DigestObject 或等价）并在加载时校验；
  - 若 `*_ref` 采用 `path:`，则必须为相对引用且只能通过 ResolvedPaths（3.6.1）解析，并携带 resolved_paths_digest。

### 0.1.3 空值与可选字段约定（Null Convention）

- MUST 所有契约对象、事件流、报告、manifest、hash 输入中的“无/未启用/不适用”一律用 JSON null 表达。
- MUST NOT 使用字符串 "none"（或其他别名）表达空值；任何进入 *_hash / *_digest / *_id / options_hash 的输入若出现字符串 "none"，strict_mode 下 MUST Fail-Fast。
- MUST 文档中出现的描述性短语“显式为 none”统一解释为“显式为 null”，并以本条为准。

### 0.2 文档治理规则

| 规则 | MUST（必须） | MUST NOT（禁止） | Fail-Fast 判据 |
| --- | --- | --- | --- |
| 文档定位 | 描述层次/边界/契约对象/门控/不变量/证据链。 | 实现教程、代码细节、库 API 用法。 | 5 分钟内能回答：分几层、谁负责什么、哪些 gate 会拒绝运行。 |
| 单一真相 | 每个定义/口径/ID/不变量/门控都指向唯一锚点（0.3）。 | 多处“再定义同一概念”。 | 同一概念只有一个权威定义，其它位置只能引用。 |
| 一致性执法 | 以 0.3 锚点为唯一来源，并由第 4–7 章门控/证据链/不变量执行。 | 绕开锚点另起动作/规则/账本/统计口径。 | 发现绕行：拒绝运行/拒绝合并，并按 0.4 纳入锚点治理。 |
| 依赖方向 | 明确输入/输出与依赖；只允许向下或同层 Adapter。 | 跨层绕行与“上层改下层状态”。 | 任意模块能画依赖箭头且无反向写入。 |
| 契约优先 | 讨论实现前先落在契约对象与锚点上。 | 隐式 fallback / 硬编码绕契约。 | 任意变更可回答：改了哪个对象、ID/Hash 如何变化。 |
| Fail-Fast 门控 | 门控必须声明拒绝条件 + 必要证据字段。 | 静默 fallback 掩盖缺失/不一致。 | 触发 gate 可定位：哪个 gate、因何拒绝、证据在哪。 |
| 证据链唯一 | 统计/评估只来自 EventStream，记录 proposed→executed trace。 | 从中间态/策略输出直接派生统计。 | 任意矛盾可单手回放定位到事件与映射原因。 |
| 可复现治理 | 产物必须携带 Provenance；缺失即不可用。 | 只记录配置名/命令行不记录版本哈希。 | 同一 provenance 可跨机器重放；缺失直接拒绝加载。 |
| 复杂度预算 | 优先复用既有对象/锚点；新增对象必须 Define 并声明影响面。 | 堆砌条款导致概念爆炸。 | 可复用却新增对象：视为违规并拒绝合并。 |

### 0.2.1 防复发机制闭环（P0）

- MUST 对 0.3 表中每个权威锚点（契约对象）同时满足以下最小闭环，否则视为“不可落地/易复发”并拒绝进入主线：
  1) **可哈希语义闭包**：存在 *_id/*_hash/*_digest 定义与 canonicalization 规则，且能进入 options_hash 或 gate/cache。
  2) **至少一个可机器执法点**：对应 Gate（第 7 章）或 Ledger/Invariant（第 6 章）能在运行或 CI 中 Fail-Fast。
  3) **至少一个回归样本覆盖**：要么进入 Golden Fixtures（5.1.2），要么进入 Contract Kit 的跨语言 Test Vectors（3.4.1）；两者之一必须存在。
- MUST 当新增/修改权威锚点语义（Define/Refine）时，同步更新：闭包字段→门控/不变量→fixture/vector；否则变更视为不完整。

### 0.3 权威锚点映射

> 本表定义“单一真相”的唯一落点；文档其他位置 MUST 只引用这些锚点。

| 契约对象 / 概念 | 权威锚点（章节） | 主要责任层 | 其他章节 MUST NOT |
| --- | --- | --- | --- |
| Canonical Action | 3.1 Canonical Action | Protocol / Environment | 再定义 bet/raise/all-in 执行口径与主表示 |
| RuleSet | 3.2 RuleSet | Protocol / Environment | 在其他层解释平台规则细节 |
| Compat Triad | 3.3 Compat Triad | Protocol / Data / Runtime | 用默认值绕过 triad 校验 |
| Schema Contract + schema_hash | 3.4 Schema Contract | Protocol / Data / Runtime | 训练/推理各写一套 schema |
| Provenance Envelope | 3.5 Provenance Envelope | Protocol / Data | 只记配置名不记版本/哈希/seed |
| Hash Canonicalization | 3.5.1 Canonicalization | Protocol / Data | 各处自定义序列化/在 hash 输入中使用 float |
| Identifier Naming | 0.1.2 ID/Hash/Label | Protocol | 在 gate/cache/options_hash 中使用 *_label/_alias |
| Null Convention | 0.1.3 Null Convention | Protocol | 在 hash 输入里用字符串 "none" |
| Controlled Enums | 0.4.1 Controlled Enums | Protocol | 在其他章节重列/扩展枚举取值集合 |
| ActionKind 受控枚举（ActionKind） | 3.1 Canonical Action | Protocol / Environment | 在其他章节重列/扩展 action kind 取值集合 |
| RoundingMode 受控枚举（ActionAdapter.rounding_mode） | 3.12 ActionAdapter Contract | Protocol / Environment | 在其他章节重列/扩展 rounding_mode 取值集合 |
| FallbackPolicyMode 受控枚举（fallback_policy.mode） | 3.12.2 fallback_policy 的唯一规范 | Protocol / Environment | 在其他章节重列/扩展 fallback_policy.mode 取值集合 |
| MappingReasonCode 受控枚举（mapping_trace.reason_code） | 3.13.1 mapping_trace 最小字段集 | Protocol / Environment | 在其他章节重列/扩展 reason_code 取值集合 |
| MW RungID 受控枚举（MW rung_id） | 3.18.2 官方最小 Rung ID 集合 | Engines / Policy / Environment | 在其他章节重列/扩展 rung_id 取值集合 |
| PolicyKind 受控枚举（PolicySpec.policy_kind） | 3.19.3 PolicySpec Contract | Protocol / Runtime / Policy | 在其他章节重列/扩展 policy_kind 取值集合 |
| Street Enum (Snapshot.street / StreetDealt.street) | 3.11.1.1 Street 受控枚举 | Protocol / Environment | 在其他章节重列/扩展 street 取值 |
| Scenario Package | 3.6 Scenario Package | Protocol / Runtime | 歧义路由或静默 fallback |
| ScenarioID | 3.6.2 ScenarioID 与最小语义闭包 | Protocol / Runtime | 在其他章节自算 scenario_id 口径 |
| Scenario Family Key | 3.6.3 scenario_family_key 与 latest 语义 | Protocol / Runtime | 用“latest/alias”跨 family 漂移 |
| PathsConfig + ResolvedPaths | 3.6.1 PathsConfig + ResolvedPaths | Protocol / Runtime | 模块内自行解析外部路径/持久化绝对路径 |
| CacheKey Contract | 3.7 CacheKey Contract | Protocol / Data / Runtime | 业务层手拼字符串 key |
| Observation View | 3.8 Observation View | Protocol / Environment | 训练/推理读取不可见信息 |
| BeliefSpec | 3.8.1 BeliefSpec Contract | Protocol / Policy / Environment | 多人后验在各模块各自推导导致分叉 |
| MetricsSpec | 3.9 MetricsSpec Contract | Evaluation | 分母/单位/动作分类口径各处自定义 |
| ReportSchema + RuleConformanceReport | 3.10 ReportSchema / 3.10.1 RuleConformanceReport | Evaluation | 拼字符串输出、字段随意变更 |
| Engine Boundary + Snapshot | 3.11 Engine Boundary Contract | Environment | 在 Environment 外重算事实量 |
| ActionAdapter | 3.12 ActionAdapter Contract | Protocol / Environment | 多模块自算换算/无 trace |
| TreePathMappingSpec | 3.13 TreePathMappingSpec | Protocol / Data | 尺寸映射不可回放 |
| MW Strategy Ladder + mw_context_digest | 3.18 MW Strategy Ladder Spec | Engines / Policy / Environment | 绕开 ladder 直接执行隐式近似 |
| Proposed→Executed | 4.2 Proposed→Executed | Policy / Environment | 统计从 proposed 派生忽略 executed |
| Event Model | 5.1 Event Model | Environment | stats/arena 自建第二条事件链 |
| EventStream Artifact | 5.1.1 EventStream | Environment / Evaluation | 绕开 EventStream 的汇总/采样不留 provenance |
| Ledger Invariants | 6.1/6.1.1 Global Invariants | Environment | 模糊守恒口径/账本再定义 |
| MWAssumptionGuardSpec | 7.7 MW Assumption + Guard | Engines / Policy / Environment | HU 近似当作 MW 通用真理 |
| Stage Evidence Enums (stage_id / artifact_kind / status / degraded_reason) | 3.19.1.1 Stage Evidence 受控枚举 | Protocol / Runtime | 在其他章节重列/扩展这些受控枚举取值集合 |
| PolicySpec Contract | 3.19.3 PolicySpec Contract | Protocol / Runtime / Policy | 在脚本/模块里用字符串解释 policy 含义 |
| ProfileSpec Contract | 3.20 ProfileSpec Contract | Protocol / Runtime | 把实现细节暴露成自由 CLI 参数 |
| Pipeline CLI Contract | 3.21 Pipeline CLI Contract | Protocol / CLI | 发明新顶层命令/绕开 RunSpec 与门控 |
| Contract Kit（schema‑first 代码生成） | 3.4.1 Contract Kit | Protocol / Data / Runtime | 各语言手写 schema/序列化/hasher |
| Golden Fixtures 回归门禁 | 5.1.2 Golden Fixtures | Environment / Evaluation | 仅靠日志/经验验证一致性 |
| ForcedBets kind 受控枚举（ForcedBets.kind） | 5.1 Event Model | Environment | 在其他章节重列/扩展 forced bets kind 取值集合 |
| ActionSource 受控枚举（ActionChosen.action_source_id） | 5.1 Event Model | Environment | 在其他章节重列/扩展 action_source_id 取值集合 |

### 0.4 文档变更流程

- MUST 任何修改先归类为以下四类之一（只选其一）：Define / Refine / Enforce / Restructure。
  - Define：新增契约对象或新增权威锚点（并更新 0.3）。
  - Refine：澄清/扩展既有对象，不改变其唯一真相落点。
  - Enforce：新增/加强门控或不变量（只引用既有对象与锚点）。
  - Restructure：仅调整组织与表述，不改变 Normative 语义。
- MUST 变更指定落点（0.3）；MUST 声明影响（schema_hash / scenario_id / cache_key / options_hash / provenance 字段变化）；MUST 给出验证（回放 + 门控/不变量）。
- MUST Refine/Enforce MUST NOT 引入新对象名称或新口径。
- MUST Define 说明不可复用原因 + 影响面 + 收敛声明（防止同类对象继续膨胀）。

### 0.4.1 受控枚举治理（Controlled Enums）

- MUST 任何受控枚举取值集合的新增视为 Define，并同步更新 0.3 与对应权威锚点。
- MUST 任一受控枚举的“取值集合”只允许在其权威锚点列出一次；其他章节 MUST NOT 重列取值集合或以示例形式暗示新增取值。
- MUST 若某受控枚举的取值会影响决策/执行/统计语义，则其选择必须进入对应 *_id 的内容闭包并最终进入 options_hash（3.19.2）；否则视为架构违规并 Fail-Fast。

### 0.5 决策记录（DR）

- SHOULD 涉及 Normative 区的变更追加一条 DR，至少包含：DR-ID、摘要、影响面、迁移策略、验证方式。

**DR 模板（Informative）**

- DR-ID：DR-YYYYMMDD-XX
- 变更类型：Define | Refine | Enforce | Restructure
- 影响面（必须可枚举）：
  - 可能变化的：schema_hash / scenario_id / cache_key / options_hash / provenance 字段（列出具体字段名）
  - 不应变化的：列出“必须保持不变”的 ID/Hash（若变化则属于 bug）
- 迁移策略：向前/向后兼容、fixture 更新策略、灰度/回滚点
- 验证：
  - 门控/不变量：触发点 + Fail-Fast 证据字段
  - 回归：Golden Fixtures 或 Contract Kit Test Vectors（二选一或都写）
  - 回放定位：给出最小可复现入口（event_stream_ref + hand_selector）
- 结论：接受/拒绝 + 原因（可审计短语）

## 1. 目标与非目标

### 1.1 目标

- MUST 单一真相：动作/规则/账本/统计口径只有一套权威来源。
- MUST 可回放证据链：可定位到“哪手牌、哪一步、哪次映射”。
- MUST Fail‑Fast：规则/资产/口径/不变量不满足即拒绝运行。
- MUST 可复现：版本锁定 + seed/options 记录可回归。
- MUST 训练/推理同构：schema\_hash 一致才允许训练/加载/编译。
- MUST 防信息泄漏：只使用线上可见信息。
- MUST 多人近似显式化：适用范围与护栏可验证、可审计。
- MUST 对手可归因且可复现：对手作为 PlayerAgent，来源可追溯、生态可冻结、需要时可校准。

### 1.2 非目标

- MUST NOT 描述具体实现代码与性能调参细节。
- MUST NOT 在本文档展开 solver 算法细节比较（只给边界与契约期望）。

---

## 2. 系统分层与依赖方向

系统分为六层；依赖只允许向下或同层 Adapter；禁止跨层绕行。

1. **Protocol**：全系统契约与口径定义（第 3 章）。
2. **Environment**：唯一执行 + 唯一账本 + 事件流 + 不变量。
3. **Engines**：以 **HU solver** 与 **postflop-solver** 作为翻后核心引擎（HU/MW 求解或近似推断），输出建议而非执行。
4. **Policy**：组合查表/模型/引擎生成 ProposedAction。
5. **Data**：翻前表/翻后库/模型/缓存等可复现产物。
6. **Evaluation**：只读事件流生成统计/报表/回放样本。

硬约束：

- MUST 只有 Environment 可以执行动作并修改账本。
- MUST 只有 Protocol 可以定义口径与契约对象。
- MUST 上层只消费 DecisionPoint Snapshot（3.11）与 Event Stream（5.1），不得读取/推导规则引擎内部事实量。
- MUST 规则引擎（如 pokerkit）只允许存在于 Environment（3.11）。
- MUST Evaluation 只读事件流，禁止读策略中间态。

### 2.1 单向数据流

- Environment MUST 产出 Snapshot 与 Event Stream（事实单位 chips(int)）。
- Engines/Policy MUST 基于 Snapshot 生成 ProposedAction；Environment MUST 合法化为 ExecutedAction，并把 proposed/executed/trace 写入事件流。
- Data/Cache/Model/HotCache MUST 由事件流派生并携带 Provenance（3.5）。
- Evaluation MUST 仅基于事件流 + MetricsSpec（3.9）+ ReportSchema（3.10）输出结果。

### 2.2 翻后核心引擎（HU solver / postflop-solver）

实现约定（仅约束接口与可复现闭包，不规定具体算法）：
- SHOULD **postflop-solver（Rust）** 通过 **PyO3/maturin** 方式产出可安装的 Python 扩展模块（例如 wheel 或本地 editable 安装）；若采用 CLI 子进程方式，必须在 ProfileSpec/PolicySpec 的语义闭包中显式声明 binding_kind，并确保其版本/commit 进入 solver_build_id（3.5）。
- MUST 构建/安装所使用的 postflop-solver 源码版本（commit）与构建指纹必须进入 solver_build_id（3.5），并由 Provenance Gate 执法（7.3）；不得仅依赖“某个本机目录里是什么”。
- MUST postflop-solver 源码位置的解析必须通过 PathsConfig 的 `postflop_solver_src_root`（3.6.1）；不得在 Normative 区写死宿主机绝对路径。

- MUST 翻后求解/检索/热启动相关能力以 **HU solver** 与 **postflop-solver** 作为 Engines 层的核心引擎实现；它们只产生 **建议（ProposedAction/策略摘要）**，不得直接执行动作或修改账本（执行仍由 Environment 唯一完成；见 3.11/4.2）。
- MUST 两个 solver 只允许读取 Snapshot（3.11）与 ObservationView（3.8）以及 Scenario/Policy 明确声明的资产引用（3.6/3.19.3）；不得读取 Environment 内部 state 或不可见信息（7.6）。
- MUST 任一 solver 产物（离线库/热启动权重/求解缓存等）必须以 `artifact_ref + digest + provenance_ref` 被引用：要么进入 ScenarioPackage.postflop_ref（3.6），要么进入 PolicySpec.policy_deps（3.19.3），并最终进入 options_hash（3.19.2/7.3）。

---

## 3. Protocol 权威定义区

> 本章为权威定义区；其他章节 MUST 只引用，不得再定义。

### 3.1 Canonical Action

Anchor ID: Protocol.CanonicalAction

- MUST ActionKind 为受控枚举；唯一允许取值：FOLD | CHECK | CALL | BET | RAISE。新增取值视为 Define（0.4）；strict_mode 下遇到未登记取值即 Fail-Fast。

- MUST Canonical Action 的执行主表示为：
  - kind: ActionKind
  - target_total_commit_chips: int

- MUST 执行口径统一为“执行后该玩家本手牌总投入应变成多少”（target_total_commit_chips，单位 chips(int)）。
- MUST 所有**金额**事实单位为 chips(int)。
- MUST bb / pot_frac 等仅允许作为输入或展示语义，MUST NOT 作为内部执行口径或进入 *_hash 输入。
- MUST 进入 *_hash 的**比例/费率**必须使用受控整数编码并显式声明单位（例如 rake 的 pct_ppm:int），MUST NOT 使用 float（3.5.1）。

- MUST 对 FOLD/CHECK/CALL 的 target_total_commit_chips 采用唯一确定规则（用于消除实现分叉）：
  - FOLD：target_total_commit_chips = actor_commit_chips（不再追加投入）。
  - CHECK：target_total_commit_chips = actor_commit_chips（且 to_call_chips MUST == 0）。
  - CALL：target_total_commit_chips = actor_commit_chips + to_call_chips（且 to_call_chips MUST > 0）。

- MUST 对 BET/RAISE 的唯一判定规则（仅依赖 Snapshot 事实量，避免各处自算）：
  - 若 to_call_chips == 0 且 target_total_commit_chips > actor_commit_chips，则 kind MUST 为 BET。
  - 若 to_call_chips > 0 且 target_total_commit_chips > actor_commit_chips + to_call_chips，则 kind MUST 为 RAISE。

- MUST ALLIN 不是 ActionKind。
  - MUST is_allin 作为派生属性（derived tag）存在：
    - is_allin := (target_total_commit_chips == actor_commit_chips + actor_stack_chips) OR (max_raise_to_chips != null AND target_total_commit_chips == max_raise_to_chips)。
  - MUST is_allin 的派生只能由 Environment 基于 DecisionPoint Snapshot + ExecutedAction 计算，并作为可回放字段进入事件流/报告；Metrics/Report MUST NOT 各自推导口径（见 3.9.1）。

- MUST 任意非 chips(int) 的输入必须经 ActionAdapter（3.12）转换为 Canonical Action；转换采用确定的 rounding_mode，并将 rounding_mode 与误差/替换原因写入 mapping_trace 与 provenance/options_hash（3.5/3.19.2）。

#### 3.1.1 Canonical Action 的规范化与合法化（Normative）

> 目标：彻底消除“上层各算各的 kind/all-in/合法性”导致的口径漂移。

- MUST Environment 将 `target_total_commit_chips` 视为 Canonical Action 的主语义；`kind` 视为冗余字段（便于人类阅读/调试），但其语义必须可由 Snapshot 唯一派生（3.1）。

- MUST Environment 在接收任何 ProposedAction / 外部动作表示时，按以下顺序完成**规范化（canonicalize）→ 合法化（legalize）**：
  1. **规范化（Canonicalize）**：
     - 对 FOLD/CHECK/CALL：MUST 按 3.1 的唯一规则重建 `target_total_commit_chips`；若输入与重建值不一致：
       - strict_mode 下 MUST Fail-Fast；
       - 非 strict_mode 下 MAY 覆写为重建值，但必须记录 mapping_trace（按 3.13.1；动作前后由 proposed_action/executed_action 提供），并标记 degraded=true（6.2/3.19.1）。
     - 对 BET/RAISE：MUST 仅基于 Snapshot.{to_call_chips, actor_commit_chips} 与 `target_total_commit_chips` 按 3.1 的唯一判定规则派生 `derived_kind`；若输入 kind 与 derived_kind 不一致：
       - strict_mode 下 MUST Fail-Fast；
       - 非 strict_mode 下 MAY 覆写为 derived_kind，并记录 mapping_trace（按 3.13.1；动作前后由 proposed_action/executed_action 提供），标记 degraded=true。
  2. **合法化（Legalize）**：
     - MUST “允许执行”的唯一集合为：Environment 在该 DecisionPoint 根据 triad.action_bins_id + Snapshot + (action_adapter_id,mapping_spec_id) 计算得到的离散候选列表（3.11.2）；Snapshot.legal_actions_digest 仅作为该列表的不可逆指纹用于一致性对比/缓存键。
     - MUST legal_actions_digest 单独出现时 MUST NOT 被解释为可逆编码或“可直接还原候选集合”。
     - 若规范化后的 Canonical Action 不在候选集合中：
       - strict_mode 下 MUST Fail-Fast，并输出最小证据闭包（6.2）；
       - 非 strict_mode 下 MAY 仅在 ActionAdapter/MappingSpec 明确声明了可用的 fallback_policy 时进行替换（例如 nearest-bin snap / clamp），并且必须：
         - 记录 proposed→executed 的差异；
         - 记录完整 mapping_trace（含输入、替换后动作、fallback_policy、原因）；
         - 将 degraded=true 与 degraded_reason=illegal_action 或 mapping_lossy 体现在 Stage Evidence（3.19.1）与事件流（5.1）。

- MUST 任何“合法化替换”的语义闭包（允许哪些 fallback_policy、如何选择替换目标、如何处理边界）必须归入 ActionAdapter（3.12）与/或 TreePathMappingSpec（3.13）的可哈希内容闭包；否则视为口径漂移并 Fail-Fast（3.12/3.13/3.19.2）。

### 3.2 RuleSet

Anchor ID: Protocol.RuleSet

- MUST RuleSet 将平台差异封装为单一契约对象：它必须完整覆盖会影响“动作合法性/最小加注/是否重新开放行动/抽水/结算/四舍五入/无翻牌不抽水”等语义的所有规则维度。
- MUST RuleSet 只允许由 Environment 解释并成为唯一事实源；其他层 MUST NOT 再解释平台规则细节（见 3.11）。
- MUST rules.validate()：缺字段/非法组合/歧义组合必须 Fail-Fast。

#### 3.2.1 RuleSet 最小字段闭包（必须可哈希）

- MUST RuleSet 的字段闭包必须可被 3.5.1 canonicalization 稳定序列化；任何缺失/不适用一律用 JSON null 表达（0.1.3）。
- MUST 下列字段为 RuleSet 的最小闭包；实现可扩展，但扩展字段若影响动作合法性/结算语义/抽水语义，则必须进入 ruleset_id 的 hash 输入闭包（3.2.2）。

- MUST RuleSet 至少包含以下字段（仅示意字段形状；语义以本节为准）：
  - game_kind：例如 "NLHE"
  - blinds：{sb_chips:int, bb_chips:int}
  - ante：null 或 {kind:"uniform", ante_chips:int} 或 {kind:"by_seat", by_seat_ante_chips:object}
  - straddle：null 或 {kind:"button"|"utg"|"by_seat"|"custom", amount_chips:int, by_seat_amount_chips:object|null}
  - rake：null 或 {pct_ppm:int, cap_chips:int|null, rounding_mode:rounding_mode（受控枚举，见 3.12）, no_flop_no_drop:bool}
    - no_flop_no_drop 语义：若为 true 且本手牌未发出 flop（EventStream 中不存在 StreetDealt{street:"FLOP"}，见 5.1），则 total_rake_chips MUST == 0，且事件流中 MUST NOT 出现任何 `PotUpdate.rake_chips_delta != 0`（或等价字段）。
    - rake 计算口径：
      - rake_base_pot_chips := HandEnd.rake_base_pot_chips（Environment 记录的、用于本手 rake 计算的 pot 基数）。
      - raw_rake := rake_base_pot_chips * pct_ppm / 1_000_000。
      - 按 rounding_mode 将 raw_rake 取整为 int(chips)，再与 cap_chips 取 min（cap_chips 为 null 则不封顶）。
      - 最终 total_rake_chips 为上述结果（并受 no_flop_no_drop 约束）。
  - min_raise_rule：{basis:"last_raise_increment", reopen_on_short_allin:bool}

说明（必须写死口径，避免漂移）：

- MUST ante/straddle/rake 的“未启用”语义必须用字段为 null 表达；MUST NOT 使用字符串 "none" 或缺字段表达（0.1.3）。

- MUST min_raise_rule.basis 当前唯一允许为 "last_raise_increment"：
  - min-raise 的最小增量以“上一手牌内最后一次完整加注的增量”为准（而非 to_call）。
- MUST min_raise_rule.reopen_on_short_allin 明确 all-in 不足最小加注时是否重新开放行动：
  - 当 reopen_on_short_allin=false 时：不足最小加注增量的 all-in 不重新开放后续玩家的加注权。

#### 3.2.2 ruleset_id / ruleset_hash 的规范化

- MUST ruleset_id = hash(canonicalized RuleSet)，遵循 3.5.1（键排序/UTF-8/无 float/bb/pot_frac）。
- MUST ruleset_hash 若存在，必须与 ruleset_id 相等（别名而非第二口径）；strict_mode 下若不相等即 Fail-Fast。
- MUST RuleSet 的 rounding_mode（尤其 rake 四舍五入/截断规则）必须进入 ruleset_id 输入闭包；否则视为平台口径漂移并 Fail-Fast。

#### 3.2.3 NLHE 最小加注与短 all-in reopen 的确定算法（Normative）

- MUST 本节仅适用于 game_kind=="NLHE" 且 min_raise_rule.basis=="last_raise_increment"（3.2.1）；其他 game_kind 或其他 basis 均属于 Define（0.4）。

定义（均以“总投入 target_total_commit_chips”口径表达，与 3.1 一致）：

- current_bet_to_total_chips := actor_commit_chips + to_call_chips（等于当前轮次内的最高总投入）。
- raise_increment_chips := target_total_commit_chips - current_bet_to_total_chips（对 BET/RAISE 的增量；执行时 MUST > 0）。
- street_opening_increment_chips：
  - preflop：取本手牌 preflop 开始后、任何自愿动作发生前的 current_bet_to_total_chips（由 blinds/straddle 决定；通常为 bb 或 straddle amount）。
  - flop/turn/river：= blinds.bb_chips。
- last_full_raise_increment_chips：本 street 内最近一次“完整加注(full raise)”的增量；若本 street 尚无完整加注，则 = street_opening_increment_chips。

最小下注/加注（写死口径，避免漂移）：

- 若 to_call_chips==0：最小 BET 的 target_total_commit_chips = actor_commit_chips + blinds.bb_chips。
- 若 to_call_chips>0：最小 RAISE 的 target_total_commit_chips = current_bet_to_total_chips + last_full_raise_increment_chips。

完整加注(full raise) 判定：

- 当 raise_increment_chips >= last_full_raise_increment_chips 时，该次 raise 为 full raise；Environment MUST 将 last_full_raise_increment_chips 更新为 raise_increment_chips，并对后续玩家开放 re-raise 权（体现在其 legal_actions_digest 中包含 RAISE）。

短 all-in raise 与 reopen（消除平台口径分叉）：

- 当 raise_increment_chips < last_full_raise_increment_chips 且 is_allin==true（3.1）时，称为 short all-in raise。
- 若 min_raise_rule.reopen_on_short_allin==false：该 short all-in raise MUST NOT 重新开放“已在本 street 自上一次 full raise 以来轮到过行动的玩家”的加注权；Environment MUST 在这些玩家的后续 DecisionPoint 中移除 RAISE（legal_actions_digest 不得包含任何 RAISE）。
- 若 min_raise_rule.reopen_on_short_allin==true：该 short all-in raise MUST 视为 full raise（更新 last_full_raise_increment_chips 并 reopen）。

- MUST Environment 的唯一职责是把上述算法结果固化为 Snapshot 的 {to_call_chips,min_raise_to_chips,max_raise_to_chips,legal_actions_digest} 与 EventStream，可回放（3.11/5.1）；Metrics/Report/CLI MUST NOT 自算。

#### 3.2.4 RuleSet 源文件/注册与可复现约束（Normative）

> 目的：把“internal fixtures 绑定哪个规则平台 / ruleset_version 如何定义”收敛为**唯一契约**，避免用字符串版本号制造第二真相。

- MUST RuleSet 的唯一权威语义为 3.2；任何“文件路径/别名/版本名（例如 internal_ruleset_v1）”仅作为载入入口与展示信息，不得成为第二真相源（见 0.1.2）。
- MUST `ruleset_id = hash(canonicalized RuleSet)`（3.2.2）为**唯一规范性标识**；任何人工命名的 `ruleset_label/ruleset_alias`：
  - MUST NOT 进入 `ruleset_id`/`options_hash`/cache key/gates；
  - MUST 在进入门控前被确定性解析为 `ruleset_id`（解析过程仅允许写入 resolution_trace）。
- MUST 仓库内 SHOULD 提供一个规范来源目录用于 RuleSet 源文件（推荐：`specs/rulesets/`）：
  - 每个源文件载入后必须通过 Contract Kit validator 校验（3.4.1）；
  - MUST 对载入内容执行 canonicalization 并计算 `ruleset_id`；若文件内显式携带 `ruleset_id` 字段，则 MUST 与计算值一致，否则 strict_mode 下 MUST Fail-Fast。
- MUST Golden Fixtures（5.1.2）与 Scenario Package（3.6）对“平台规则基准”的绑定，必须使用 `ruleset_id`；若 fixture/scene 仅给出 label/alias 而无法解析到唯一 `ruleset_id`，则 strict_mode 下 MUST Fail-Fast。

### 3.3 Compat Triad

Anchor ID: Protocol.CompatTriad

- MUST 定义 triad：`action_bins_id / obs_schema_id / rake_id`。
- MUST triad 作为 Data/Model/Cache 的最小兼容门控：任一组件不一致即拒绝训练/加载/编译/读缓存（见 7.1/7.5）。

rake_id 的唯一语义（防止“数据抽象抽水”与“执行抽水”两套口径）：

- MUST `rake_id` 表示 **RuleSet 抽水语义闭包** 的内容哈希；其输入闭包来自 RuleSet（3.2），并遵循 3.5.1 canonicalization。
- MUST 令 `ruleset_rake_closure := canonicalized {rake}`，其中 `rake` 字段取自 RuleSet（3.2.1）：
  - 未启用抽水时 `rake` MUST 为 `null`（见 0.1.3）；
  - 启用抽水时 `rake` MUST 为 `{pct_ppm, cap_chips|null, rounding_mode, no_flop_no_drop}`。
- MUST 定义 `ruleset_rake_id := hash(ruleset_rake_closure)`（遵循 3.5.1）。
- MUST `triad.rake_id == ruleset_rake_id`；若不一致，Triad Gate（7.1）必须 Fail-Fast。

约束：

- MUST NOT 在任何模块/脚本中引入第二套“抽水模型 ID”或用字符串 label/alias 代替 `rake_id`（见 0.1.2）。
- SHOULD 任何影响抽水语义的变更必须体现在 RuleSet（3.2）并导致 `ruleset_rake_id` 变化，从而通过 triad 门控强制全链路一致。

### 3.4 Schema Contract

Anchor ID: Protocol.SchemaContract

- MUST 定义训练/推理同构契约并计算 schema\_hash。
- MUST 覆盖：ActionSpace、LegalMaskRule、FeatureEncoderSpec、PostProcessSpec。
- MUST schema\_hash 不一致则拒绝训练/加载/编译。

#### 3.4.1 Contract Kit（Schema‑first + 代码生成的唯一实现）（Normative）

> 目标：终结多语言/多模块手写结构与序列化导致的 schema/hash 漂移。
>
> 术语：本节中的“目标语言/各语言”仅指 Contract Kit 需要生成绑定的语言集合；当前覆盖 Python / Rust / TypeScript，未来新增语言同样适用。

- MUST 所有 Protocol schema（契约对象/事件模型/报告）由**单一 schema 源**定义，并由 Contract Kit 生成跨语言结构体/类型；禁止手写重复结构。
- MUST schema 源必须同时定义：字段结构 + null 约定（0.1.3）+ 受控枚举集合（0.4.1）+ canonicalization 规则（3.5.1）+ hash 输入闭包；这些视为不可分割整体，禁止在各语言/各模块分别实现。
- MUST Contract Kit 同时生成：
  - validator（严格校验 null/受控枚举/字段缺失）；
  - canonicalizer（3.5.1 的规范序列化实现）；
  - hasher（所有 *_hash/*_digest/*_id 的统一计算器）。
- MUST 运行时与工具链（doctor/replay/stats/训练数据生成）对 schema 校验、canonicalization 与 hash 计算必须使用 Contract Kit 的实现；禁止各模块各算各的。

##### 3.4.1.1 跨语言实现规则（Normative）

> 目的：避免“各目标语言 各自实现一套”导致的口径漂移与重复工作。

- MUST “三语言支持”只意味着：同一份 schema 源通过 Contract Kit **生成**三语言的类型/校验/序列化/哈希产物，并在各自运行时被调用；MUST NOT 理解为三套独立规范或三套独立实现。
- MUST canonicalizer/hasher 的权威逻辑只能存在于 Contract Kit（生成器 + 其冻结的 Test Vectors）；各语言运行时只允许调用生成产物或极薄的 glue code（I/O/绑定），不得复制实现逻辑。
- MUST 任何在某一语言侧新增/修改序列化、哈希、字段默认、枚举取值集合、排序规则等“会影响 *_hash/*_digest/*_id 的语义闭包”的代码，必须先以 schema 变更落入 Contract Kit（并走 0.4 的 Define/Refine），再 regenerate；否则视为绕开单一真相并 Fail-Fast。
- SHOULD 工程上把“生成产物之外的手写实现”变成不可见/不可达（例如不导出内部 API、denylist 静态检查）；发现重复实现即拒绝合并。

CI/门禁（把“正确性”写成工程制度）：

- MUST CI 门禁（生成一致性）：任何 schema 变更必须执行 regenerate；若生成结果与仓库不一致（re-generate 后 diff 非空）则拒绝合并。
- MUST CI 门禁（跨语言一致性）：仓库必须维护一组冻结的 **Schema/Hash Test Vectors**（不可变输入集），覆盖至少：
  - null 约定（0.1.3）与受控枚举（0.4.1）的边界值；
  - Canonicalization（3.5.1）的对象键排序/数组顺序/字符串转义；
  - DigestObject（3.5.1.2）与 SeatMap（3.5.1.1）的编码规则；
  - EventStream NDJSON 行格式与行级 canonicalization（5.1.1）。
- MUST 上述 Test Vectors 在 CI 中必须由 各目标语言的**生成产物**分别执行并产出期望输出（canonicalized bytes/hash/digest）（强调：不是三套手写实现）；任一语言不一致即视为口径漂移并拒绝合并。

演进规则（防止“兼容性”成为漂移借口）：

- MUST schema 演进规则：任何 breaking change 必须显式 bump 对应 *_schema_id / event_model_id / report_schema_id，并提供迁移（或更新 fixtures 门禁，见 5.1.2）；不得静默变更字段语义或删改受控枚举取值集合。
- MUST 对 non-breaking change 也必须写死兼容约束：
  - 新增字段若不适用必须默认为 null（0.1.3），且不得改变既有字段的 hash 输入语义；
  - 任何会影响 gate/cache/options_hash/统计口径的变化，一律视为 breaking（必须 bump 对应 *_id 并触发门禁更新）。

### 3.5 Provenance Envelope

Anchor ID: Protocol.ProvenanceEnvelope

- MUST 规定产物出生证明：engine/solver 版本、环境版本、ruleset\_id、triad、schema\_hash、options\_hash（见 3.19）、seed。
- MUST 同时记录并锁定：pokerkit\_version、engine\_build\_id、solver\_build\_id（或 solver\_commit）、python\_version、runtime\_env\_id（如 OS/arch），并将其纳入 provenance 与 options\_hash（3.19）。
- MUST `solver_build_id` 的语义闭包必须覆盖 **HU solver** 与 **postflop-solver** 两个核心求解器的版本/commit/编译指纹；任一变化都必须导致 `solver_build_id` 变化（否则视为 provenance 不完整并在 Provenance Gate（7.3）下拒绝加载）。

#### 3.5.1 Hash 输入的规范序列化（Canonicalization）

- MUST 所有 \*\_hash / \*\_digest / \*\_id 的输入采用同一套规范序列化：JSON 对象键排序（按 key 的 Unicode code point 字典序升序）；数组保持顺序；UTF‑8；不得依赖空白/缩进。
- MUST 例外：任何 SeatMap（3.5.1.1）对象在参与 *_hash/*_digest 时，必须按 seat_id 数值升序排序其条目（见 3.5.1.1）。

- MUST 执行口径相关数值字段一律为 int(chips)；hash 输入中 MUST NOT 出现 bb / pot\_frac / float。

- MUST 进入 *_hash 的比例/费率只允许使用受控整数编码并显式单位（例如 pct\_ppm:int）；MUST NOT 使用 float（与 3.1 一致）。

- MUST 禁止 NaN/Inf；任何来自浮点的输入必须先经 ActionAdapter（3.12）按 rounding\_mode 落到 int(chips)。

- MUST hash 输入显式包含 schema/version 标识（如 event\_model\_id / report\_schema\_id / obs\_schema\_id），禁止隐式升级。

- MUST provenance 额外携带 **rng\_lineage\_id** 与 **seed\_derivation\_digest**（全局 RNG 依赖树指纹）；任何使用随机性的模块 MUST 能被该 lineage 回放与比对。

- MUST 若使用动作映射/树路径映射，则 provenance MUST 额外携带 action\_adapter\_id / mapping\_spec\_id（3.12/3.13）。

- MUST 若场景启用 MW（Snapshot.players_alive\_count>=3 的路由可能发生），则 provenance MUST 携带 mw\_ladder\_id（3.18）。

- MUST 缺失 provenance 的产物不可用。

#### 3.5.1.1 SeatMap（*_by_seat*）统一约定（Normative）

> 目标：消除“seat→value 映射”在多语言/多模块中的编码、排序、稀疏语义不一致导致的 hash 漂移与统计口径分叉。

- MUST 任一表示“按 seat 汇总/分配”的字段采用 SeatMap 约定；字段名 MUST 包含 `_by_seat` 或 `by_seat_`。
- MUST SeatMap 在结构化 payload 中用 JSON object 表达：`{ "<seat_id>": <value>, ... }`。
  - MUST key 为 seat id 的十进制字符串：`"0"` 或不带前导 0 的正整数；strict_mode 下若出现前导 0（如 `"01"`）、非数字 key 或负数 key，MUST Fail-Fast。
  - MUST value 为 JSON 可表达的标量或其递归组合；进入任何 *_hash/*_digest 输入时，MUST NOT 为 float/NaN/Inf（与 3.5.1 一致）。
- MUST SeatMap 的“稀疏/稠密”语义必须被字段权威锚点写死，且 strict_mode 下强制检查：
  - **SparseSeatMap（稀疏）**：仅记录 value != 0（或显式相关）的 seat；缺失 key 表示 0。strict_mode 下 MUST NOT 包含 0 值条目；空对象 MUST Fail-Fast（用 null 或缺失该字段/事件表达“不适用/未启用”，见 0.1.3）。
  - **DenseSeatMap（稠密）**：必须覆盖 context 中声明的 seat 域（默认使用 HandStart.seats_in_hand）；strict_mode 下缺失任一 seat 或出现域外 seat MUST Fail-Fast；0 值允许且语义显式。
- MUST 本文档内已定义字段的 SeatMap 模式为：
  - SparseSeatMap：ForcedBets.by_seat_amount_chips；RuleSet.ante.kind=="by_seat" 的 by_seat_ante_chips；RuleSet.straddle.kind=="by_seat" 的 by_seat_amount_chips；HandEnd.forced_bets_total_by_seat（若输出）。
  - DenseSeatMap：HandEnd.initial_stacks_by_seat（value>=0）；HandEnd.final_stacks_by_seat（value>=0）；HandEnd.stack_deltas_by_seat（value 允许负数，且 MUST == final - initial）。
- MUST 任一 SeatMap 参与 *_hash/*_digest 计算时，其条目排序为**按 seat_id 数值升序**（将 key 解析为 int 后排序）；该排序为 3.5.1 的唯一例外。
- MUST strict_mode 下若任一 key 无法解析为非负 int（或出现前导 0 等非法 seat key），MUST Fail-Fast。

#### 3.5.1.2 标量与摘要对象的统一编码（Normative）

> 目标：把跨语言最容易漂移的“整数/字符串/摘要对象”口径钉死，避免同一内容在不同实现下序列化不同导致 hash/digest 漂移。

- MUST 所有 int 字段采用十进制编码；除数值 0 外 MUST NOT 有前导 0；负数仅允许一个前导负号（例如 -12）。
- MUST 所有以 `*_id / *_hash / *_digest` 参与门控/缓存/路由的字段，在结构化 payload 中必须是字符串或对象（不得以 number 直接承载二进制/字节序列），并遵守本节与 3.5.1。
- MUST seat_id / decision_id / hand_seq 等“计数/索引/标识号”在结构化对象中一律为 int；若需要作为 JSON object key（例如 SeatMap），则按 3.5.1.1 的十进制字符串规则表达。

摘要对象（DigestObject）统一约定：

- MUST 任一摘要字段采用对象形态：`{alg:"sha256", hex:"<lowercase-hex>"}`。
- MUST `alg` 仅允许 "sha256"（除非对应权威锚点显式声明允许其他算法）；strict_mode 下出现其他 alg MUST Fail-Fast。
- MUST `hex` 必须为小写十六进制字符串；长度必须与算法匹配（sha256 为 64）。strict_mode 下不匹配 MUST Fail-Fast。

字符串与转义约定：

- MUST 所有字符串按 UTF-8 编码；MUST NOT 进行 Unicode 归一化/大小写折叠/去空白等隐式处理；hash 输入以字节序列为准（3.5.1）。
- MUST 任何出现在字符串值中的换行字符必须以 JSON 转义 `\n` 表达；不得在字符串值中直接嵌入平台相关的行结束符（例如 `\r\n`）。

#### 3.5.2 Reproducibility Tier（确定性层级）

- MUST 明确一次运行所承诺的可复现层级，并记录在 Run Manifest 与报告头（引用 3.19/3.10）：
  - Tier‑A：事件流可复现（同 seed + options\_hash 生成同一 event\_stream\_digest）。
  - Tier‑B：统计可复现（指标一致；事件顺序/分片允许不同，但必须可回放定位）。
- MUST strict\_mode 默认要求至少 Tier‑B；Tier‑A 仅在回归/对比场景启用，但一旦声明为 Tier‑A 则必须满足。

### 3.6 Scenario Package

Anchor ID: Protocol.ScenarioPackage

- MUST 定义 ScenarioID（关键规则维度 + triad/schema 派生）。
- MUST Scenario Package 是可回放的自描述对象：至少引用 ruleset\_id（3.2）、triad（3.3）、schema\_hash（3.4）、abstraction\_ref（action\_bins/bins 版本）、preflop\_ref、postflop\_ref（若启用）、opponent\_suite\_id（3.16）与 population\_id（3.15）。
- MUST 缺失关键引用/出现歧义时 Fail‑Fast；不得用默认值静默补齐改变 scenario\_id。

**主键族与 “latest” 语义（防止用错场景）**

- MUST 定义并遵守 **scenario\_family\_key = hash(canonicalized {scenario\_id, ruleset\_id, abstraction\_hash})**，并遵循 3.5.1；任何 “latest” 指针只能在同一 family 内移动。
- MUST abstraction\_hash = hash(canonicalized {action\_bins\_id, action\_adapter\_id, mapping\_spec\_id})，遵循 3.5.1；任何会改变动作空间/映射语义的规则（含 size\_jitter/阈值/回退）必须被纳入 action\_adapter\_id 或 mapping\_spec\_id 的内容闭包，否则视为口径漂移并 Fail‑Fast。
- MUST NOT 允许跨 family 的 latest/别名漂移；一旦发生即视为歧义路由并 Fail‑Fast。

**路径引用（防止跨机读错库）**

- MUST 场景包内所有 artifact\_ref 仅允许使用**相对引用**（相对场景包根）；MUST NOT 持久化绝对宿主路径。
- MUST 运行时仅由 PathsConfig 解析并生成 ResolvedPaths（见 3.6.1），并将 resolved\_paths\_digest 写入 Run Manifest；缺失即 Fail‑Fast。
- MUST 若场景允许 MW 决策（Snapshot.players_alive_count>=3 且不强制 HU-only），则 Scenario Package MUST 绑定 mw\_ladder\_id（3.18）；缺失即 Fail‑Fast。
- SHOULD 若 suite 需要校准（3.17），则必须绑定唯一 opponent\_artifact\_id（或 params\_hash）；缺失视为不可运行。

#### 3.6.1 PathsConfig + ResolvedPaths

**第三方源码/工具依赖的路径注入（含 postflop-solver）**

- MUST 任何第三方源码或可执行工具（例如 **postflop-solver**）不得在 Normative 区以“某台机器的绝对路径”被引用（例如 `/Users/...`）；此类路径只允许通过 PathsConfig 注入并在 RunManifest.resolution_trace 记录（3.19.1），用于开发机/CI 的解析审计。
- MUST 为 postflop-solver 预留一个稳定的逻辑键：`postflop_solver_src_root`。
  - 默认值 SHOULD 为仓库内相对路径（例如 `./third_party/postflop-solver`）或等价的受控引用（例如 `path:third_party/postflop-solver`）。
  - 开发机 MAY 覆盖为宿主机绝对路径（例如本机检出位置），但该绝对路径 MUST NOT 进入 options_hash（3.19.2）。
- MUST `resolved_paths_digest` 的 hash 输入闭包必须 **machine-independent**：仅基于 PathsConfig 的逻辑键与其规范化的相对/受控引用（不得包含宿主机绝对根、用户名、挂载点）；宿主机绝对路径仅作为 resolution_trace 的审计字段存在。
- MUST 若启用 postflop-solver 的 Python 绑定/可执行产物：其“可运行制品”必须以 `artifact_ref + digest` 被引用并进入 options_hash（3.19.2），不得仅依赖源码目录本身的可变状态（防止同路径不同 commit 的漂移）。


Anchor ID: Protocol.PathsConfig

- MUST PathsConfig 是“外部路径解析输入”的唯一契约对象；其语义闭包只描述“如何把场景包内的相对引用解析为宿主机绝对路径”，不得引入任何会改变场景语义的隐式默认值（见 0.1.2/7.4）。
- MUST Scenario Package（3.6）内所有 artifact_ref 仅允许相对引用；PathsConfig MUST 提供必要的根目录与解析规则，使解析结果在 strict_mode 下为确定函数。
- MUST ResolvedPaths := resolve(PathsConfig, ScenarioPackage) 的输出为绝对路径清单；其内容必须可 canonicalize 并计算 resolved_paths_digest（3.5.1）。
- MUST resolved_paths_digest MUST 写入 Run Manifest（3.19.1）与 EventStream 头部（5.1.1），并进入 options_hash（3.19.2）；缺失即 Fail-Fast。
- MUST PathsConfig/ResolvedPaths MUST NOT 进入 scenario_id（3.6.2）；它们只影响“运行宿主可达性”，不改变场景语义。

落盘位置约束（回答“产物落盘位置偏好”）：

- MAY 默认将 `artifacts_root` 解析为工作区内的相对目录（推荐：`path:./artifacts/`），以便本地与 CI 一致；也 MAY 指向外部根目录。
- MUST 无论选择何处落盘：所有产物的 `artifact_ref`（尤其 `path:`）必须通过 ResolvedPaths 解析，并伴随 `resolved_paths_digest` 做校验与归因（3.6.1/5.1.1/3.19.1）。
- MUST 不允许模块内自行拼绝对路径或绕过 PathsConfig 直接写盘；发现绕行视为违反“单一真相/可复现治理”，strict_mode 下 MUST Fail-Fast（0.2/3.6.1）。

最小字段闭包（示意；字段闭包必须进入 paths_config_id 的 hash 输入，遵循 3.5.1）：

- MUST paths_config_id = hash(canonicalized PathsConfig)，遵循 3.5.1。
- MUST PathsConfig 至少包含：
  - roots：{scenario_root, artifacts_root, data_root}（每项为 string 或 null；若 null 导致解析不确定，则 strict_mode 下 MUST Fail-Fast）
  - search_order：string 数组（稳定顺序）
  - allow_symlink：bool
- MUST ResolvedPaths 至少包含：
  - resolved_roots：{scenario_root_abs, artifacts_root_abs, data_root_abs}
  - resolved_artifacts[]：{artifact_ref, abs_path}
  - resolved_paths_digest

#### 3.6.2 ScenarioID 与最小语义闭包

Anchor ID: Protocol.ScenarioID

- MUST scenario_id 表示“场景语义闭包”的内容哈希（不是路径哈希），用于门控、缓存与回放归因（3.7/5.1.1/7.4）。
- MUST scenario_id = hash(canonicalized ScenarioSpecClosure)，遵循 3.5.1；其闭包必须覆盖会改变“环境/动作空间/对手生态/多人路由”语义的所有引用。

最小语义闭包（字段名固定；不适用为 null，见 0.1.3）：

- MUST ScenarioSpecClosure 至少包含：
  - scenario_schema_id：固定字符串（例如 "scenario_spec_v1"；用于显式升级）
  - ruleset_id（3.2）
  - triad（3.3）
  - schema_hash（3.4）
  - abstraction_hash（3.6；action_bins_id + action_adapter_id + mapping_spec_id）
  - preflop_ref：{artifact_ref, digest} 或 null
  - postflop_ref：{artifact_ref, digest} 或 null
  - opponent_suite_id（3.16）
  - population_id（3.15）
  - mw_ladder_id：string 或 null（3.18；若场景允许 MW 路由则 MUST 非 null）
- MUST Scenario Package 的描述性字段（label/注释/作者等）MUST NOT 进入 ScenarioSpecClosure（见 0.1.2）。
- MUST 若 Scenario Package 源文件显式携带 scenario_id，则 MUST 与计算值一致，否则 strict_mode 下 MUST Fail-Fast。
#### 3.6.3 scenario_family_key 与 latest 语义

Anchor ID: Protocol.ScenarioFamilyKey

- MUST 定义并遵守：
  - scenario_family_key := hash(canonicalized {scenario_id, ruleset_id, abstraction_hash})，遵循 3.5.1。
- MUST 任何 “latest/别名” 指针只能在同一 scenario_family_key 内移动；MUST NOT 跨 family 漂移。
- MUST 一旦发生跨 family 漂移或歧义解析，Scenario Gate（7.4）必须 Fail-Fast，并输出 evidence_ref（6.2）。

说明：

- MUST abstraction_hash 的输入闭包必须包含会改变动作空间/映射语义的对象引用（至少：action_bins_id + action_adapter_id + mapping_spec_id）；任何遗漏视为口径漂移并 Fail-Fast（见 3.6/3.7/3.19.2）。

#### 3.6.4 Scenario 源文件与别名映射的载入约束（Normative）

- MUST Scenario Package 的唯一权威语义为 3.6；任何“源文件/目录/别名”仅为载入入口，不得成为第二真相源（0.1.2）。
- MUST 若系统支持从文件载入 Scenario Package（例如 specs/scenarios/*.json），则：
  - MUST 载入后先做 schema 校验；失败必须 Fail-Fast。
  - MUST 对载入内容执行 canonicalization 并计算 `scenario_id`（见 3.6.2 的最小语义闭包）；若文件内显式携带 `scenario_id` 字段，则 MUST 与计算值一致，否则 strict_mode 下 MUST Fail-Fast。
  - MUST RunSpec/Run Manifest 中最终写入与用于门控/缓存的字段必须是 `scenario_id` 与其派生闭包字段（ruleset_id/triad/schema_hash/abstraction_hash 等）；输入侧的 path/alias/ref 只能进入 resolution_trace（诊断用途），MUST NOT 进入 options_hash（3.19.2）或任何 *_hash 输入（0.1.2/3.5.1）。
- MUST 若系统支持 scenario alias/registry（例如 specs/scenarios/aliases.json 或等价机制），则该 alias 映射本身 MUST 是不可变 artifact（具备 digest + provenance_ref），并满足：
  - MUST alias 解析在 strict_mode 下必须是确定函数（7.4）：多候选/跨 family/依赖隐式默认值均 MUST Fail-Fast。
  - MUST alias_map_ref 与其 digest 仅进入 resolution_trace 与 Run Manifest（诊断/审计用途），MUST NOT 进入 options_hash；唯一进入 options_hash 的仍然只有解析后的 `scenario_id` 与其语义闭包字段（3.19.2）。

### 3.7 CacheKey Contract

Anchor ID: Protocol.CacheKeyContract

- MUST 缓存 key 至少包含：state\_hash、scenario\_id、schema\_hash、engine\_build\_id、options\_hash（见 3.19）。
- MUST options\_hash 覆盖 action\_adapter\_id / mapping\_spec\_id 等会影响映射结果的对象；否则视为幽灵缓存风险并拒绝启用。
- MUST 若启用 MW 路由，则 options\_hash MUST 覆盖 mw\_ladder\_id（3.18）以及各 rung 声明的 dependency\_ids（3.18）。
- MUST NOT 业务层手拼 key。

### 3.8 Observation View

Anchor ID: Protocol.ObservationView

- MUST 定义线上可见视图 ObservationView（作为所有 PlayerAgent 的唯一可见信息集输入）。
- MUST FeatureEncoder 仅以 ObservationView 为输入。
- MUST 训练数据由事件回放生成同构 ObservationView，防信息泄漏。
- MUST System/Opponent/Baseline 等任何 PlayerAgent **只能接收 ObservationView + Snapshot 摘要**；MUST NOT 直接读取/传递引擎内部 state 对象或不可见字段。

#### 3.8.1 BeliefSpec Contract

Anchor ID: Protocol.BeliefSpec

- MUST 将“多人信息集后验/继续概率”收敛为 BeliefSpec（可版本化/可哈希），并产出 belief\_spec\_id。
- MUST BeliefSpec 的输入只允许来自 ObservationView（3.8）与该手牌可见事件历史；MUST NOT 读取引擎内部 state 或不可见字段（Leakage Gate 仍适用，7.6）。
- MUST BeliefSpec 的输出为 belief\_digest: 对本次决策点的后验摘要指纹；其生成规则遵循 3.5.1 的 canonicalization。
- MUST belief\_digest 的 hash 输入 **MUST NOT** 直接包含浮点概率；若需要表达概率/强度信息，MUST 使用受控离散编码（例如 bucket\_id / 等级枚举 / 受控整数编码）并在 BeliefSpec 的权威实现中固定其映射规则。
- MUST 若某 MW rung 在 dependency\_ids 中声明 belief\_spec\_id，则：
  - 缺失 belief\_spec\_id 或 belief\_digest 时，必须触发门控/护栏并按 3.18 的 downgrade\_policy 单向降级（或 Fail‑Fast）。
  - ActionChosen 事件必须记录 belief\_spec\_id 与 belief\_digest（见 5.1）。
- MUST `belief_spec_id` 为 options\_hash（3.19.2）的字段之一：若所选 MW rung 在 dependency\_ids 中声明依赖，则其值 MUST 为该 `belief_spec_id`；否则 MUST 为 null。该字段 MUST 随 options\_hash 写入 Provenance（3.5）并通过 CacheKey 的 options\_hash 进入缓存闭包（3.7）。
- MUST 本节只定义契约与证据字段；MUST NOT 描述具体算法/模型实现细节。

### 3.9 MetricsSpec Contract

Anchor ID: Protocol.MetricsSpec

- MUST metric\_spec\_id = hash(canonicalized MetricsSpec)，遵循 3.5.1。
- MUST 比率指标输出机会集（numerator\_count, denominator\_count）。
- MUST 动作相关指标只基于 executed\_action。
- MUST 金额事实单位为 chips(int)；任何 bb/pot\_frac 显示单位 MUST 可回放其转换来源。
- MUST 输出携带 metric\_spec\_id；缺失视为无效。
- MUST NOT 在脚本/报表中内联新口径；只能引用既有 metric\_spec\_id。

#### 3.9.1 Action 分类的唯一派生规范（Normative）

- MUST 动作分类（fold/check/call/bet/raise/is_allin）必须由 Environment 基于 ExecutedAction + DecisionPoint Snapshot（to_call_chips/min_raise_to_chips/max_raise_to_chips/actor_commit_chips/actor_stack_chips）按 3.1 的唯一判定规则派生；Metrics/Report/Evaluation MUST NOT 自算或重写口径。
- MUST ActionChosen 事件（5.1）必须携带 `derived_action`（或等价字段闭包），至少包含：{kind, is_allin, target_total_commit_chips}；缺失时：
  - strict_mode 下 MUST Fail-Fast；
  - 非 strict_mode 下 MAY 由回放器按本条规则补算，但 MUST 将报告标记为 degraded 并输出 evidence_ref（6.2）。

### 3.10 ReportSchema Contract

Anchor ID: Protocol.ReportSchema

- MUST report\_schema\_id = hash(canonicalized ReportSchema)，遵循 3.5.1。
- MUST 每次评测至少产出结构化报告；文本日志只是渲染视图。
- MUST 文本渲染只能来自结构化报告与事件流派生（5.1）；不得绕开 ReportSchema 在各处拼装“第二套统计口径”。
- SHOULD 报告头额外输出 routing\_by\_rung（从 EventStream 聚合得到：{rung\_id: {count, degraded\_count}}），用于评测“各 rung 覆盖与贡献”（引用 3.18/5.1）。
- MUST 报告（以及 Run Manifest / Stage Evidence 的结构化字段）只能使用 **JSON‑Schema 可表达的类型闭包**（int/float/bool/str/null/array/object）；MUST NOT 直接输出 numpy/torch 等运行时类型。违反即在 strict\_mode 下 Fail‑Fast。
- MUST 报告头携带：provenance（3.5）、options\_hash（3.19.2）、scenario\_id（3.6）、schema\_hash（3.4）、event\_stream\_ref、event\_stream\_digest、metric\_spec\_id、report\_schema\_id、repro\_tier（3.5.2）；缺失则无效。
- MUST NOT 静默增删改名字段；任何变更走 0.4。

#### 3.10.1 RuleConformanceReport（规则一致性审计子报告）

Anchor ID: Protocol.RuleConformanceReport

- MUST RuleConformanceReport 是 ReportSchema（3.10）中的固定子块 `rule_conformance`；其字段闭包必须被 report_schema_id 覆盖（3.10）。
- MUST RuleConformanceReport 只能由 EventStream 回放派生（5.1.1），且仅允许以 RuleSet（3.2）+ EventStream 作为事实来源；MUST NOT 读取策略中间态或 Environment 内部 state 对象。
- MUST strict_mode 下，任何产出结构化报告的路径（至少包含 eval/doctor/stats）都 MUST 产出 `rule_conformance`；缺失或字段漂移即视为报告无效并 Fail-Fast（与 3.10 一致）。
- MUST 若出现失败项，则每条失败必须可由 replay({event_stream_ref, hand_selector}) 定位，并与最小证据闭包（6.2）兼容。

最小字段集（字段名固定；不适用时用 null，见 0.1.3）：

- context：{scenario_id, ruleset_id, triad, schema_hash, options_hash, provenance_ref, event_stream_ref, event_stream_digest}
- sampled_hands_count:int
- checked_items[]：受控集合（本条为权威）：button_rotation / forced_bets / rake / no_flop_no_drop / min_raise / allin_reopen / ledger_conservation
- failures_count:int
- failures[]：每条 MUST 包含 {hand_selector, item, reason, decision_id_or_state_hash, expected_or_null, observed_or_null, evidence_ref}
  - evidence_ref：{event_stream_ref, event_stream_digest, hand_selector}（字段闭包与 6.2 兼容；缺失即视为该 failure 不可回放）。

约束：

- MUST failures_count == len(failures)。
- MUST decision_id_or_state_hash 为结构化定位对象：{decision_id:null|int, state_hash:null|string}；若该失败定位到某个 DecisionPoint/ActionChosen，则二者 MUST 同时非 null；若为手级失败（例如 button_rotation/forced_bets），则二者 MUST 同时为 null（与 5.1.1 hand_selector 约定一致）。
- MUST checked_items 为去重后的稳定排序列表（字典序升序）。
- MUST 若 failures_count>0，则报告总体必须可机器判定为失败；strict_mode 下不得将 failures_count>0 标记为 pass。

### 3.11 Engine Boundary Contract

Anchor ID: Protocol.EngineBoundary

- MUST 规则引擎（pokerkit）只能由 Environment 持有与调用。
- MUST NOT 在 Environment 外推导/重算 pot/to\_call/commit/min‑raise/all‑in/rake/cap/边池等事实量。
- MUST Environment 在每个 DecisionPoint 输出只读 Snapshot（chips(int)），作为上层唯一事实输入。

#### 3.11.1 Snapshot 与 DecisionPoint 的最小事实字段集

- MUST Snapshot 至少包含最小事实字段集（缺失即不允许进入 Engines/Policy/Evaluation）：
  - street（受控枚举 Street；见 3.11.1.1）、actor_seat、players_alive_count
  - pot_chips、to_call_chips、actor_commit_chips、actor_stack_chips（均为 int chips）。
    - 约束：to_call_chips 表示该 actor 在本 DecisionPoint “最多可投入的跟注额”，必须已对 stack 做裁剪：to_call_chips := min(required_to_call_chips, actor_stack_chips)。
    - required_to_call_chips 由 Environment 基于引擎事实量计算（当前轮次最高 commit - actor_commit_chips），但 MUST NOT 以字段形式在 Snapshot 外暴露为第二口径。
  - min_raise_to_chips、max_raise_to_chips（可加注则为 int；否则显式为 null，见 0.1.3）
    - 约束：二者 MUST 同时为 null 或同时为 int；若为 int 则 MUST 满足 min_raise_to_chips <= max_raise_to_chips；strict_mode 下违反即 Fail-Fast。
    - 约束：若 actor_stack_chips <= to_call_chips（含 all-in call），则二者 MUST 为 null（该 actor 不具备加注/下注空间）。
    - 约束：若 max_raise_to_chips 为 int，则 MUST == actor_commit_chips + actor_stack_chips（table-stakes 上限）；若需要其他上限，必须通过 RuleSet 显式 Define 并进入 ruleset_id（3.2.2）。
    - 语义：当 to_call_chips==0 时，min_raise_to_chips 表示最小 BET 的 target_total_commit；当 to_call_chips>0 时，表示最小 RAISE 的 target_total_commit（算法见 3.2.3）。
  - legal_actions_digest：本决策点 Canonical Action 合法集合摘要（由 Environment 生成；规范见 3.11.2）。
  - observation_digest：ObservationView（3.8）的内容摘要（推荐 sha256）；MUST 由 Environment 对“本次决策点实际提供给 PlayerAgent 的 ObservationView”按 3.5.1 canonicalization 计算；strict_mode 下缺失即 Fail-Fast。

- MUST state_hash 输入 = Snapshot 最小字段集 + legal_actions_digest + observation_digest + ruleset_id + triad + schema_hash，并遵循 3.5.1。
- MUST 上层不得补算/推导上述字段；只能消费 Snapshot 输出（3.11）。

##### 3.11.1.1 Street 受控枚举（Normative）

Anchor ID: Protocol.StreetEnum

- MUST Street 为受控枚举；唯一允许取值：PREFLOP | FLOP | TURN | RIVER。新增取值视为 Define（0.4）；strict_mode 下出现未登记取值即 Fail-Fast。
- MUST Snapshot.street MUST 使用该枚举，表示当前 DecisionPoint 所处街。
- MUST StreetDealt.street MUST 使用同一枚举，但事件仅允许出现 FLOP | TURN | RIVER；PREFLOP MUST NOT 出现在 StreetDealt。
- MUST Street 的字符串表示一律使用全大写；strict_mode 下大小写不匹配 MUST Fail-Fast。

#### 3.11.2 legal_actions_digest 的唯一规范（排序/去重/编码）

- MUST legal_actions_digest 的输入为 Canonical Action 列表（每项为 {kind, target_total_commit_chips}），其生成只能由 Environment 完成。

- MUST legal_actions_digest 表示“本决策点允许 Policy 提议的**离散** Canonical Action 候选集合”；其候选集合的唯一来源为：triad.action_bins_id 所定义的 ActionSpace，经 ActionAdapter/MappingSpec（3.12/3.13）在本 DecisionPoint Snapshot 下过滤得到。
- MUST legal_actions_digest 仅是候选列表的不可逆指纹；单独的 digest MUST NOT 被解释为可逆编码或“可直接还原候选集合”。
- MUST legal_actions_digest MUST NOT 试图表达“连续可下注区间”；连续区间只通过 Snapshot 的 {to_call_chips, min_raise_to_chips, max_raise_to_chips} 表达；离散候选集合由 ActionSpace 负责。

- MUST 候选过滤的唯一判定（仅由 Environment 执行；其他层 MUST NOT 重算）：
  - FOLD：仅当 to_call_chips > 0 才允许；否则 MUST NOT 出现。
  - CHECK：仅当 to_call_chips == 0 才允许。
  - CALL：仅当 to_call_chips > 0 才允许，且 target_total_commit_chips MUST == actor_commit_chips + to_call_chips（3.1）。
  - BET：仅当 to_call_chips == 0 且 min_raise_to_chips/max_raise_to_chips 均非 null 才允许；并要求 min_raise_to_chips <= target_total_commit_chips <= max_raise_to_chips。
  - RAISE：仅当 to_call_chips > 0 且 min_raise_to_chips/max_raise_to_chips 均非 null 才允许；并要求 min_raise_to_chips <= target_total_commit_chips <= max_raise_to_chips。

- MUST 归一化规则（防止同一语义多种表示）：
  - CHECK vs CALL：若 to_call_chips==0，则合法集合中 MUST 只允许 CHECK；CALL(0) MUST NOT 出现。
  - 对 FOLD/CHECK/CALL 的 target_total_commit_chips 必须按 3.1 的唯一规则派生（禁止出现 null 或歧义表示）。

- MUST 去重规则：
  - 若出现重复的 (kind, target_total_commit_chips) 条目，则 strict_mode 下 MUST Fail-Fast；非 strict_mode 下 MUST 先去重并在事件流记录 degraded=true 与 evidence_ref（6.2）。

- MUST 稳定排序规则（作为 digest 的唯一输入顺序）：
  - kind_order 固定为：FOLD < CHECK < CALL < BET < RAISE。
  - 在同 kind 内，按 target_total_commit_chips 升序排序。

- MUST digest 计算：
  - 将排序后的列表按 3.5.1 canonicalization 序列化后取 sha256，得到 legal_actions_digest。
  - legal_actions_digest 形态为 {alg:"sha256", hex:string}；strict_mode 下若 alg 不是 "sha256" 则 MUST Fail-Fast。
- MUST legal_actions_digest 只反映“合法动作集合口径”，不得混入策略概率、bin 映射、随机采样等信息。

#### 3.11.3 Snapshot 与 legal_actions_digest 的一致性自检（Normative）

- MUST 对每个 DecisionPoint，Environment 必须执行以下一致性自检；strict_mode 下任一失败 MUST Fail-Fast：
  - 若 legal_actions_digest 所代表的候选集合中包含任一 BET/RAISE，则 Snapshot.{min_raise_to_chips,max_raise_to_chips} MUST 均非 null；反之，若二者任一为 null，则候选集合 MUST NOT 包含 BET/RAISE。
  - 候选集合中任一 BET/RAISE 的 target_total_commit_chips MUST 满足：min_raise_to_chips <= target_total_commit_chips <= max_raise_to_chips。
  - 若 to_call_chips==0，则候选集合 MUST 包含 CHECK 且 MUST NOT 包含 CALL；若 to_call_chips>0，则候选集合 MUST 包含 CALL 且 MUST NOT 包含 CHECK。
  - 候选集合中 FOLD 的存在性 MUST 与 to_call_chips>0 条件一致（3.11.2）。

- MUST 若非 strict_mode 允许降级运行，则以上任一不一致必须在事件流与 Stage Evidence 中显式标记 degraded=true，并输出 evidence_ref（6.2）；不得静默继续。

### 3.12 ActionAdapter Contract

Anchor ID: Protocol.ActionAdapter

- MUST rounding\_mode 为受控枚举，唯一允许取值：floor | ceil | nearest\_ties\_up。新增取值视为 Define（0.4）；strict\_mode 下出现未登记取值即 Fail‑Fast。

- MUST 外部动作表示（solver UID、bins、pot‑fraction、raise‑add 等）到 Canonical Action（3.1）的转换只能通过 ActionAdapter。

- MUST 所有涉及 **float/比例/PPM → chips(int)** 的换算采用确定的 rounding\_mode，并将 rounding\_mode、reason_code、lossy、fallback_mode（若适用）与 delta_target_total_commit_chips（若发生替换）写入 mapping\_trace（字段闭包以 3.13.1 为准）；动作前后由 proposed_action / executed_action 提供；不得隐式截断/四舍五入。

- MUST 产出 mapping\_trace（链路/IDs、lossy、reason_code、fallback_mode、delta_target_total_commit_chips 等；字段闭包以 3.13.1 为准；动作前后由 proposed_action / executed_action 提供）。

- MUST Adapter 必须显式声明映射是否 reversible 或 lossy；若为 lossy，MUST 在 mapping\_trace 中记录 loss 与原因（可证伪）。

- MUST action\_adapter\_id = hash(canonicalized ActionAdapter 配置闭包)，遵循 3.5.1。

- MUST 该闭包覆盖所有会改变外部语义 → target\_total\_commit\_chips 的规则（至少包含 rounding\_mode、bet/raise 语义换算、lossy/fallback 策略）；未覆盖视为口径漂移并 Fail‑Fast。

- MUST action\_adapter\_id 被 3.6（abstraction\_hash）、3.19.2（options\_hash）与 3.7（cache key）引用；缺失即拒绝运行/读缓存。


#### 3.12.1 外部动作换算的唯一实现点与工程执法（Normative）

> 目标：把“外部动作表示→chips(int)→合法集合对齐”的换算彻底收口到唯一实现点，阻断多处重复换算复发一致性问题。

- MUST 除 ActionAdapter（3.12）、TreePathMappingSpec（3.13）与 Environment 的 legalize（3.1.1）之外，任何模块/脚本/评测器 MUST NOT 出现以下换算逻辑：
  - float/比例/PPM → chips(int)；
  - pot_frac/uid/bins/raise_add → target_total_commit_chips；
  - clamp/snap/round/nearest-bin 的实现代码（除非被上述契约对象引用）。
- MUST 以工程方式执法：lint/静态检查/依赖边界（例如 Rust crate 可见性、Python import 规则、denylist grep/AST rule）在 CI 中强制；发现绕行即拒绝合并。
- SHOULD 在语言层面优先用“可见性/依赖边界”把换算实现封装为私有模块（例如 Rust 私有模块/私有 crate API、Python 不导出内部换算函数、TS 仅导出类型不导出实现），使非授权模块在编译/导入阶段即无法调用。
- MUST 若确需新增换算能力或回退策略，必须以 Refine/Define 的方式落入 ActionAdapter 或 TreePathMappingSpec 的可哈希闭包，并确保其影响进入 action_adapter_id/mapping_spec_id 与 options_hash（3.19.2）；不得以临时代码绕过契约对象。

##### 3.12.1.1 动作口径三件套的唯一实现点（Adapter→Legalize→DerivedAction）（Normative）

> 目标：把“动作怎么表示、怎么变合法、怎么被统计”钉成唯一流水线，避免各处各算各的复发。

- MUST 外部动作表示 → Canonical Action（3.1）的转换**只能**发生在 ActionAdapter（3.12）与/或 TreePathMappingSpec（3.13）；除这两处外出现任何等价换算，视为口径漂移并拒绝合并。
- MUST Canonical Action → ExecutedAction 的合法化替换**只能**发生在 Environment 的 canonicalize→legalize（3.1.1），且合法集合的唯一来源为 Snapshot.legal_actions_digest（3.11.2）；任何模块 MUST NOT 以“连续区间直觉/自算 min-raise”绕过该集合。
- MUST ExecutedAction → derived_action（fold/check/call/bet/raise/is_allin）的派生**只能**由 Environment 按 3.9.1 输出并写入事件流（5.1）；Metrics/Report/Evaluation MUST 只使用 derived_action，不得自算。
- MUST 工程执法同样覆盖“派生口径”：在 evaluation/metrics/report 层发现对 Snapshot/ExecutedAction 的自定义派生（例如自行判断 raise/all-in、或在 to_call==0 时输出 CALL），strict_mode 下视为违规并 Fail-Fast；非 strict_mode 下也必须标记 degraded 并输出 evidence_ref（6.2）。

#### 3.12.2 fallback_policy 的唯一规范（Normative）

> 目标：将“非法动作如何替换/如何对齐离散 bins”的语义钉死到**唯一算法 + 可哈希闭包**，避免各处各算各的。

- MUST 任一“合法化替换/回退执行”只能使用 ActionAdapter 配置闭包中显式声明的 `fallback_policy.mode`；该 mode 及其所有决定性参数 MUST 进入 `action_adapter_id` 的 hash 输入闭包（3.12/3.5.1）。
- MUST Environment 进行 legalize（3.1.1）时，只能对 `legal_actions_digest` 所代表的候选集合做选择；MUST NOT 以连续区间直觉绕过候选集合（3.11.2）。

受控枚举：fallback_policy.mode（唯一允许取值；本节为权威取值集合）

- fail_fast
- conservative_check_call
- snap_nearest
- clamp_then_snap

确定算法（只依赖 Snapshot + 候选集合；严禁隐式默认）：

- 输入：
  - `proposed`：规范化后的 Canonical Action（3.1.1 Canonicalize 输出）。
  - `S`：Environment 在本 DecisionPoint 计算 `legal_actions_digest` 时得到的候选集合（每项为 {kind, target_total_commit_chips}；该集合可由 triad.action_bins_id + Snapshot + (action_adapter_id,mapping_spec_id) 重新计算验证；见 3.11.2）。
  - `Snapshot`：至少包含 {to_call_chips, actor_commit_chips, min_raise_to_chips, max_raise_to_chips}（3.11.1）。

- 若 `proposed ∈ S`：MUST `executed = proposed`，并在 mapping_trace 中标记 `reason_code=none`、`lossy=false`（3.13.1）。

- 否则（`proposed ∉ S`）：
  - 若 mode==fail_fast：strict_mode 下 MUST Fail-Fast；非 strict_mode 下也 MUST Fail-Fast（该 mode 不允许替换）。

  - 若 mode==conservative_check_call：
    - 若 `to_call_chips==0`：MUST 选择 CHECK（其 target_total_commit_chips 由 3.1 唯一规则派生）。
    - 若 `to_call_chips>0`：MUST 选择 CALL（其 target_total_commit_chips 由 3.1 唯一规则派生）。
    - 若上述目标动作不在 `S`（理论上不应发生；视为上游口径漂移）：strict_mode 下 MUST Fail-Fast；非 strict_mode 下 MAY 退化为“从 S 中选择 kind_order 最小的一项”，并标记 degraded=true 与 evidence_ref（6.2/3.19.1）。

  - 若 mode==snap_nearest：
    - 定义候选子集 `T`：
      - 若 `proposed.kind ∈ {BET, RAISE}`：`T = {a ∈ S | a.kind == proposed.kind}`；
      - 否则：`T = {a ∈ S | a.kind == proposed.kind}`（该集合 SHOULD 为单元素）。
    - 若 `T` 为空：MUST 等价于执行 mode==conservative_check_call。
    - 否则选择 `a* ∈ T` 使 `abs(a*.target_total_commit_chips - proposed.target_total_commit_chips)` 最小；若并列，MUST 选择 `target_total_commit_chips` 更小者（保守 tie-break）。
    - MUST `executed = a*`。

  - 若 mode==clamp_then_snap：
    - 若 `proposed.kind ∈ {BET, RAISE}` 且 `min_raise_to_chips/max_raise_to_chips` 均非 null：
      - `clamped_target = min(max(proposed.target_total_commit_chips, min_raise_to_chips), max_raise_to_chips)`；
      - 令 `proposed' = {kind: proposed.kind, target_total_commit_chips: clamped_target}` 并按 mode==snap_nearest 继续选择。
    - 否则 MUST 等价于 mode==snap_nearest。

- MUST 任一次替换（proposed != executed）必须：
  - 在 ActionChosen.mapping_trace 中记录 `fallback_mode`、`delta_target_total_commit_chips` 与 `reason_code`（3.13.1/5.1）；
  - 在 Stage Evidence 中标记 degraded=true，并给出 degraded_reason 与 evidence_ref（3.19.1/6.2）；
  - 保证其语义闭包已进入 `action_adapter_id` 或 `mapping_spec_id`，并进入 options_hash（3.12/3.13/3.19.2）。


### 3.13 TreePathMappingSpec

Anchor ID: Protocol.TreePathMappingSpec

- MUST TreePathMappingSpec 是“离散动作/树路径/尺寸桶”等抽象空间到 Canonical Action（3.1）/合法候选集合（3.11.2）的**唯一可哈希映射契约对象**，用于保证训练/推理/回放/统计在同一映射口径下工作。
- MUST TreePathMappingSpec 仅允许声明：
  - domain_spec：映射域（例如 preflop/postflop、street、stack_bucket、positions 等）的受控离散定义；
  - binning_spec：离散桶定义（size bins / raise-to bins / action bins 的引用或内嵌闭包）；
  - mapping_rule：从 domain_spec 到候选集合的确定映射规则（必须可被 3.5.1 规范序列化）；
  - tie_break_rule：并列选择的稳定规则（必须声明并进入 hash 输入闭包）；
  - fallback_policy：若映射产生非法/空集合时的处理（必须声明并进入 hash 输入闭包；与 3.12.2 的 fallback_policy 兼容且不得绕开 legal_actions_digest）。
- MUST `mapping_spec_id = hash(canonicalized TreePathMappingSpec)`，遵循 3.5.1。
- MUST mapping_spec_id 被 `abstraction_hash`（3.6）、`options_hash`（3.19.2）与 CacheKey（3.7）引用；缺失即拒绝运行/读缓存。
- MUST Environment 在生成 legal_actions_digest（3.11.2）与执行 Proposed→Executed（4.2）过程中，若使用了 TreePathMappingSpec，则 ActionChosen.mapping_trace.mapping_spec_id MUST 为该 mapping_spec_id；否则 MUST 为 null（0.1.3）。
- MUST 除 Environment 外，任何模块 MUST NOT 自行实现或“内联一段映射规则”绕开 TreePathMappingSpec；违反视为口径漂移并 Fail-Fast。

#### 3.13.1 mapping_trace 最小字段集（Normative）

> 目标：让任何“外部表示→Canonical→合法集合”的映射与替换都具备统一、可审计、可回放的结构化证据，避免只靠日志猜。

- MUST EventStream 的 ActionChosen.mapping_trace 必须是结构化对象，并满足如下最小字段闭包；缺失字段即视为口径漂移。
- MUST strict_mode 下，任一 ActionChosen 缺失 mapping_trace 或 mapping_trace 缺失最小字段集 MUST Fail-Fast。
- MUST mapping_trace 的字段含义为**执行证据**，不得承载解释性统计（bb/100、胜率等属于 3.9/3.10）。

最小字段集（字段名固定；不适用为 null，见 0.1.3）：

- trace_schema_id：固定字符串 "mapping_trace_v1"（用于显式升级；变更需 bump event_model_id，5.1.1）
- action_adapter_id：string（必须等于本次运行的 action_adapter_id；见 3.12/3.6/3.19.2）
- mapping_spec_id：string|null（若本次选择涉及 TreePathMappingSpec；否则为 null）
- rounding_mode：string|null（若本次映射涉及 chips 取整；否则为 null；取值集合见 3.12）
- reason_code：受控枚举（本节为权威取值集合）：
  - none
  - kind_override
  - rounding
  - illegal_action
  - snap_to_bin
  - clamp
  - conservative_fallback
  - other
- lossy：bool（是否发生 lossy 变换/替换）
- delta_target_total_commit_chips：int|null（executed.target_total_commit_chips - proposed.target_total_commit_chips；若无变化则为 0；若无法计算则为 null）
- fallback_mode：string|null（若发生 fallback；其取值见 3.12.2 的 fallback_policy.mode；否则为 null）

约束：

- MUST 若 proposed_action != executed_action：
  - lossy MUST 为 true；
  - reason_code MUST NOT 为 none；
  - delta_target_total_commit_chips MUST 非 null。
- MUST 若 proposed_action == executed_action：
  - lossy MUST 为 false；
  - reason_code MUST 为 none；
  - fallback_mode MUST 为 null；
  - delta_target_total_commit_chips MUST 为 0。
- MUST 若 reason_code∈{snap_to_bin,clamp,conservative_fallback}：fallback_mode MUST 非 null。
- MUST 若 reason_code==kind_override：mapping_trace 必须与 3.1.1 的 kind 重建/覆写行为一致（不得出现“只改 kind 不改 target”）。

### 3.14 OpponentProfileSpec

Anchor ID: Protocol.OpponentProfileSpec

- MUST 将“对手风格/强度目标”定义为可版本化契约对象 opponent_profile_id（内容哈希）。
- MUST `opponent_profile_id = hash(canonicalized OpponentProfileSpec)`，遵循 3.5.1。
- MUST 仅声明目标行为分布与约束域（可按位置/有效筹码/街/人数分段）。
- MUST NOT 在本文档定义实现算法/调参过程。

### 3.15 TablePopulationSpec

Anchor ID: Protocol.TablePopulationSpec

- MUST 将“一桌对手生态组成”定义为可版本化契约对象 population_id（内容哈希）。
- MUST `population_id = hash(canonicalized TablePopulationSpec)`，遵循 3.5.1。
- MUST 声明：座位数/席位分配（或分布）+ opponent_profile_id 的混合权重（或席位绑定）（引用 3.14）。
- MUST population_id 被 Scenario（3.6）引用；缺失即 Fail‑Fast。

### 3.16 OpponentSuiteSpec

Anchor ID: Protocol.OpponentSuiteSpec

- MUST 将对手集合按用途分层为 opponent_suite_id（内容哈希），并使其用途（purpose）可被审计与复现。
- SHOULD 提供覆盖以下用途的标准 suite：baseline / realistic / pressure / exploit；这些用途字符串仅用于展示/筛选，MUST NOT 进入 options_hash 或任何 *_hash 输入（0.1.2/3.5.1）。
- MUST `opponent_suite_id = hash(canonicalized OpponentSuiteSpec)`，遵循 3.5.1。
- MUST opponent_suite_id 引用一个 TablePopulationSpec（3.15）及其依赖的 OpponentProfileSpec 集合（3.14）。

#### 3.16.1 Opponent 相关 Spec 的注册、载入与可复现约束（Normative）

- MUST OpponentProfileSpec（3.14）/ TablePopulationSpec（3.15）/ OpponentSuiteSpec（3.16）的唯一权威语义分别以其权威锚点为准；任何“文件/目录/别名”仅为载入入口，不得成为第二真相源（0.1.2）。
- MUST 对任一 Opponent 相关 Spec：
  - MUST `*_id = hash(canonicalized *Spec)`，遵循 3.5.1。
  - MUST 若源文件显式携带 `*_id` 字段，则 MUST 与计算值一致，否则 strict_mode 下 MUST Fail-Fast。
  - MUST RunSpec（3.19）与任何门控/缓存/报表头中，只允许出现解析后的 `opponent_suite_id / population_id / opponent_profile_id`（以及依赖的 artifact digests）；输入侧 path/alias/ref 只能进入 resolution_trace（诊断用途），MUST NOT 进入 options_hash（3.19.2）或任何 *_hash 输入闭包（0.1.2/3.5.1）。
- MUST 若提供 OpponentRegistry / alias 映射（例如 specs/opponents/aliases.json），则该映射本身 MUST 是不可变 artifact（digest + provenance_ref），且 strict_mode 下解析必须是确定函数：多候选/跨 scenario_family_key/依赖隐式默认值均 MUST Fail-Fast（7.8/7.4 类比）。
- SHOULD doctor/stats 输出可见的 OpponentRegistry：列举可用 opponent_suite_id / population_id / opponent_profile_id 与其来源 ref（artifact_ref 或源文件 ref），用于审计；但任何运行门控必须只基于这些 *_id 与其可解析内容（7.8/7.3）。

### 3.17 CalibrationSpec

Anchor ID: Protocol.CalibrationSpec

- MUST 将“对手校准闭环”定义为可版本化契约对象 calibration\_id（可哈希）。
- MUST 声明：校准目标（引用 metric\_spec\_id）、收敛判据、预算与输出产物形态。
- MUST 校准产物携带 Provenance（3.5）并生成 opponent\_artifact\_id（或 params\_hash）；需要校准的 suite MUST 以其为唯一加载输入。

### 3.18 MW Strategy Ladder Spec

Anchor ID: Protocol.MWStrategyLadderSpec

- MUST 将多人成员（Snapshot.players_alive_count>=3）场景下的“引擎/近似选择”定义为唯一契约对象 MWStrategyLadderSpec，并分配 mw\_ladder\_id（可版本化/可哈希）。
- MUST MWStrategyLadderSpec 由有序 rungs 构成；Engines/Policy MUST 按序评估并选择首个满足适用条件的 rung。
- MUST 每个 rung 仅声明（不得嵌入算法细节）：
  - applicability\_predicate：基于 Snapshot（3.11）可见事实的适用条件；
  - dependency\_ids：所需资产/模型/求解器 ID（作为门控与 options\_hash 输入）；
  - assumption\_guard\_id：引用 7.7 的 MWAssumptionGuardSpec（内容哈希）；baseline/failsafe 允许为 null。
  - output\_requirements：必须附带的诊断字段名集合（受 schema\_hash 管控）；
依赖约定（多人能力栈最小化）：
- MAY micro3 / reducer4p 等 rung 的 dependency\_ids 进一步包含：belief\_spec\_id（3.8.1）、mw\_risk\_spec\_id（7.7）、以及用于 MW Blueprint 的 policy\_deps 引用（3.19.3，policy\_kind=blueprint）。
- MUST 若上述依赖被声明但运行时缺失，则该 rung 必须按 downgrade\_policy 单向降级；MUST NOT 静默 fallback 为更激进的 rung。
- MUST 若运行实际使用了上述任一依赖，其 id/digest 必须进入 options\_hash（3.19.2）并可在 EventStream/ActionChosen 中回放定位（5.1）。
- MUST mw\_ladder\_id 被 Scenario Package（3.6）与 Provenance Envelope（3.5）引用；缺失视为不可用。
- MUST Event Stream 在 ActionChosen 记录 routing（mw\_ladder\_id + rung\_id + mw\_context\_digest），用于分桶评估与回放归因（5.1）。
- MUST mw\_context\_digest = hash(canonicalized {state\_hash, mw\_ladder\_id, rung\_id, belief\_digest\_or\_none, mw\_risk\_spec\_id\_or\_none})，并遵循 3.5.1；其目的仅是为 MW 路由与护栏触发提供可比对、可回放的上下文指纹（非算法细节）。
- MUST 上述 canonicalized 输入中的 \*\_or\_none 语义在序列化时必须以 JSON null 表达（见 0.1.3），MUST NOT 使用字符串 "none"。
- MUST NOT 将 HU 策略/任意启发式作为 MW 默认真相；只能作为 ladder 中显式 rung，且其假设与护栏必须被记录与门控（7.7）。

#### 3.18.1 Ladder 规模与保守性预算

> 本小节约束 Ladder 的“规模与风险形状”，以提高落地成功率并避免策略/口径膨胀。

- MUST Ladder 保持短小：rungs 总数 **SHOULD ≤ 5**；若必须超出，必须走 0.4 的 Define 并说明新增 rung 不可由既有 rung 覆盖的原因。
- MUST rung 顺序体现“保守优先”的风险单调性：越靠前的 rung 越 **依赖更少、行为更保守、失败影响更可控**。
- MUST downgrade\_policy **只允许向更保守的 rung 单向降级**（或 Fail‑Fast）；MUST NOT 因缺失资产/不确定性而升级到更激进的 rung。
- SHOULD 提供一个 **Baseline rung**：仅保证合法性与可回放证据链，用于环境/口径/统计验收时的基准对手或基准策略（不追求强度）。
- SHOULD 在“仅有 HU 引擎”的阶段提供一个 **HU‑Isolate rung**：其目标仅是把局面推向 HU 或保持低风险（而非宣称 MW‑GTO）。
- MAY 提供 **Micro‑3P rung**（Snapshot.players_alive_count==3 且依赖满足时启用），并必须显式声明其适用范围与回退边界。
- MUST 提供最终 **Failsafe rung**（或明确 Fail‑Fast）：当所有依赖缺失/假设不成立时，系统仍能选择可解释且保守的动作集合，并把触发原因写入事件流（5.1）。

#### 3.18.2 官方最小 Rung ID 集合（防止自由命名分叉）

- MUST rung\_id 仅允许取受控集合：baseline / hu\_isolate / micro3 / reducer4p / failsafe。
- 若需新增 rung\_id，MUST 走 0.4 Define，并在 ladder 中声明适用域与回退边界；否则拒绝加载该 ladder。

---

### 3.19 RunSpec Contract

Anchor ID: Protocol.RunSpec

定义：RunSpec 是一次运行的**唯一语义入口**（对象选择 + 意图选择 + 可复现控制）；其语义闭包由 options\_hash（3.19.2）锁定，并写入 Run Manifest（3.19.1）。

最小字段集（语义层）：

- MUST 至少引用：scenario\_id（3.6）、profile\_id（3.20）、policy\_id（3.19.3）、opponent\_suite\_id（3.16；不涉及则显式为 null）。
- MUST 明确：seed、strict\_mode、execution\_hint（仅提示执行方式，不改变语义口径）。
- MUST 固定：run\_id 与 options\_hash（3.19.2）。
- MUST 在运行开始写入结构化 Run Manifest 头：run\_id/options\_hash/seed/strict\_mode +（scenario/profile/policy/opponents）+ provenance（3.5）+ rng\_lineage\_id（3.5）+ ResolvedPaths + resolved\_paths\_digest（3.6.1）。
- MUST 在 run 结束后冻结 Run Manifest 为不可变产物并计算 digest（3.5.1）；该 digest MUST 进入报告头（3.10）与回归比较输入。

#### 3.19.0 RunID Contract（Normative）

> 目的：回答“run_id 生成策略（内容哈希 vs UUID）”，并把它变成可机器执法的契约，避免跨机/跨语言引用漂移。

- MUST `run_id` 为**内容寻址**（content-addressed）标识，且在 Tier‑A 复现承诺下跨机器稳定。
- MUST 定义 `run_id_schema_id`（固定字符串，例如 "run_id_v1"），并将其作为 hash 输入的一部分，用于显式升级。
- MUST run_id 的唯一生成规则：
  - `run_id = sha256( canonicalized { run_id_schema_id, options_hash, seed } )`（hex 小写，长度 64；canonicalization 规则同 3.5.1）。
- MUST `run_id` 仅表达“语义运行闭包 + 随机种子”的稳定引用；它不得承载文件路径、时间戳或执行资源信息。

可选区分（物理执行实例，不影响语义）：

- MAY 额外记录 `run_instance_uuid`（随机 UUID）用于区分多次重复执行的落盘目录/日志聚合。
- MUST `run_instance_uuid` 只能进入 Run Manifest 的诊断字段（例如 resolution_trace/execution_trace），MUST NOT 进入 options_hash、任何 *_digest 输入或门控判定。

#### 3.19.1 Stage Evidence 最小字段集

> 目的：让“断点续跑/幂等审计/回归对比”不依赖日志文本，而依赖可机器校验的结构化证据；同时保持字段稳定、简约。

##### 3.19.1.1 Stage Evidence 受控枚举（Normative）

Anchor ID: Protocol.StageEvidenceEnums

- MUST 下列受控枚举的取值集合**只允许**在本锚点列出一次；其他章节（含示例）MUST NOT 重列/扩展取值集合（见 0.4.1）。

stage_id（与 3.21 CLI 顶层动词一致）：
- init
- import-preflop
- solve-postflop
- train
- eval
- doctor
- stats

artifact_kind（Stage Evidence 的 inputs_summary/outputs_summary）：
- runspec
- scenario_package
- jobs
- chunk
- manifest
- sqlite_index
- dataset
- model
- event_stream
- report

status：
- pass
- fail

degraded_reason（degraded=false 时必须为 null）：
- missing_asset
- guard_triggered
- illegal_action
- mapping_lossy
- fallback_policy
- other

##### 3.19.1.2 Stage Evidence 最小字段闭包（Normative）

Run Manifest 中每个 pipeline stage 的记录 MUST 包含以下最小字段集（不得缺省、不得由脚本自由扩展语义）：

- stage_id：受控枚举（见 3.19.1.1）。
  - 注：ingest 作为 solve-postflop 的内部子步骤，只能体现在 inputs/outputs_summary 的 artifact_kind 与 counts 中，不得作为 stage_id。

- effective_context：本 stage 实际使用的语义上下文，至少包含：
  - scenario_id（3.6）
  - ruleset_id（3.2）
  - triad（3.3）
  - schema_hash（3.4）
  - options_hash（3.19）
  - resolved_paths_digest（Run 级 ResolvedPaths 的指纹；见 3.6/3.19）

- inputs_summary[]：输入产物摘要列表；每个条目 MUST 包含：
  - artifact_kind：受控枚举（见 3.19.1.1；新增取值 MUST 走 0.4 Define 并同步更新 0.3）
  - artifact_ref：稳定引用（MUST 使用受控前缀之一：run:// / scenario:// / artifact:// / path:；且必须可唯一定位）
  - digest：{ alg, hex }（推荐 sha256；DigestObject 形态见 3.5.1.2）
  - counts：稳定计数键值（仅允许“不可歧义的客观计数”，例如 rows/spots/chunks/hands/events/files）
  - provenance_ref：指向 Provenance（3.5）的引用（可为 provenance_hash 或 provenance 文件指针）

- outputs_summary[]：输出产物摘要列表；字段同 inputs_summary。

- status：受控枚举（见 3.19.1.1）。

- degraded：true | false（是否发生会改变语义可信度的降级/替代执行）。

- degraded_reason：受控枚举（见 3.19.1.1）；degraded=false 时 MUST 为 null。

- degraded_counts：{reason: count}（可为空对象）。约束：
  - 若 degraded==false：degraded_reason MUST 为 null，且 degraded_counts MUST 为空对象。
  - 若 strict_mode==true 且 degraded==true：status MUST 为 fail（禁止假成功）。

- evidence_ref：若 fail 或 degraded=true，MUST 指向可回放证据；degraded=true 时必须包含 degraded_reason 与影响面。

约束：

- counts MUST NOT 引入解释性口径（例如 bb/100、胜率等属于 3.9/3.10 的派生产物，不得混入 stage evidence）。
- 任何 stage 的“幂等判定” MUST 仅基于：effective_context + inputs_summary 的 digest+counts；不得以时间戳/随机顺序作为隐式输入。


#### 3.19.2 options\_hash Definition

- MUST options\_hash = hash(canonicalized “run semantic closure”)，遵循 3.5.1。
- MUST 覆盖所有会改变“决策语义/映射/门控结果”的输入引用与开关，至少包含：
  - scenario\_id（3.6）、ruleset\_id（3.2）、triad（3.3）、schema\_hash（3.4）、resolved\_paths\_digest（3.6.1）
  - abstraction\_hash（3.6；派生自 action\_bins\_id + action\_adapter\_id + mapping\_spec\_id）
  - policy\_id（3.19.3）、profile\_id（3.20）、opponent\_suite\_id（3.16；不涉及则显式为 null）
  - opponent\_artifact\_id\_or\_params\_hash（若 suite 需校准，见 3.17/7.8；不涉及则显式为 null）
  - mw\_ladder\_id（3.18；若该 scenario 允许 MW 路由；否则显式为 null）
  - belief\_spec\_id（3.8.1；若所选 MW rung 声明依赖；否则显式为 null）
  - mw\_risk\_spec\_id（7.7；若所选 MW rung 声明依赖；否则显式为 null）
  - adaptation\_digest（若 policy 启用适配；不涉及则显式为 null）
  - engine\_build\_id、solver\_build\_id、pokerkit\_version（3.5）
  - strict\_mode 与 RunSpec 中任何“会改变语义”的布尔开关
- MUST NOT 包含：时间戳、日志级别、workers/resume 等 execution\_hint、以及 *\_label/\_alias（0.1.2）。
- MUST options\_hash 被写入：Provenance（3.5）、Run Manifest（3.19.1）、CacheKey（3.7）与报告头（3.10）；缺失即拒绝加载/读取缓存。

#### 3.19.3 PolicySpec Contract

Anchor ID: Protocol.PolicySpec

**定义：**PolicySpec 是一次运行中“策略来源与依赖”的唯一契约对象；RunSpec 的 policy\_id **MUST** 指向某个 PolicySpec（可版本化/可哈希）。

最小字段集（声明性，不含算法细节）：

- **policy\_kind**：受控枚举，MUST ∈ {model, oracle, live\_oracle, blueprint, rule, baseline}；新增取值视为 Define（0.4）
- **policy\_deps[]**：依赖产物列表（artifact\_ref + digest），用于门控、options\_hash 与 cache key（3.7/3.19）
- **policy\_params\_digest**：影响决策语义的参数指纹（不描述实现），遵循 3.5.1
- **stochastic**：true|false；若 true，则 MUST 由 RNGManager 受控并可由 rng\_lineage\_id 回放（3.5）

硬约束：

- MUST policy\_id = hash(canonicalized PolicySpec)，遵循 3.5.1；policy\_label 仅用于展示，MUST NOT 进入 options\_hash（0.1.2）
- MUST policy\_id 纳入：options\_hash（3.19）、Provenance（3.5）、CacheKey（3.7）与报告头（3.10）；缺失即拒绝运行/加载
- MUST 任何 policy 的降级/回退必须以 degraded 机制显式记录（3.19.1），且在事件流中体现 proposed→executed 的替换与原因（4.2/5.1）

#### 3.19.3.1 PolicySpec 的注册、载入与可复现约束（Normative）

- MUST PolicySpec 的唯一权威语义为 3.19.3 本节内容；PolicySpec 的任意“文件/目录/别名”仅为载入入口，不得成为第二真相源（0.1.2）。
- MUST `policy_id = hash(canonicalized PolicySpec)`，遵循 3.5.1；运行语义闭包中只允许出现 `policy_id`（3.19.2），不得以路径/别名/“latest”替代。
- MUST 若系统支持从文件载入 PolicySpec（例如 specs/policies/*.json），则：
  - MUST 载入后先做 schema 校验；失败必须 Fail-Fast。
  - MUST 对载入内容执行 canonicalization 并计算 `policy_id`；若文件内显式携带 `policy_id` 字段，则 MUST 与计算值一致，否则 strict_mode 下 MUST Fail-Fast。
  - MUST RunSpec 中最终写入的字段必须是 `policy_id`；输入侧的 path/alias/ref 只能进入 resolution_trace（诊断用途），MUST NOT 进入 options_hash（3.19.2）或任何 *_hash 输入（0.1.2/3.5.1）。
- SHOULD doctor/stats 输出可见的 PolicyRegistry：列举可用 policy_id 与其来源 ref（artifact_ref 或源文件 ref），用于审计；但任何门控必须只基于 `policy_id` 与其可解析内容（7.3/3.19.3）。

#### 3.19.4 并发与发布边界

（防止多进程污染真相库）

- MUST 任何“发布型产物”（manifest/sqlite\_index/dataset/event\_stream/report 等）只允许由**单 writer**写入；多 worker 仅允许产出 append‑only 的不可变结果产物。
- MUST 发布型产物的落地必须可由 digest+counts 证明幂等；否则视为并发写入风险并拒绝运行。

禁止：

- 任何入口 **MUST NOT** 绕过 RunSpec 直接触发 pipeline 执行；绕过视为架构违规。
- 任何入口 **MUST NOT** 通过“临时命令行参数/脚本常量”改变运行语义而不进入 RunSpec（从而不影响 options\_hash）。

### 3.20 ProfileSpec Contract

Anchor ID: Protocol.ProfileSpec

**定义：**ProfileSpec 是“实现细节参数”的唯一收敛容器；CLI 只允许选择 profile\_id，不允许把 ProfileSpec 内部字段再暴露为独立 CLI 参数。

硬约束：

- ProfileSpec **MUST** 可版本化/可哈希并产出 profile\_id；profile\_id **MUST** 纳入 RunSpec 的 options\_hash（3.19），并进入 Provenance（3.5）与 CacheKey（3.7）。
- ProfileSpec **MUST** 可被 schema 校验；校验失败 **MUST** 拒绝运行（由 doctor/gates 执行）。

禁止：

- CLI **MUST NOT** 提供与 ProfileSpec 内部字段一一对应的 flags（避免参数爆炸与口径漂移）。
- 任意模块 **MUST NOT** 私自解释 profile 名称/含义；只能引用 profile\_id 与其权威加载机制。

#### 3.20.1 ProfileSpec 的注册、载入与可复现约束（Normative）

- MUST ProfileSpec 的唯一权威语义为 3.20 本节内容；ProfileSpec 的任意“文件/目录/别名”仅为载入入口，不得成为第二真相源（见 0.1.2）。
- MUST `profile_id = hash(canonicalized ProfileSpec)`，遵循 3.5.1；运行语义闭包中只允许出现 `profile_id`（见 3.19.2），不得以路径/别名/“latest”替代。
- MUST 若系统支持从文件载入 ProfileSpec（例如 specs/profiles/*.json），则：
  - MUST 载入后先做 schema 校验；失败必须 Fail-Fast（见 3.20）。
  - MUST 对载入内容执行 canonicalization 并计算 `profile_id`；若文件内显式携带 `profile_id` 字段，则 MUST 与计算值一致，否则 strict_mode 下 Fail-Fast。
  - MUST RunSpec 中最终写入的字段必须是 `profile_id`；输入侧的 path/alias/ref 只能进入 resolution_trace（诊断用途），MUST NOT 进入 options_hash（3.19.2）或任何 *_hash 输入（0.1.2/3.5.1）。
- SHOULD 提供一个“ProfileRegistry”（实现细节不限）以列举当前可用 profile_id 与其来源（artifact_ref 或源文件 ref），用于 doctor/stats 的可见性与审计；但任何运行门控必须只基于 `profile_id` 与其可解析内容（7.3/3.20）。

### 3.21 Pipeline CLI Contract

Anchor ID: Protocol.PipelineCLI

**定义：**CLI 是 RunSpec 的薄壳：选择对象（scenario）、选择意图（profile/policy/opponents）、选择可复现性控制（seed/strict），并触发受控 pipeline 动词；CLI **MUST NOT** 成为配置与口径的第二真相源。

动词预算（收敛原则）：

- CLI 顶层动词 MUST 固定为 `stage_id` 受控枚举取值集合（权威锚点：3.19.1 Stage Evidence 最小字段集）；本文不重复列举取值。
- MUST 任何新增能力 MUST 先归入既有 `stage_id`；MUST NOT 发明新的顶层命令作为逃逸口。

参数集（进一步收紧）：

- CLI **MUST** 只接受以下“意图层/可复现层”参数（其余一律禁止）：
  - **对象选择**：--scenario
  - **意图选择**：--profile / --policy / --opponents
  - **可复现控制**：--seed / --strict
  - **可选**：--runspec（直接指定 RunSpec 输入；与 --scenario/--profile/--policy/--opponents 互斥）
- CLI **MUST NOT** 接受任何“执行方式/资源调度/断点续跑/日志粒度/性能分析”等参数（例如 workers/resume/log-level/profiling 等）。
- 若需要并行/断点/分布式等执行方式，**MUST** 通过 ProfileSpec（3.20）或 Scenario Package（3.6）的既有配置机制给出，并作为 **execution\_hint** 写入 Run Manifest（3.19）；该 hint **MUST NOT** 改变语义口径。

配置收敛：

- 所有“实现细节参数” **MUST** 进入 ProfileSpec（3.20）或 Scenario Package（3.6），不得以 CLI flag 形式出现。
- 任何改变运行语义的配置变更 **MUST** 体现为 profile\_id / scenario\_id 等 ID/Hash 的变化，并进入 options\_hash（3.19）。

门控与证据链：

- pipeline 的执行在语义层面 **MUST** 等价于：先校验（doctor/gates）后运行；校验失败 **MUST** 拒绝运行（Fail‑Fast）。
- 每次执行 **MUST** 生成/引用 RunSpec（3.19）并写入结构化 Run Manifest；评测输出 **MUST** 遵循 ReportSchema（3.10）。

## 4. 动作生命周期

### 4.2 Proposed→Executed

Anchor ID: Lifecycle.Proposed→Executed

- Policy 产出 ProposedAction（Canonical Action + provenance）。
- Environment MUST 按 3.1.1 执行规范化（canonicalize）→ 合法化（legalize），得到 ExecutedAction。
- MUST 记录 proposed→executed trace（proposed_action, executed_action）。
- MUST 记录 mapping_trace（替换原因、误差、lossy/fallback_policy、是否 kind_override、是否 snap/clamp）。
- MUST ExecutedAction 必须属于该 DecisionPoint 的合法候选集合（3.11.2）；若不属于：strict_mode 下 MUST Fail-Fast。
- MUST 任意降级/替换均需同时满足：
  - 事件流可回放定位（5.1.1）；
  - Stage Evidence 标记 degraded=true 且给出 degraded_reason 与 evidence_ref（3.19.1/6.2）；
  - 其语义闭包已进入 action_adapter_id / mapping_spec_id 与 options_hash（3.12/3.13/3.19.2）。

#### 4.2.1 MappingTrace 最小字段闭包（Normative）

> 目的：让任何 proposed→executed 的差异都能被机器判定与回放定位；MappingTrace 的**唯一权威定义**在 3.13.1，本节仅声明在生命周期中的使用约束。

- MUST mapping_trace 的 schema/字段闭包/受控枚举取值集合以 3.13.1 为准；本文档其他章节 MUST NOT 再定义/重列取值集合（0.4.1）。
- MUST 任一 proposed_action != executed_action 的 ActionChosen 都 MUST 携带 mapping_trace（4.2/5.1）。
- MUST strict_mode 下，缺失 mapping_trace 或不满足 3.13.1 的最小字段闭包即 MUST Fail-Fast，并按 6.2 输出最小证据闭包。

### 4.3 Lossy 映射显式化

- MUST 让评估层可回答：动作为何被替换、概率如何被裁剪、触发条件是什么。

---

## 5. 事件溯源与证据链

### 5.1 Event Model

Anchor ID: Events.EventModel

- MUST 每手牌形成不可变事件序列；统计/评估只允许由 EventStream 派生（3.9/3.10/5.1.1）。
- MUST 事件模型为受控 schema；其版本指纹为 `event_model_id`（5.1.1）。
- MUST 每手牌至少包含下列最小事件族（允许实现拆分/合并事件，但语义字段闭包 MUST 可回放等价）：
  - HandStart：至少包含 {hand_id, hand_seq, button_seat, seats_in_hand, ruleset_id, triad, schema_hash, options_hash, provenance_ref}。
    - MUST hand_seq 为 run 内单调递增 int（用于 button_rotation 审计；不得依赖文件顺序/隐式索引）。
    - MUST button_seat 为该手牌按钮位置的 seat id（int）。
    - MUST seats_in_hand 为去重后的 seat id(int) 列表，并按 seat id 升序排序；strict_mode 下任一重复/非升序/域外 seat 值 MUST Fail-Fast；用于 forced_bets/button_rotation 审计与回放一致性。
  - ForcedBets：盲注/前注/死钱等强制投入；至少包含 {kind, by_seat_amount_chips}。
    - MUST kind 为受控枚举；唯一允许取值：sb | bb | ante | straddle | dead。新增取值视为 Define（0.4）；strict_mode 下出现未登记取值即 Fail-Fast。
    - MUST by_seat_amount_chips 为 seat→amount 的映射；key MUST 为 seat id 的十进制字符串（无前导 0）；value MUST 为非负 int(chips)。
    - MUST by_seat_amount_chips 只包含 amount_chips>0 的 seat；不得出现 0 值；空对象 strict_mode 下 MUST Fail-Fast（用“缺失该 kind 的 ForcedBets 事件”表达无该类强制投入）。
    - SHOULD 若平台存在额外强制投入类型（例如 bring-in），应以新增 kind 的 Define 方式加入，并确保 ruleset_id 与 RuleConformanceReport 可审计。
  - DecisionPoint：至少包含 {decision_id（hand 内单调递增）, state_hash, legal_actions_digest, snapshot_payload, observation_view_payload}。
    - MUST snapshot_payload **MUST** 采用**方案 A（inline）**：inline SnapshotMinFields（字段闭包必须至少覆盖 3.11.1 的最小事实字段集）。
  - 说明：方案 B（{snapshot_ref, snapshot_digest}）如未来因体积/存储需要引入，必须走 0.4 的 **Define**，并显式 bump `event_model_id`（5.1.1），否则视为绕开本契约并 Fail-Fast。
- MUST observation_view_payload **MUST** 采用**inline ObservationView（3.8）**。
  - 说明：方案 B（{observation_ref, observation_digest}）同上；若启用，除满足“ref+digest 可回放且 digest 校验通过”外，还必须保证 `observation_digest == Snapshot.observation_digest`（3.11.1），并走 Define + bump `event_model_id`。
    - MUST 若 observation_view_payload 选择方案 B，则其 observation_digest MUST == Snapshot.observation_digest（3.11.1）；若选择方案 A，则 Environment 仍 MUST 按 3.5.1 计算同一 digest 并填入 Snapshot.observation_digest（用于 state_hash 去重与缓存闭包）。
    - strict_mode 下，若提供 digest 但缺失对应 *_ref（导致无法回放），则 MUST Fail-Fast。

  - ActionChosen：至少包含 {decision_id, state_hash, action_source_id, proposed_action, executed_action, mapping_trace, derived_action, routing, belief_spec_id, belief_digest, mw_risk_spec_id}。
    - MUST proposed_action / executed_action 为 Canonical Action（3.1）。
    - MUST mapping_trace 遵循 3.13.1 的最小字段集；若发生 kind_override/rounding/fallback，mapping_trace MUST 以 reason_code/fallback_mode/delta_target_total_commit_chips 体现。
    - MUST strict_mode 下缺失 mapping_trace（或 trace_schema_id 不匹配）即 MUST Fail-Fast，并按 6.2 输出最小证据闭包。
    - MUST derived_action 为 Environment 派生的动作分类闭包（见 3.9.1），至少包含：{kind, is_allin, target_total_commit_chips}。
    - MUST strict_mode 下若缺失 derived_action，则该 hand 的事件流视为不可用于统计/评测，且 MUST Fail-Fast，并按 6.2 输出最小证据闭包。
    - MUST 若 Snapshot.players_alive_count>=3，则 MUST 附带 routing：{mw_ladder_id, rung_id, mw_context_digest}（定义见 3.18）。
    - MUST 若启用 belief，则 MUST 附带 {belief_spec_id, belief_digest}（3.8.1）；未启用则字段 MUST 为 null（0.1.3）。
    - MUST 若启用 mw_risk，则 MUST 附带 {mw_risk_spec_id}（7.7）；未启用则字段 MUST 为 null（0.1.3）。

  - StreetDealt：至少包含 {street}。
    - MUST 当且仅当该 street 的公共牌被发出时，Environment MUST 追加该事件；包括“提前 all-in 后直接 runout 无后续决策点”的情况。
    - MUST `street` 为受控枚举 Street（见 3.11.1.1）；本事件仅用于“公共牌是否发出”的可回放事实，不承载牌面细节（牌面可选地由其他 artifact_ref 表达）。
    - MUST no_flop_no_drop（3.2）与 RuleConformanceReport（3.10.1）对“是否发出 flop”的判定，唯一以 `StreetDealt{street:"FLOP"}` 的存在性为准；禁止以“是否出现 flop 决策点”替代（避免 all-in runout 误判）。

  - PotUpdate：至少包含 {pot_chips_delta, rake_chips_delta}（若适用）。
    - MUST pot_chips_delta：只表示“玩家/桌面资金流”对 pot 的影响（下注/跟注为正；派奖/退回为负）；MUST NOT 把 rake 计入 pot_chips_delta。
    - MUST rake_chips_delta：只表示“从 pot 抽走的 rake”（非负 int）；单手内所有 rake_chips_delta 之和 MUST == HandEnd.total_rake_chips（6.1.1）。
    - MUST pot 的更新口径唯一为：pot_next = pot_prev + pot_chips_delta - rake_chips_delta（用于回放对账；避免 double-count）。
  - HandEnd：至少包含 {initial_stacks_by_seat, final_stacks_by_seat, stack_deltas_by_seat, total_rake_chips, rake_base_pot_chips, invariants_ok}；失败时 MUST 给出 evidence_ref（6.2/5.1.1）。
    - MUST initial_stacks_by_seat / final_stacks_by_seat / stack_deltas_by_seat 满足 6.1.1 的定义与守恒不变量；缺失即视为不可审计。
    - MUST rake_base_pot_chips 为本手用于 RuleSet.rake 计算的唯一 pot 基数（3.2.1）；其值必须与 PotUpdate.rake_chips_delta 的累积效果可对账（6.1.1）。
    - SHOULD forced_bets_total_by_seat（blinds/ante/straddle 的总计，用于快速定位 forced 口径漂移；见 6.1.1）。

- MUST action_source_id 为受控枚举；其取值集合仅在本锚点声明：system_policy / opponent_policy / solver / gate / baseline_random。

规则：
- MUST 回放与聚合必须以 EventStream artifact 的 append 顺序作为 hand 内事件排序的唯一准则；若 EventStream 同时包含显式序号字段（例如 `event_seq`），则该字段 MUST 与 append 顺序一致且在 hand 内单调递增；strict_mode 下若无法确定唯一顺序则 MUST Fail-Fast。

#### 5.1.1 EventStream 作为唯一证据链产物

Anchor ID: Events.EventStreamArtifact

- MUST `event_model_id = hash(canonicalized event schema)` 并遵循 3.5.1；Event schema 变更必须走 0.4 的 Define/Refine，并更新 `event_model_id`。

- MUST 每次 run 产出可持久化的 EventStream artifact（或等价分片）；其头部 MUST 包含：
  - run_id
  - options_hash
  - seed
  - scenario_id
  - schema_hash
  - event_model_id
  - event_stream_digest
  - provenance_ref
  - resolved_paths_digest
  - repro_tier（3.5.2）

- MUST event_stream_digest 的唯一计算规则：
  - event_stream_digest 形态为 {alg, hex}，其中 alg MUST 为 "sha256"。
  - 摘要输入为 canonicalized EventStream payload：将 header 记录与后续事件记录按 append 顺序编码为 NDJSON（每行一个 JSON 对象）。
  - 每行 JSON 对象的 canonicalization MUST 遵循 3.5.1（对象键排序、UTF-8、无 float、数组顺序保持）与 0.1.3（null 约定）。
  - `event_stream_digest` 字段本身 MUST NOT 参与摘要输入（避免自引用）。
  - 行分隔符 MUST 固定为 LF（\n，字节 0x0A）；strict_mode 下若发现 CRLF（\r\n）或混入空白行/尾随空格导致语义不确定，则 MUST Fail-Fast。
  - 若 EventStream 分片（shards），则每片 MUST 计算 shard_digest（同上规则）；run 级 event_stream_digest = sha256(canonicalized [{shard_ref, shard_digest}...] 按 shard_order 的稳定列表)。

- MUST EventStream 为 append-only；任何裁剪/采样 MUST 生成新 artifact，并携带新的 digest 与 provenance_ref；MUST NOT 原地修改。

- MUST event_stream_ref / shard_ref 为稳定定位符（artifact_ref），用于报告/失败证据/回放入口的唯一引用：
  - MUST 形态遵循 3.19.1 的 artifact_ref 前缀约定：run:// / artifact:// / path:。
  - SHOULD 优先使用 artifact://{sha256hex}（与对应 digest 一致）作为跨机可移植引用；若使用 path:，必须为相对引用且只能通过 ResolvedPaths 解析，且 MUST 同时携带 resolved_paths_digest（3.6.1）。
  - MUST 任一消费方在加载 event_stream_ref 后校验其 digest（event_stream_digest 或 shard_digest）；不匹配即 Fail-Fast。
  - MUST shard_ref 在 run 内必须可稳定排序（优先使用 shard_index:int；否则以 shard_ref 字典序），并与 event_stream_digest 的 shard_order 一致。

- MUST hand_selector 为机器可解析对象，用于 replay 精确定位：
  - 最小：{hand_id}
  - 可选增强：{hand_id, decision_id:null|int, state_hash:null|string, event_seq_range:null|object}
  - strict_mode 下若 selector 旨在定位某个 DecisionPoint/ActionChosen，则 MUST 同时提供 decision_id 与 state_hash（6.2/3.11.1）。

- MUST 提供唯一回放入口 replay：输入 {event_stream_ref, hand_selector} 输出逐事件视图；用于定位 gate/invariant 失败与策略差异。
  - SHOULD 回放/失败输出优先包含：hand_id、decision_id/state_hash、proposed/executed 差异、mapping_trace、routing（若适用）。

- MUST 任何统计/评估只允许消费 EventStream 与其派生 artifact；MUST NOT 从策略中间态或 proposed 直接派生统计（见 0.2/4.2）。

#### 5.1.2 Golden Fixtures（黄金回放样本）作为回归门禁（Normative）

> 目标：把“环境一次做好后永不回退”变成可机器证明的门禁，而不是靠经验与日志猜。

证据来源与范围（回答“CoinPoker 对齐证据来源是否必须”）：

- MUST Golden Fixtures 的**最小必需**是“系统内部对齐”：fixture 以本系统 Environment 生成的 EventStream 为唯一事实源，并通过 replay+doctor+stats 形成回归门禁（本节）。
- MAY 引入“外部平台对齐证据”（例如 CoinPoker 的 HH/导出 EventStream）作为额外审计增强，但这不是 P0 必需；若未提供外部证据，系统仍必须能完成内部一致性闭环并通过所有门禁。
- 若未来启用外部对齐（MAY）：外部证据必须以不可变 artifact（artifact_ref + digest）形式纳入 fixtures，且其解析/载入必须走 PathsConfig/ResolvedPaths，并产出可回放的对齐报告；不得以“网页/手工文件/隐式路径”作为第二真相源。

平台基准绑定（回答“internal fixtures 是否绑定 ruleset_version”）：

- MUST 每个 fixture 明确绑定 `ruleset_id`（3.2.2/3.2.4）与 `event_model_id`/`report_schema_id` 等关键口径指纹；不得仅依赖 label/文件名。
- MUST fixture 的回归门禁判定只基于 digest/ID（ruleset_id/options_hash/event_stream_digest 等），MUST NOT 基于 label/alias/latest（0.1.2）。

- MUST 维护冻结的 Golden Fixtures（不可变产物集）：每个 fixture 至少包含 {event_stream_ref, event_stream_digest, ruleset_id, options_hash, provenance_ref}，并附带期望输出指纹集合。
- MUST fixtures 覆盖至少以下高风险规则维度（其审计结果必须映射到 RuleConformanceReport.checked_items 的受控 token，见 3.10.1）：button_rotation、forced_bets、min_raise、allin_reopen、no_flop_no_drop、rake、ledger_conservation。
- MUST fixtures 还必须包含边界用例（作为上述维度的覆盖样本，而不是新增 checked_items）：sidepot、all-in runout（含无后续决策点的公共牌发出）、rake rounding/cap。

门禁强约束（不可被“临时绕过”）：

- MUST 任意 PR/发布必须跑 replay+doctor+stats：对每个 fixture 的多指纹输出必须完全一致，否则拒绝合并/拒绝发布：
  - event_stream_digest（5.1.1）；
  - rule_conformance.failures_count==0（3.10.1）；
  - ledger invariants_ok==true（6.1/HandEnd.invariants_ok）；
  - SHOULD 额外比对关键 DecisionPoint 片段指纹（state_hash、legal_actions_digest、derived_action）以提升定位精度。
- MUST 若门禁失败，输出必须给出**最先不一致**的 {hand_selector, decision_id/state_hash 或 event_seq} 与字段级 diff，并引用 replay 与最小证据闭包入口（5.1.1/6.2）。

分层与可维护性（避免 fixture 变成负担从而被团队绕开）：

- MUST fixtures 分层维护为三类（同一套门禁，不是三套口径）：
  - rule micro-fixtures：单规则边界（最小事件数、最小手数）；
  - integration fixtures：整手流（多事件协同）；
  - regression pack：线上事故手（永久冻结、禁止删除，只允许追加注释/原因）。
- SHOULD 增补 **Metamorphic/Property fixtures（变形不变量）**：对同一 fixture 的事件流做无损变换（例如：NDJSON 对象键顺序扰动、字段中的 "\\n" 转义与解析往返、不同语言实现对同一结构化对象 round-trip 序列化）后，replay+doctor+stats 的关键输出指纹必须一致；用于捕获 canonicalization/序列化/分片层的隐形漂移。
- SHOULD 提供失败最小化支持：当门禁失败时，工具链应能自动输出“最小失败集合”（例如最先失败的 hand_selector 或最短事件片段），以降低定位成本。

有意变更流程（允许修正 bug/升级模型，但必须显式化、可审计）：

- MUST 当且仅当发生以下任一情况，才允许更新 fixture 的期望指纹：
  - event_model_id / report_schema_id 的显式 bump；
  - Normative 语义修复导致的确定性变化（例如修复 ledger/invariant 或 RuleSet 算法错误）；
  - Contract Kit（3.4.1）的 canonicalizer/hasher 变更（必须伴随 test vectors 变化）。
- MUST 任一次更新期望指纹都必须同时提交：
  - 变更原因（可机器检索的短语 + 人类可读说明）；
  - 受影响的 fixture 列表与受影响的指纹字段集合；
  - 对应的最先不一致定位样本（hand_selector 或事件片段 ref），用于复盘与回归。
- MUST 禁止以“临时关闭门禁/跳过 fixture”方式合并；任何需要临时绕开的需求必须走 0.4 的 Enforce/Refine 并留下 DR（0.5）。

## 6. 账本不变量与 Fail-Fast

### 6.1 Global Invariants

Anchor ID: Ledger.GlobalInvariants

Environment MUST 强制检查：

- 结算守恒：对每手牌，令 `stack_delta[seat] = final_stack - initial_stack`（int chips），则 MUST 满足：
  - `sum(stack_delta_by_seat) + total_rake_chips == 0`（统一口径）。

- pot 闭环：令 pot_balance_delta := Σ_over_PotUpdate(pot_chips_delta - rake_chips_delta)，则 MUST 满足 pot_balance_delta == 0（默认 HandStart pot=0 且 HandEnd pot=0）；违反即视为账本/事件口径漂移并 Fail-Fast。
- stacks 不为负；commit/pot/stack 的更新单调性正确（不得出现“投入回滚/负 pot/负 commit”）。
- to_call 与 commits 一致；Snapshot（3.11.1）的 `to_call_chips` 必须与引擎事实量一致。
- rake 不超过 cap；no-flop-no-drop 等平台规则在对应 RuleSet（3.2）口径下生效正确。
- forced bets/ante 等强制投入与 RuleSet 期望一致；缺失/漂移即 Fail-Fast。

#### 6.1.1 Ledger 记账闭环与可审计字段

Anchor ID: Ledger.LedgerClosure

- MUST 账本口径仅由 Environment 维护与解释（3.11）；其他层 MUST NOT 重算 pot/to_call/sidepot/rake/派奖。

符号约定（必须统一，否则统计与审计必漂移）：

- MUST stack_delta_by_seat[seat] 表示“玩家筹码变化”（盈利为正，亏损为负），单位 chips(int)。
- MUST rake_base_pot_chips（本手用于 rake 计算的唯一 pot 基数；见 3.2.1）。
- MUST total_rake_chips 表示“从桌面抽走的筹码”（非负），单位 chips(int)。

闭环审计字段（每手牌 HandEnd MUST 输出，避免统计层做推断式会计）：

- MUST initial_stacks_by_seat（hand 开始时各 seat 的筹码）
- MUST final_stacks_by_seat（hand 结束时各 seat 的筹码）
- MUST stack_deltas_by_seat（= final - initial）
- MUST total_rake_chips
- SHOULD forced_bets_total_by_seat（blinds/ante/straddle 的总计，用于快速定位 forced 口径漂移）

守恒不变量：

- MUST `sum(stack_deltas_by_seat) + total_rake_chips == 0`（引用 6.1）。
- MUST 若不满足，则 strict_mode 下 Fail-Fast，并按 6.2 输出最小证据闭包（含 event_stream_ref 与 selector）。

### 6.2 失败证据输出

- MUST 任一门控（第 7 章）或不变量（6.1/6.1.1）失败时，系统必须输出可回放的最小证据闭包；不得仅依赖文本日志。
- MUST 最小证据闭包至少包含：
  - run_id
  - options_hash
  - seed（若在生成 EventStream 之前失败，则 seed 仍应来自 RunSpec；若确实不可得则为 null）
  - context：{scenario_id_or_null, ruleset_id_or_null, triad_or_null, schema_hash_or_null}
  - hand_selector_or_null（手内失败必须提供；run 级失败则为 null）
  - decision_id_or_null 与 state_hash_or_null（若旨在定位某个 DecisionPoint/ActionChosen，则二者 MUST 同时非 null；见 5.1.1/3.11.1）
  - event_stream_ref_or_null（或事件片段 artifact_ref）与对应 digest_or_null（若失败发生在 EventStream 产出之前，则允许为 null）
  - proposed/executed 差异与 mapping_trace（若适用；mapping_trace MUST 满足 3.13.1 的最小字段集；old/new 语义由 proposed_action 与 executed_action 字段提供）
  - 触发的 gate/invariant 标识与失败原因（机器可解析）
- MUST 失败证据必须可由 replay 入口（5.1.1）在同一 options_hash 闭包下复现并定位。
- MUST strict_mode=true 时，任何缺失上述证据字段的失败输出视为二次失败（Fail-Fast）。

## 7. 一致性门控与近似护栏

### 7.1 Triad Gate

- MUST triad（3.3）不一致拒绝训练/加载/编译/运行；不得以默认值绕过。
- MUST triad 的一致性检查必须包含派生一致性：
  - MUST 校验 `triad.rake_id == ruleset_rake_id`（见 3.3 对 `ruleset_rake_id` 的定义与输入闭包）。
  - 若不一致，则即使 triad 的其他字段一致，也 MUST 视为 triad 不一致并 Fail-Fast。
- MUST 拒绝时输出（机器可解析）：
  - triad（observed）
  - ruleset_id（observed）与 ruleset_rake_id（expected）
  - schema_hash、scenario_id、options_hash
  - evidence_ref（6.2；可回放定位到具体 hand/decision 或 run 级别 gate）

### 7.2 Schema Gate

- MUST schema_hash（3.4）不一致拒绝训练/加载/编译/运行。
- MUST Schema Gate 以及任何 schema 校验/hash 计算路径必须使用 Contract Kit 生成的 validator/canonicalizer/hasher（3.4.1）；禁止使用自定义序列化或手工 hash。
- MUST 拒绝时输出：期望 schema_hash 与实际 schema_hash、options_hash、evidence_ref（6.2）。

### 7.3 Provenance Gate

- MUST 缺失关键 Provenance 字段的产物不可用；缺失即拒绝加载/拒绝读缓存（3.5）。
- MUST 至少包含：ruleset_id、triad、schema_hash、options_hash、seed、runtime_env_id；以及（若适用）engine_build_id/solver_build_id/pokerkit_version。
- MUST provenance_ref 必须可解析到不可变内容哈希闭包；仅有 label/路径而无 digest 视为不可用。

### 7.4 Scenario Gate

- MUST 运行前加载并校验 Scenario Package（3.6）与 ResolvedPaths（3.6.1），并将 `resolved_paths_digest` 写入 Run Manifest（3.19.1）与 EventStream 头部（5.1.1）；缺失或权限失败 MUST Fail-Fast。
- MUST 场景选择必须是确定函数（Deterministic Resolution）：给定 `{requested_scenario_ref, paths_config, strict_mode}` 的解析结果必须唯一，且必须产出可回放的 resolution_trace。
- MUST “latest/别名”解析只允许在同一 `scenario_family_key`（Protocol.ScenarioFamilyKey；见 3.6 的定义）内移动；任意跨 family 漂移、歧义解析（多候选）、或解析依赖隐式默认值，均 MUST Fail-Fast。
- MUST 若 Scenario Package 中声明的 `ruleset_id/triad/schema_hash/abstraction_hash` 与当前 RunSpec 语义闭包（3.19.2）不一致，则 MUST Fail-Fast；不得以“尽量运行”方式静默替换或降级。
- MUST Fail-Fast 时输出（机器可解析）：
  - requested_scenario_ref（原始输入）
  - resolved_or_null：{scenario_id, scenario_family_key}
  - candidates_or_null：候选集合（若因歧义失败）
  - reason（受控短语；例如 ambiguous, cross_family_drift, missing_ref, permission_denied, mismatch, other）
  - schema_hash、triad、ruleset_id、options_hash
  - resolved_paths_digest
  - evidence_ref（6.2；必须可由 replay 或等价入口定位到解析失败的证据）

### 7.5 Cache Correctness Gate

- MUST CacheKey 遵循 3.7；任何命中必须可追溯到 {state_hash, scenario_id, schema_hash, engine_build_id, options_hash} 的闭包。
- MUST 读缓存前校验：缓存条目 provenance_ref 与当前 run 的 options_hash/schema_hash/triad/ruleset_id 一致；不一致即视为幽灵缓存并 Fail-Fast。

### 7.6 Leakage Gate

- MUST FeatureEncoder/Policy/System/Opponent 等任何 PlayerAgent 只能使用 ObservationView（3.8）与 Snapshot 摘要（3.11）；MUST NOT 读取不可见信息或引擎内部 state。
- MUST 训练数据必须由 EventStream 回放生成同构 ObservationView；发现信息泄漏即拒绝训练/拒绝评测并输出 evidence_ref（6.2）。

### 7.7 MW Assumption + Guard

Anchor ID: Gates.MWAssumptionGuard

- MUST mw_risk_spec_id 用于标识 MW 风险塑形/惩罚闭包（内容哈希，遵循 3.5.1）；当某 rung 在 dependency_ids 中声明该依赖时，mw_risk_spec_id MUST 进入 options_hash（3.19.2）并在 ActionChosen 中可回放（5.1）。
- MUST 当所选 MW rung 声明依赖 belief_spec_id（3.8.1）或 mw_risk_spec_id，但运行时缺失/不可用（由门控或 guard 判定）时，guard_triggered MUST 为 true，并按 3.18 的 downgrade_policy 单向降级到更保守 rung（或 failsafe / Fail-Fast）。
  - MUST 事件流记录：mw_context_digest、guard_triggered、guard_reason，并保留 proposed→executed trace（4.2/5.1）。
- MUST 将“近似假设 + 护栏规则”收敛为单一契约对象 MWAssumptionGuardSpec，并分配 assumption_guard_id（内容哈希，遵循 3.5.1）。
  - Assumption：适用范围、目标与风险模型（声明性，不含算法细节）。
  - Guard：触发条件与降级动作（保守/推向 HU/弃牌等）。
- MUST 除 baseline/failsafe 外，任何 MW rung 的 assumption_guard_id 必须存在且可解析；缺失即 Fail-Fast（见 3.18）。

### 7.8 Opponent Suite Gate

Anchor ID: Gates.OpponentSuiteGate

- MUST 运行前校验：Scenario Package 已声明 opponent_suite_id 与 population_id（3.16/3.15）；缺失即拒绝运行。
- MUST 若 suite 需要校准（3.17），则 opponent_artifact_id（或 params_hash）必须存在，且其 Provenance 与当前 ScenarioID/triad/schema_hash 一致；否则拒绝运行。
- MUST 在 HandStart/Run Provenance 中记录 opponent_suite_id 与 opponent_artifact_id（或 params_hash），使评测结果可复现且可归因。

## 8. 目录结构建议（Informative）

> 本章为 Informative：用于表达边界与依赖方向；MUST NOT 引入新口径/新定义/新枚举取值集合。

- SHOULD 代码与包结构体现 2.x 分层边界：Protocol / Environment / Engines / Policy / Data / Evaluation。
- MUST 任何跨层依赖只允许向下或同层 Adapter；MUST NOT 出现上层写入下层状态。

- MAY 采用如下目录结构（示例，仅用于导航；括号内为对应权威锚点的“落点提醒”）：
  - schema/  （单一 schema 源；对应 3.4.1 Contract Kit 的 schema-first 要求）
  - contract_kit/  （生成器 + validator/canonicalizer/hasher；对应 3.4.1；运行时与工具链不得各自实现）
  - protocol/
  - environment/
    - gates/  （门控实现的集中位置；对应第 7 章各 Gate）
    - invariants/  （账本/一致性不变量的集中位置；对应第 6 章）
  - engines/
    - hu/
    - mw/
      - micro3/
      - reducer4p/
  - policy/
    - system/
    - opponents/
  - data/
    - preflop_db/
    - postflop_library/
    - model_registry/
    - caches/
  - evaluation/
  - tools/  （doctor/replay/stats/diff/minimize 等只读工具；与 evaluation/ 保持“工具 vs 逻辑”边界）
  - tests/
    - contract_vectors/  （Contract Kit 跨语言一致性 Test Vectors；对应 3.4.1）
    - golden_fixtures/  （冻结回放样本；对应 5.1.2）
  - cli/
  - specs/  （可选：人类可读的契约对象“源文件”目录；也可命名为 conf/。语义以 3.x 权威锚点为准，且路径/别名 MUST NOT 进入 options_hash）
    - SHOULD 只保留一个“源文件根”（specs/ 或 conf/ 二选一）；若两者并存，建议用符号链接或镜像保持内容一致，避免出现两套 registry。
    - SHOULD profiles/policies/scenarios/opponents 均以 *_id 为唯一入口（3.6/3.19/3.20/3.16）；文件路径仅作为载入入口与 resolution_trace（诊断用途）。
    - profiles/  （ProfileSpec 源文件；见 3.20/3.20.1）
    - policies/   （PolicySpec 源文件；见 3.19.3）
    - scenarios/  （Scenario Package/别名源文件；见 3.6/7.4）
    - opponents/  （OpponentSuite/Population/Profile 源文件；见 3.14–3.17/7.8）


## 9. 实战高 ROI 改进点（Operational）

> 本章为 Operational：MUST 仅引用第 3–7 章权威锚点，不引入新口径/新枚举/新执行语义。

### 9.2 Postflop / MW 提强建议

#### 9.2.1 Postflop Solved Spot Library（离线库 + 在线检索）

目标：将 HU re-solve 的常见局面从“在线现解”收敛为“离线产物 + 在线检索/热启动”，以降低延迟并提高一致性。

核心引擎（约束性描述，非算法细节）：
- **HU solver**：用于 HU 局面在线 re-solve / 校准基线输出；
- **postflop-solver**：用于离线 solved spot 生成 + 在线未命中时的现解/热启动。
- 上述两者的版本指纹必须进入 provenance/options_hash（3.5/3.19.2），其离线/在线产物必须以 digest 形式被引用（3.6/3.19.3/7.3）。

落点与约束（引用：3.6 Scenario Package，3.7 CacheKey，3.19 RunSpec/Stage Evidence，3.19.3 PolicySpec，4.2 Proposed→Executed，5.1/5.1.1 EventStream）：

- MUST 离线库产物以不可变 artifact 形式发布，并携带 digest + provenance：
  - MUST 在 Run Manifest 的 Stage Evidence（3.19.1）中以 `outputs_summary` 记录该库的 `artifact_kind`（MUST 为 3.19.1 所列受控枚举合法值）、`artifact_ref`、`digest`、`counts`、`provenance_ref`；不得缺省。
  - MUST 离线库产物的 provenance 满足 3.5（Protocol.ProvenanceEnvelope）；缺失视为不可用（7.3）。
  - MUST 发布型产物遵守单 writer 与幂等可证（3.19.4）。

- MUST 场景绑定与路径约束遵守 Scenario Package（3.6）：
  - MUST Scenario Package 通过 `postflop_ref`（3.6）引用离线库版本（相对引用）；MUST NOT 持久化绝对宿主路径（3.6）。
  - MUST 运行时仅由 PathsConfig/ResolvedPaths 解析外部路径并写入 `resolved_paths_digest`（3.6.1）；缺失即 Fail-Fast。

- MUST 在线检索/热启动的语义闭包进入 PolicySpec 与 options_hash：
  - MUST PolicySpec（3.19.3）将离线库相关依赖写入 `policy_deps`（`artifact_ref` + `digest`）。
  - MUST PolicySpec 的 `policy_params_digest`（或 RunSpec 的 `adaptation_digest`，若启用适配）覆盖所有会改变检索/匹配/回退语义的配置闭包（例如：特征选择、距离度量与阈值、k 值、回退策略、热启动策略），并按 3.5.1 规范序列化。
  - MUST 上述 digest 进入 `options_hash`（3.19.2），并随 `options_hash` 写入 Provenance（3.5）、Run Manifest（3.19.1）、CacheKey（3.7）与报告头（3.10）；缺失即拒绝运行/拒绝读缓存。

- MUST 检索键与可复现性：
  - MUST 在线检索的主键至少包含 DecisionPoint 的 `state_hash`（3.11.1）；若使用 `state_hash` 的确定性投影作为键，则该投影规则 MUST 被 `policy_params_digest`/`adaptation_digest` 覆盖并进入 `options_hash`（3.19.2）。
  - MUST 所有参与 hash/digest 的输入遵守 3.5.1（Canonicalization）；所有执行口径数值一律为 int(chips)。

- MUST 运行证据与降级显式化：
  - MUST 对“命中库直接出策略 / 未命中触发 re-solve / 依赖缺失触发回退”等路径，在 Stage Evidence（3.19.1）的 `counts` 与 `degraded_counts` 中记录客观计数（例如 hits/misses/resolves/fallbacks）；若写入 `degraded_reason`，其取值 MUST 为 3.19.1 所列受控枚举合法值；strict\_mode 下不得假成功。
  - MUST 任何导致决策语义变化的回退与替换遵守 Proposed→Executed 证据链（4.2）与 EventStream 唯一证据链要求（5.1.1）。

#### 9.2.2 BeliefSpec 最小可用版本（多人继续概率/后验摘要）

目标：为 MW 路由与近似策略提供“不过分离谱”的多人后验输入，以降低多家底池的非摊牌损失风险。

落点与约束（权威锚点：3.8.1 BeliefSpec；3.18 MW Ladder；5.1 Event Model）：

- MUST BeliefSpec 的输入仅来自 ObservationView（3.8）与该手可见事件历史；MUST NOT 读取不可见字段或引擎内部 state（7.6）。
- MUST BeliefSpec 产出 belief\_spec\_id 与 belief\_digest，并遵守 3.5.1 的 canonicalization。
- MUST 若某 MW rung 在 dependency\_ids 中声明 belief\_spec\_id，则缺失 belief\_spec\_id 或 belief\_digest 时必须触发门控/护栏并按 downgrade\_policy 单向降级（或 Fail-Fast）（3.8.1/3.18/7.7）。
- MUST ActionChosen 在事件流中记录 belief\_spec\_id 与 belief\_digest（5.1），并使其进入 options\_hash（3.19.2）、CacheKey（3.7）与 Provenance（3.5）。
- MAY BeliefSpec 的实现形态为规则/表/模型；若包含随机性，则 MUST 由 rng\_lineage\_id 可回放（3.5.1）。

#### 9.2.3 mw\_risk\_spec 的“统一风险预算”最小版本

目标：在 MW rung（例如 hu\_isolate/reducer4p）中引入可解释、可回放的风险塑形闭包，使多人场景下的激进行为被可控地压制。

落点与约束（权威锚点：7.7 MW Assumption + Guard；3.18 MW Ladder；5.1 Event Model）：

- MUST mw\_risk\_spec\_id 作为内容哈希（遵守 3.5.1）标识风险塑形闭包；当某 rung 在 dependency\_ids 中声明该依赖时，mw\_risk\_spec\_id MUST 进入 options\_hash（3.19.2），并在 ActionChosen 中可回放（5.1/7.7）。
- MUST 当所选 rung 声明依赖 belief\_spec\_id 或 mw\_risk\_spec\_id，但运行时缺失/不可用时，guard\_triggered MUST 为 true，并按 downgrade\_policy 单向降级到更保守 rung（或 failsafe / Fail-Fast）（7.7/3.18）。
- MUST 将“近似假设 + 护栏规则”收敛为 MWAssumptionGuardSpec，并分配 assumption\_guard\_id（内容哈希，3.5.1）；除 baseline/failsafe 外任何 MW rung 的 assumption\_guard\_id 缺失即 Fail-Fast（7.7/3.18）。

#### 9.2.4 OpponentSuite 分层 + 校准闭环（基准/拟真/压测）

目标：使对手生态“可控强度、可复现、可归因”，并提升定位漏洞与迭代效率。

落点与约束（权威锚点：3.14/3.15/3.16/3.17；7.8 Opponent Suite Gate）：

- MUST OpponentSuiteSpec（3.16）至少支持 baseline / realistic / pressure / exploit 用途分层，且 suite\_id 可版本化/可哈希。
- MUST suite\_id 引用一个 TablePopulationSpec（3.15）及其依赖的 OpponentProfileSpec 集合（3.14）。
- MUST Scenario Package（3.6）指向唯一 suite\_id；MUST NOT 在运行时用散落参数拼装对手（3.16）。
- MUST 若 suite 需要校准，则 CalibrationSpec（3.17）产物携带 Provenance（3.5）并生成 opponent\_artifact\_id（或 params\_hash）；需要校准的 suite MUST 以其为唯一加载输入（3.17）。
- MUST Opponent Suite Gate（7.8）在运行前校验：Scenario Package 已声明 opponent\_suite\_id 与 population\_id；若需校准则 opponent\_artifact\_id（或 params\_hash）存在且其 Provenance 与当前 ScenarioID/triad/schema\_hash 一致；否则拒绝运行。



$1

### 10.0A 高成功率保守方案（推荐默认）

> 目标：**尽可能少的变量**拿到“可跑、可审计、可回归”的闭环；任何提强/多引擎/多人近似都必须在闭环稳定后再逐步引入。
>
> 约束：本节仍属于 Operational；不引入新口径，只约束**推进顺序与默认开关**。

**保守默认开关（建议作为主线默认值）**

- MUST 默认 `strict_mode=true`；任何 `strict_mode=false` 只能用于“定位/对比实验”，其产物 MUST 标记为 degraded 且 MUST NOT 进入回归基线（3.19.1/6.2）。
- MUST 默认 `fallback_policy.mode=fail_fast`；如确需“跑通链路”而暂时容忍输入噪声，只允许 `conservative_check_call`，并且：
  - MUST 记录 proposed→executed + mapping_trace（4.2/3.13.1），并在 Stage Evidence 中标记 degraded=true（3.19.1）。
  - MUST NOT 使用 snap/clamp 这类“近似修复”作为早期默认（3.12.2），避免把口径漂移掩盖成“可运行”。
- MUST 先 HU-only：Scenario 早期 MUST 固定为 `players_alive_count==2` 或强制 `mw_ladder_id=null`（3.6/3.18）；在 Golden Fixtures 全绿之前 MUST NOT 宣称 MW 能力。
- MUST 先 baseline policy：policy_kind MUST 为 baseline 或 rule（3.19.3），且不得依赖外部模型/库（policy_deps 为空或仅依赖冻结的极小产物）。
- MUST 单 ruleset / 单 scenario family：早期只允许一个 `ruleset_id` 与一个 `scenario_family_key`（3.2/3.6.3），避免“同时推进多个平台差异”导致无法定位。
- MUST 单 writer：所有发布型产物（event_stream/report/manifest 等）早期 MUST 单进程写入（3.19.4），并把并发/分布式留到闭环稳定后再引入。

**保守推进纪律（把成功率写成流程）**

- MUST 一次只推进一个“权威锚点闭环”：任何新增/Refine 的对象，必须同时补齐 **语义闭包可哈希 → 至少一个 gate/invariant → fixture/vector**（0.2.1）。
- MUST 先把“可证伪”做硬：任何发现口径不一致/缺证据字段/绕开 EventStream 的统计，必须优先修复为 Fail‑Fast，而不是加更多日志或临时兼容（0.2/5.1.1）。
- SHOULD 把 Golden Fixtures 做到“极小但覆盖高风险”：优先覆盖 checked_items（3.10.1）中的最小集合与边界手（5.1.2），而不是追求大量手数。

**最小可交付闭环（MVP 定义）**

- MUST 满足：Contract Kit 可用（3.4.1） + Minimal Environment（Snapshot/Proposed→Executed/EventStream/Ledger Invariants，3.11/4.2/5.1/6.1） + Doctor/Stats 只读事件流（3.10.1/5.1.1）。
- MUST 在 strict_mode 下对一组最小 Golden Fixtures：replay+doctor+stats 全绿（5.1.2），且 event_stream_digest 可重复对比（至少 Tier‑B；若声明 Tier‑A 则必须一致，3.5.2/5.1.1）。

**退出条件（避免“跑起来就上强度”）**

- MUST 在阶段 C 之前不引入：MW rung（除 baseline/failsafe）、postflop 离线库、任何依赖外部模型/权重的 policy_deps（3.18/9.2.1/3.19.3）。
- MUST 在阶段 D 之前不引入：缓存命中作为“加速主路径”（可以实现，但默认关闭；等 Cache Correctness Gate 全绿后再开启，3.7/7.5）。
- SHOULD 在阶段 E 之后再追求：提强与时延优化；否则极易把“语义不稳”伪装成“性能问题”。

---

### 10.0 建议的 5 阶段落地（含最小退出证据）

#### 阶段 A：Contract‑Kit 先行（先把口径钉死，避免后续返工）
- MUST 先落地 Contract Kit（3.4.1）并打通：schema 校验 + canonicalization + hasher（3.5.1），使所有 *_id/*_hash/*_digest 计算路径统一可用。
- MUST 建立跨语言 Schema/Hash Test Vectors（3.4.1），覆盖 null/枚举/SeatMap/NDJSON 行 canonicalization 等高漂移点。
- 退出证据（最小）：
  - 至少 1 组 test vectors 在各目标语言上输出一致（3.4.1）。
  - Schema Gate（7.2）可在任意入口处 Fail‑Fast（引用 3.4/3.5.1）。

#### 阶段 B：Minimal Environment 闭环（唯一执行 + 账本闭环 + 事件链可回放）
- MUST 优先落地 Environment：唯一执行 + Snapshot（3.11）+ Proposed→Executed（4.2）+ Event Model/EventStream（5.1/5.1.1）。
- MUST 强制 Ledger Invariants（6.1/6.1.1）与 Snapshot/合法动作自检（3.11.3），strict_mode 下 Fail‑Fast。
- 退出证据（最小）：
  - 任意一手牌可产出 event_stream_ref + event_stream_digest（5.1.1）。
  - HandEnd 必含账本闭环字段且 invariants_ok==true（6.1.1）。
  - ActionChosen 必含 mapping_trace（3.13.1）与 derived_action（3.9.1/5.1）。

#### 阶段 C：Evaluation/Doctor 门禁成体系（把“正确”变成可机器证明）
- SHOULD Evaluation 全面切换为“只读 EventStream + MetricsSpec + ReportSchema”（3.9/3.10），禁止从中间态派生统计（0.2）。
- MUST 落地 RuleConformanceReport（3.10.1）并由 doctor/stats 产出；作为线上口径对标的唯一审计产物。
- MUST 引入 Golden Fixtures 回归门禁（5.1.2），至少覆盖 checked_items 的最小集合与关键边界用例。
- 退出证据（最小）：
  - 对最小 fixtures pack：replay+doctor+stats 通过（5.1.2），rule_conformance.failures_count==0（3.10.1），且关键指纹一致（5.1.2）。

#### 阶段 D：主线可用闭环（Policy/CLI/Cache/Opponents 全接入，形成“可跑、可控、可回归”的最小产品）
- MUST 打通 RunSpec/PolicySpec/ProfileSpec 的主线装配：任何一次运行都必须可由 {scenario_id, profile_id, policy_id, opponents} 唯一确定语义闭包，并写入 options_hash（3.19.2）。
- MUST 落地 Pipeline CLI Contract（3.21）：CLI 只负责选择对象与意图（--scenario/--profile/--policy/--opponents/--seed/--strict），不得引入第二配置口径。
- MUST 接入 CacheKey Contract（3.7）与 Cache Correctness Gate（7.5）：保证“命中缓存”与“语义一致”绑定，杜绝幽灵缓存。
- MUST 实现并启用确定性解析/注册：RuleSet / Scenario / Profile / Policy / Opponents 的 source files/alias → *_id 解析必须是确定函数，并把 resolution_trace 写入 Run Manifest（3.2.4/3.6.4/3.19.3.1/3.20.1/3.16.1/7.4/7.8）。
- MUST 实施 Leakage Gate（7.6）：所有 PlayerAgent 只接收 ObservationView（3.8）+ Snapshot 摘要（3.11）；训练数据与评测数据必须由 EventStream 回放生成同构 ObservationView。
- MUST 接入 Opponent Suite（3.14–3.16）与 Opponent Suite Gate（7.8）：让对手生态可复现、可归因；缺失/不一致必须拒绝运行。
- SHOULD 提供一个可跑的 baseline policy（PolicyKind=baseline 或 rule），其目标不是强度而是：**合法、可回放、可审计、可稳定回归**。

退出证据（最小）：
- 至少 1 条端到端路径（init → eval → doctor → stats）在 strict_mode 下全绿：
  - 通过 Triad/Schema/Scenario/Provenance/Cache Gate（7.1/7.2/7.4/7.3/7.5）；
  - 产出 event_stream + report（5.1.1/3.10），且报告头字段齐全（3.10）。
- 确定性解析可证：同一 requested_*_ref 在 strict_mode 下解析结果唯一；歧义/跨 family/缺失依赖均按 Gate Fail‑Fast 且给出 evidence_ref（7.4/7.8/6.2）。
- Leakage Gate 可证：任一训练/评测入口只消费 ObservationView；发现不可见字段读取即 Fail‑Fast，并输出最小证据闭包（7.6/6.2）。
- 同一 {options_hash, seed} 在两次独立执行中可得到可比对的关键指纹（至少 Tier‑B；若声明 Tier‑A，则 event_stream_digest 也必须一致）（3.5.2/5.1.1）。
- 对 Golden Fixtures pack（5.1.2）执行 replay+doctor+stats：规则一致性与账本不变量全通过（3.10.1/6.1）。

#### 阶段 E：基础能力必实现（把第 9 章能力纳入主线）

> 定位：阶段 E 属于**基本功能必实现**的组成部分——系统对外宣称“主线完成”必须完成 A–E。
>
> 约束：阶段 E 仍然 MUST 复用既有权威锚点（第 3–7 章），并满足 0.2.1 的 P0 闭环三件套（语义闭包可哈希 → 至少一个可机器执法点 → fixture/vector 覆盖）。
>
> 守则：E 阶段引入的任何新依赖（库/模型/表/对手参数等）都必须以 `artifact_ref + digest + provenance_ref` 进入 ScenarioPackage/PolicySpec，并最终进入 options_hash（3.19.2）；否则一律视为“不可复现的暗门”并 Fail‑Fast（7.3/7.5）。

E‑0 MW Ladder 最小实现闭环（3.18/7.7/5.1）
- MUST 在 ScenarioPackage 中绑定 mw_ladder_id（若场景允许 MW 路由，3.6），并在 ActionChosen 记录 routing（mw_ladder_id+rung_id+mw_context_digest，5.1）。
- MUST 至少实现官方最小 rung_id 集合中的 baseline / hu_isolate / failsafe 三个 rung（3.18.2），并保证 downgrade_policy 只向更保守 rung 单向降级（3.18.1/7.7）。
- 退出证据（最小）：至少 1 个 MW fixture 覆盖 routing 记录 + guard_triggered 降级路径，可回放定位（5.1.1/6.2）。

E‑1 Postflop Solved Spot Library（9.2.1）
- MUST `solve-postflop` stage 的默认实现以 **postflop-solver** 生成/更新离线库产物；需要 HU re-solve/基线对齐时以 **HU solver** 执行（两者均属于 Engines 层，不得越权执行；3.11/4.2）。
- MUST 离线库通过 ScenarioPackage.postflop_ref（3.6/3.6.2）绑定，并作为 PolicySpec.policy_deps（3.19.3）进入 options_hash（3.19.2）。
- MUST “命中/未命中/回退现解/依赖缺失”路径在 Stage Evidence 的 counts/degraded_counts 中输出客观计数（3.19.1），且任何回退都必须走 Proposed→Executed 证据链（4.2/5.1）。
- 退出证据（最小）：
  - solve-postflop 可产出不可变库产物（digest+provenance，3.5/3.19.1/9.2.1），并可被 init/eval/doctor/stats 路径稳定引用。
  - Golden Fixtures（5.1.2）追加至少 1 个包含 postflop_ref 的回放样本，确保库版本切换只能通过 options_hash 漂移体现，且回放一致性可门禁。

E‑2 BeliefSpec 最小可用（9.2.2）
- MUST BeliefSpec 只消费 ObservationView 与可见事件历史（3.8/3.8.1），并在需要时把 belief_spec_id/belief_digest 写入 ActionChosen（5.1）。
- MUST 当所选 MW rung 声明依赖 belief_spec_id 时：缺失必须触发 guard 并按 downgrade_policy 单向降级（3.18/7.7），不得静默继续。
- 退出证据（最小）：
  - 任一触发依赖的 MW 决策点，其 ActionChosen 必含 {belief_spec_id, belief_digest}（5.1/3.8.1），且 belief_spec_id 在对应条件下进入 options_hash（3.19.2）。
  - 对应路径在 doctor 报告中可见（例如通过 routing_by_rung 与 degraded_counts 观察依赖缺失/guard 触发比例；3.10/3.19.1）。

E‑3 mw_risk_spec 统一风险预算（9.2.3）
- MUST 当所选 MW rung 声明依赖 mw_risk_spec_id 时：该 id 必须进入 options_hash（3.19.2）且在 ActionChosen 中可回放（5.1/7.7）。
- MUST 缺失/不可用时必须触发 guard 并降级到更保守 rung（3.18/7.7）。
- 退出证据（最小）：至少 1 个 MW fixture 覆盖“mw_risk 依赖满足”与“依赖缺失触发降级”两条路径（5.1.2/7.7），回放可定位到具体 {hand_selector, decision_id/state_hash}（5.1.1/6.2）。

E‑4 OpponentSuite 分层 + 校准闭环（9.2.4）
- MUST suite 的“是否需要校准”由 Scenario Package 与 OpponentSuiteSpec/CalibrationSpec 契约对象闭包决定（3.16/3.17/7.8），不得由脚本参数隐式开关。
- MUST 若需要校准：必须提供 opponent_artifact_id_or_params_hash（3.19.2/7.8），且其 Provenance 与当前 ScenarioID/triad/schema_hash 一致（7.8/3.5）。
- 退出证据（最小）：
  - baseline/realistic/pressure/exploit 至少各 1 个 suite 可被确定性解析并运行（3.16/7.8），并在报告头与 provenance 中可归因（3.5/3.10）。
  - 若启用校准：校准产物以既有 artifact_kind 之一发布（例如 model 或 dataset；3.19.1），并通过 Opponent Suite Gate 拒绝“缺校准却强行运行”的情况（7.8）。

阶段 E 的共同门槛（防止“加能力破坏地基”）：
- MUST 任何 E 阶段能力接入后，Golden Fixtures pack 仍必须全绿；若引入新依赖/新闭包字段导致可预期指纹变化，则按 5.1.2 的“有意变更流程”更新期望指纹并提供最先不一致定位样本。

#### 10.0.1 全文能力覆盖核对（章节→阶段映射）
- 阶段 A 覆盖：0.x 文档元契约（ID/Hash/Null/受控枚举治理）+ 3.4.1 Contract Kit + 3.5.1 canonicalization + 跨语言 test vectors（7.2 的 Schema Gate 可执法）。
- 阶段 B 覆盖：Environment 唯一执行与事实边界（3.11）+ Canonicalize/Legalize（3.1.1/4.2）+ Event Model/EventStream（5.1/5.1.1）+ Ledger Invariants（6.1/6.1.1）。
- 阶段 C 覆盖：Evaluation/Doctor 只读 EventStream（3.9/3.10）+ RuleConformanceReport（3.10.1）+ Golden Fixtures 回归门禁（5.1.2）。
- 阶段 D 覆盖：RunSpec/RunID/Stage Evidence/CLI（3.19–3.21）+ PathsConfig/ResolvedPaths（3.6.1）+ CacheKey/Cache Gate（3.7/7.5）+ 确定性解析与注册（3.2.4/3.6.4/3.16.1/3.19.3.1/3.20.1）+ Leakage Gate（7.6）+ Opponent Suite Gate（7.8）。
- 阶段 E 覆盖：MW Ladder 与护栏（3.18/7.7）+ 第 9 章四项能力（postflop library / belief / mw_risk / calibration）并将其全部纳入主线必实现。

结论：在将阶段 E 设为“基本功能必实现”后，全文所有 Normative（第 3–7 章）的 MUST 约束均能在 A–E 中找到明确落点与 DoD；不存在“文档定义但路线未覆盖”的必实现功能。

### 10.1 每阶段最小证据输出（Operational Checklist）

本节的目标是“最小且够用”：不重复 3.19.1/5.1.1/3.10 的字段定义，只规定每个 stage 最少必须交付哪些**不可变产物 + 指纹 + 失败定位入口**。

#### 10.1.1 Run 级通用最小证据（所有 stage 都适用）
- MUST Gate Summary：scenario_id、triad、schema_hash、options_hash、provenance_ref（用于确认语义闭包一致；引用 3.5/3.19.2/7.1/7.2/7.3）。
- MUST Stage Evidence：每个 stage 在 Run Manifest 中记录 inputs/outputs_summary（digest+counts）与 evidence_ref（引用 3.19.1）。
- MUST Fail‑Fast 证据：任何 fail/degraded 必须给出最小证据闭包（6.2），可由 replay 定位（5.1.1）。

#### 10.1.2 按 stage_id 的最小产物与退出门槛（DoD）

| stage_id（3.19.1） | 最小主输出（artifact_kind） | 必须可定位/可比对的指纹 | DoD（最小通过条件） |
| --- | --- | --- | --- |
| init | manifest + runspec + scenario_package | options_hash、resolved_paths_digest、paths_config_id（3.6.1/3.19.2） | 通过 Scenario/Triad/Schema/Provenance Gate（7.4/7.1/7.2/7.3） |
| import-preflop | dataset 或 sqlite_index | 产物 digest+counts + provenance_ref（3.19.1/3.5） | 产物可复现加载（Provenance Gate，7.3），且不引入新口径（只引用 *_id/*_hash） |
| solve-postflop | dataset / chunk / sqlite_index（离线库） | 产物 digest+counts + provenance_ref；policy_deps 绑定（3.19.3/9.2.1） | 产物发布满足单 writer 与幂等可证（3.19.4），且依赖进入 options_hash（3.19.2） |
| train | model | model digest + schema_hash + triad（3.4/3.3/3.5） | Schema/Triad 不一致必须拒绝训练（7.2/7.1）；产物缺失 provenance 必须拒绝（7.3） |
| eval | event_stream + report | event_stream_digest（5.1.1）；report_schema_id + metric_spec_id（3.10/3.9） | 报告头字段齐全（3.10），统计只读 EventStream（5.1.1） |
| doctor | report（含 rule_conformance） | rule_conformance.failures_count（3.10.1）+ evidence_ref（6.2） | strict_mode 下缺失 rule_conformance 视为无效并 Fail‑Fast（3.10.1） |
| stats | report（聚合统计/对比表） | 仅引用 metric_spec_id 与 report_schema_id（3.9/3.10） | 不得在脚本里内联新口径（3.9）；输出可复现定位到 event_stream_ref（5.1.1） |

#### 10.1.3 回归门禁与变更闭环（避免“阶段都跑了但仍反复坏”）
- MUST 当触及任何权威锚点语义（Define/Refine/Enforce）时，同步满足闭环三件套：语义闭包可哈希 → 至少一个可机器执法点 → fixture/vector 覆盖（0.2.1）。
- MUST 当变更影响 canonicalization/hasher/event schema/report schema 时：
  - 更新 Contract Vectors（3.4.1）与/或 Golden Fixtures 期望指纹（5.1.2），并提供最先不一致定位样本（5.1.2/6.2）。

### 10.2 Profile 组合评测的统一做法（Operational）

目标：在不引入“第二配置口径”的前提下，支持多 Profile 组合对比（胜率/风格/稳定性等），并确保每次对比都可复现、可归因。

- SHOULD 将“不同 bot 组合”的比较收敛为一组 RunSpec 的批量执行：
  - 每个候选 bot 组合对应一个独立 RunSpec（3.19），并因此产生独立的 `options_hash`（3.19.2）。
  - 对比时 SHOULD 固定：scenario_id（3.6）、opponent_suite_id（3.16）、policy_id（3.19.3）以及评测预算；仅改变 `profile_id`（3.20）或与之对应的 policy_params_digest（3.19.3）。

- MUST 对比结果的唯一事实来源仍为 EventStream（5.1.1）与结构化报告（3.10）：
  - MUST 每个 run 产出 {event_stream_ref, report_ref}，且报告头包含 {options_hash, scenario_id, schema_hash, metric_spec_id, report_schema_id}（3.10/5.1.1）。
  - SHOULD 以 MetricsSpec（3.9）为统一统计口径输出对比表；不得在对比脚本里内联新口径（3.9）。

- SHOULD 评测“矩阵化”而不引入新契约对象：
  - profile_sweep：固定对手生态与场景，扫描多个 profile_id。
  - opponent_sweep：固定 profile_id，扫描 baseline/realistic/pressure/exploit 等 suite（3.16）。
  - seed_sweep：固定 options_hash 闭包内所有对象，扫描 seed（3.19）。

- NOTE（保守建议）：
  - 若需要把一组 RunSpec 的批量执行“固化成可复用入口”，MAY 将该批量定义为一个**不可变 runspec artifact**（例如 JSON/NDJSON 列表），其内容仅包含：{runspec_ref, runspec_digest, options_hash, seed} 的稳定列表，并计算该 artifact 的 digest。
  - 该批量 artifact 仅用于“分发/审计/复现入口”，MUST NOT 作为门控/缓存的第二真相源：任何 gate/cache 判定仍然只基于每个 RunSpec 自身的 options_hash/seed/provenance（3.19/7.x）。
  - 批量执行工具 SHOULD 在 Run Manifest 的 resolution_trace 里记录 batch_ref + batch_digest，便于追溯“这次 sweep 来自哪份清单”，但 MUST NOT 把 batch_digest 纳入 options_hash（3.19.2）。

### 10.3 变更评审 Checklist（Operational）

> 目标：把 0.4（Define/Refine/Enforce/Restructure）与 0.2.1（三件套闭环）变成日常 review 的最小清单，降低“口径复发”。

- MUST 先定性：本次变更属于 Define / Refine / Enforce / Restructure（0.4，只选其一）。
- MUST 指定权威锚点落点：影响哪个契约对象（0.3），并确保其他章节只引用该锚点。
- MUST 列出影响面：是否改变任一 *_id/*_hash/*_digest / schema_hash / scenario_id / options_hash / cache key（0.4）。
- MUST 同步闭环三件套（0.2.1）：
  - 语义闭包可哈希：对应对象的 canonicalization/hash 输入闭包明确且可计算（3.5.1）。
  - 至少一个可机器执法点：新增/加强 gate 或 invariant 能 Fail‑Fast（第 6–7 章）。
  - 至少一个回归样本覆盖：更新 Golden Fixtures（5.1.2）或 Contract Vectors（3.4.1）。
- MUST 验证可回放定位：失败/差异能落到 {hand_selector, decision_id/state_hash} 并给出 evidence_ref（6.2/5.1.1）。
- SHOULD 写 DR（0.5）：尤其是 Normative 区语义变化、受控枚举新增、事件/报告 schema 变更、或引入新的依赖闭包字段进入 options_hash。

---

## 11. 常见争议口径速答（Informative）

> 本章仅做“口径指向”，不新增任何 Normative 语义；所有回答都指回 3–7 章权威锚点。

- 关于 “internal fixtures 是否绑定 ruleset_version？”：
  - MUST 绑定 ruleset_id（= hash(canonicalized RuleSet)，3.2.2/3.2.4/5.1.2）；任何 ruleset_version/label 只能作为载入入口与展示信息（0.1.2）。

- 关于 “对齐 CoinPoker（或外部平台）证据是否 P0 必需？”：
  - MUST 的最小闭环是“系统内部对齐”：EventStream→replay/doctor/stats→Golden Fixtures 门禁（5.1.2）。
  - MAY 增补外部对齐证据作为增强审计，但其也必须以 artifact_ref + digest 形式纳入（5.1.2/3.6.1）。

- 关于 “run_id 用 UUID 还是内容哈希？”：
  - MUST run_id 为内容寻址：sha256(canonicalized {run_id_schema_id, options_hash, seed})（3.19.0）。
  - MAY 额外记录 run_instance_uuid 区分物理执行实例，但 MUST NOT 进入 options_hash/门控/缓存（3.19.0）。

- 关于 “为什么 legal_actions_digest 不可逆？”：
  - MUST 它只是候选集合指纹，用于一致性对比/缓存键（3.11.2）；可逆集合必须通过 triad.action_bins_id + Snapshot + Adapter/MappingSpec 在 Environment 侧重建验证（3.11.2）。

---

### 12 依赖库和第三方文件位置
- 依赖的开源工具postflop_solver rust 源码地址使用配置注入，在 PathsConfig 的 postflop_solver_src_root='/Users/peng/Workspace/gemini/postflop-solver'  ,通过 python包装器给当前框架交互使用
- hrc导出的翻前表内容 示例位置：/Users/peng/Documents/Hand2  ，包含 settings.json 和 nodes文件夹(里面是 N 个 牌局json 文件), 需要做成可自由配置 hrc 翻前表的位置，并自动解析

## 附录 A. DR 模板（Operational）

---

- DR-ID：
- 摘要：
- 变更类型：Define / Refine / Enforce / Restructure（0.4）
- 权威锚点落点：0.3 中的哪一行（章节号）
- 影响面（列出会变化的指纹）：
  - schema_hash / event_model_id / report_schema_id
  - scenario_id / abstraction_hash / action_adapter_id / mapping_spec_id
  - options_hash / run_id / cache key
- 迁移策略：
  - fixtures/vectors 如何更新（3.4.1/5.1.2）
  - 是否需要 bump 对应 *_schema_id / *_id
- 验证方式：
  - 哪些 gates/invariants 会覆盖（6–7 章）
  - 最小回放定位样本（hand_selector / decision_id / state_hash）

## 附录 B. 指纹与证据字段速查（Informative）

- ruleset_id：hash(canonicalized RuleSet)（3.2.2）
- triad：{action_bins_id, obs_schema_id, rake_id}（3.3）
- schema_hash：训练/推理同构指纹（3.4）
- scenario_id：场景语义闭包指纹（3.6.2）
- abstraction_hash：{action_bins_id, action_adapter_id, mapping_spec_id} 的闭包指纹（3.6）
- options_hash：一次运行语义闭包指纹（3.19.2）
- run_id：sha256({run_id_schema_id, options_hash, seed})（3.19.0）
- state_hash：Snapshot 最小字段集 + digests + ruleset_id/triad/schema_hash（3.11.1）
- event_stream_digest：EventStream NDJSON canonicalization 后 sha256（5.1.1）
- evidence_ref：失败/降级最小可回放定位入口（6.2）

