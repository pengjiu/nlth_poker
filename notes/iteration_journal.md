# 迭代心得与必读规则（请在每次改动前阅读并更新）

> 记录最新的实战经验、失败教训和改进守则。每次改动前先读；每次评测后补充“变化+结论”，形成可追踪的经验库。

## 当前基线（截至 2026-01-12）
- **最可信强度基线**：`scrimmage_coinpoker_2000_league_frozen_v5v`（2000 手，seed=2000/2001，bb/100≈+18.9 均值）。若新改动劣于此，需解释并回滚或再调。

## 最近失败原因（为什么新版本变差）
1) **过度收缩**：多重风险/抑制叠加，预翻防守率≈0.14，翻后 reach≈1%，盲注/前注结构性亏损。  
2) **局部修补破坏全局**：为修 BB flat facing-bet，额外抑制 raise/defend，未守住总防守频率→整体 EV 下降。  
3) **动作空间过粗**：只留 0.5/0.75/1.0/1.5，缺少 0.25/0.33 低成本保护线，OOP/高 rake 风险被放大。  
4) **防守质量弱且频率被压**：OOP 多街价值实现差，且又被抑制频率，双重打击。  
5) **缺少固定回归矩阵**：局部桶改善未经过同矩阵整体回归，导致“头痛医头”式退化。

## 必遵守的改动流程守则
1) **基线对照**：默认以 `v5v` 为基线；改动后必须跑同矩阵（≥2 seeds，same options_hash/opponents/ruleset/actionspace）。  
2) **守恒约束**：防守总频率不得低于基线；动作集合需包含低尺度(0.25/0.33)以保证保护线。  
3) **机制优先，勿硬阈值**：采用 EV/风险一致性或软正则；避免“抑制式”阈值。任何抑制需验证整体 EV。  
4) **统一日志输出**：保留/新增 defend vs price、EV_call_net / EV_raise_net / Δrake、面对下注混合率等结构化键，方便自动对比。  
5) **回归必填总结**：每次评测后在本文件追加一条“改动→结果→下一步”，并注明日期、种子矩阵、bb/100 变化。

## 待办 / 下一步
- 从 v5v 回滚为基线，再按守则迭代；先恢复低尺度动作，再优化 OOP 防守质量（不减频率）。

## 变更日志
- 2026-01-12：新增本文件，记录近期回退原因与守则（assistant 自动生成）。
- 2026-01-12 A/B：基线 v5v vs 当前代码（同 options_hash、seed=2000/2001、2000 手、opponent_suite=system_bot_league_7max_frozen_v1）。v5v bb/100=8.95/28.78（均值≈18.86），当前 bb/100=-4.97/8.78（均值≈1.90），差值≈-16.96 bb/100 → 结论：当前版本显著劣于 v5v，应以 v5v 为回滚基线再迭代。
- 2026-01-12 回滚尝试：移除 bench/抑制改动后重跑同矩阵（seed=2000/2001，2000手）。当前 bb/100=7.34 / 0.67（均值≈4.01），虽优于前一轮，但仍显著弱于 v5v 基线（均值≈18.86）。结论：仍需进一步回到 v5v 行为或重新对齐防守/动作机制。
- 2026-01-12 三种版本对比（同 options_hash、opponent_suite、2000 手；seeds=2000/2001/2002）：  
  - v5v：8.95 / 28.78（均值≈18.86，n=2）  
  - 当前回滚版：7.34 / 0.67 / -8.64（均值≈-0.21，n=3）  
  - 结论：当前仍比 v5v 低约 19 bb/100，且 VPIP≈0.15、flop_reach≈1.3%，显示过度收缩和过度抑制；首要任务是恢复防守/入池频率和低尺度动作，再做机制级修正。
- 2026-01-12 风险约束修订（面对下注加入风险惩罚软 cap，约束 SB/BB 抬升）：  
  - 新 runs：seed=2000 → +6.59 bb/100；seed=2001 → +9.30（均值≈7.94，n=2）。  
  - 对比 v5v 均值 18.86，仍落后 ≈10.9 bb/100；但较前一版均值 -0.21 提升显著。  
  - 仍存问题：VPIP≈0.15，flop_reach≈1.3–1.7%（v5v≈2.9%）；preflop call 仍近乎 0，防守总频率未恢复；翻后少量大额 all-in 依旧出现（单手 -10k/-9k）。下一步需：恢复低尺度防守/跟注线、限制极端 all-in、提高防守覆盖率，再跑同矩阵回归。
- 2026-01-13 防守解限 + ALLIN 再抑制后 5×2000 矩阵（seeds=2000–2004，opponents 同，options_hash 不变）：  
  - bb/100：0.78 / 8.97 / -15.88 / -6.52 / 5.08，均值≈-1.52，std≈8.83，SE≈3.95 → 显著弱于 v5v（18.86）。  
  - VPIP≈0.15，flop_reach≈1.3–1.7%，preflop call 仍≈0；Defense vs Price 0–0.20 桶 defend≈0.46（MDF_adj≈0.84）。  
  - 结论：解限幅度仍不足，且 ALLIN 抑制降低了少量高收益线，整体回报继续低；核心是 defend_target_mix 偏低导致无跟注保护、整体入池过紧。
- 2026-01-13 v5v 对齐尝试（移除 call_ev_cap/raise_equity_scale，缺省 oop_realization_weight=0，保持同场景同 options_hash）：  
  - seeds=2000/2001，bb/100=12.01 / -0.30（均值≈5.86），rake_bb/100≈29.65/34.23，flop_reach≈10%。  
  - 结论：仍明显弱于 v5v（18.86），且翻后进入率与抽水显著更高；仅去除软 cap 不足以恢复 v5v 强度，需继续回溯 preflop/防守机制或找回 v5v 代码快照。
- 2026-01-13 BB/防守混合改动（preflop call/raise 动态地板+天花板，SB/BB 防守不强制；raise_cap 改为与 call_realization 关联）：
  - seeds=2000/2001，bb/100=-2.20 / 4.74（均值≈1.27），明显弱于 v5v（18.86）。
  - BB vs open：call≈0.07，3bet≈0.14（仍低于 v5v≈0.22），BB 总 EV 继续为负。
  - 结论：当前混合机制压低 3bet 且削弱翻后侵略性（cbet 仅≈25–30%），整体回报下滑；需要提高 3bet 频率并恢复翻后进攻覆盖。
- 2026-01-13 处理 postflop solver 的 suggested_action（call/check 不再一律 bet/raise），并完成 5×2000 回归（seeds=2000–2004，同场景同对手同 options_hash）：
  - bb/100：22.14 / -3.90 / 7.68 / -0.70 / -7.99（均值≈3.45，std≈10.67，SE≈4.77）。
  - 对比 v5v 均值 18.86，仍落后 ≈15.4 bb/100；改动虽修复 “过度 cbet” 的 aggressor EV，但整体仍偏弱且波动大。
  - 结论：单点修复不足以恢复 v5v 强度；下一步需回溯 preflop 防守/3bet 强度与翻后行动覆盖，或进一步对齐 v5v 行为基线。
- 2026-01-13 预翻 defend 目标回到 MDF 逻辑（移除 SB/BB 0.45 额外缩放）+ 移除 defend_target_mix 被 call_pct 上限卡死：
  - 5×2000（seeds=2000–2004）bb/100=37.48 / 1.11 / -9.85 / -4.32 / -0.86（均值≈4.71，std≈16.80，SE≈7.51）。
  - 预翻 BB 防守/3bet 有明显上升（BB vs SB open 3bet≈0.18–0.24，flat≈0.08–0.17），但总体仍显著弱于 v5v（18.86），且方差加大。
  - 结论：提高 defend 频率单独不足以恢复强度；下一步需集中修复 BB flat 翻后 OOP 多街亏损（Facing=Y 大幅负）、以及河牌/转牌面对下注的价值实现问题。
- 2026-01-13 默认 OOP realization weight（params 缺省→rake 关联）后 5×2000（seeds=2000–2004）：
  - bb/100=36.19 / -7.05 / -12.47 / -6.66 / -2.56（均值≈1.49，std≈17.63，SE≈7.89）。
  - 结论：缺省 OOP 罚值带来额外抑制，整体均值进一步下滑；与 v5v 差距未收敛。
- 2026-01-13 引入“solver EV 直入 SB/BB 防守混合 + raise 上限由边际收益函数驱动 + OOP cost 在 solver EV 下减权”后 5×2000（seeds=2000–2004）：
  - bb/100=34.39 / -7.05 / -12.47 / -6.66 / -2.56（均值≈1.13，std≈16.93，SE≈7.57）。
  - 结论：改动未带来均值提升，方差仍高；关键弱点仍集中在 BB/SB 翻后与多街价值实现。
- 2026-01-13 预翻 call 保留条件（call_pct>raise_pct 时不移除 CALL）：
  - 5×2000 与上一轮结果完全一致（均值≈1.13），说明该条件未触发；call_share 仍≈0。
  - 结论：问题在于 preflop 混合本身把 call 压到 0，需要从 mix 生成逻辑入手。
- 2026-01-13 预翻 EV 混合再锚定（raise_cap 由 EV 边际生成，call/raise mix 直接由 EV gap 驱动）：
  - 5×2000（seeds=2000–2004）bb/100=34.39 / -7.05 / -12.47 / -6.66 / -2.56（均值≈1.13，std≈16.93，SE≈7.57）。
  - 预翻 BB vs open call 占比提升到 ~0.10–0.14，但 Defense vs Price 0.20–0.33 桶仍仅≈0.22–0.25（MDF_adj≈0.35），总体防守仍偏紧；SB EV 显著为负。
  - 结论：EV 混合锚定带来少量 flat，但仍不足以提升整体强度；核心瓶颈仍在预翻防守总量+翻后 OOP 多街处理（BB flat facing Y 大波动）。
- 2026-01-13 预翻 OOP 成本分离（raise/call 分别计入）+ SB/BB defend_target_pre 直接锚定 + call_scale 改为 EV 驱动：
  - 5×2000（seeds=2000–2004）bb/100=34.10 / -8.84 / -11.72 / -7.88 / -7.12（均值≈-0.29，std≈17.27，SE≈7.72）。
  - BB vs open call% 仍≈0.10–0.14，MDF_adj 0.20–0.33 桶 defend≈0.22–0.25，SB EV 继续偏负；个别 seed 仍出现 BB flat facing Y 极端负桶。
  - 结论：OOP 成本分离 + defend_target 锚定仍不足以恢复 v5v 强度；瓶颈依然在预翻总防守不足与翻后 OOP 多街质量不稳。
- 2026-01-13 BB/SB facing-bet 混合上限改为“边际收益函数”（EV_raise−EV_call−Δrake−oop_cost）+ raise 边际评估强制用 solver_raise_ev（若存在）：
  - 2000 手（seed=2000，same options_hash/opponent_suite/actionspace），bb/100=39.21，与上一版完全一致。
  - BB Flat Postflop EV by Street+Facing（同 seed）无变化：FLOP N=-120.94bb/100, TURN N=-97.00, RIVER N=216.71（样本数相同）。
  - 结论：改动未触发行为变化，推测 solver_raise_ev 未提供或 raise_cap_marginal 与旧 raise_cap 等价；下一步需先验证 solver EV 可用性与 raise_cap 是否实际约束 mix，再谈调优。
- 2026-01-13 日志补强（solver EV 覆盖率 + raise_cap_marginal 命中率）后复跑（seed=2000）：
  - solver_ev_coverage=266/267，raise_cap_marginal_hits=220/267（report: Analysis Table）。
  - BB/SB Facing Bet Edge 显示 raise_cap_marginal 多数大于 raise_cap（如 FLOP 0-0.20：0.262 vs 0.175），说明边际 cap 并未成为有效上限；实际仍由旧 raise_cap/其它约束主导。
  - 结论：需将 raise_cap 的主导权切换为 raise_cap_marginal（或至少优先级更高），否则边际收益上限不会真正作用于 mix。
- 2026-01-13 将 raise_cap 直接切换为 raise_cap_marginal（revert28，5×2000，seeds=2000–2004）：
  - bb/100=24.32 / -27.77 / 11.12 / -32.71 / 6.57（均值≈-3.69，std≈25.16，SE≈11.25）。
  - BB Flat Postflop EV by Street+Facing 仍出现大负桶，整体回报显著弱于 v5v（18.86）。
  - 结论：单纯切换上限导致波动放大且均值下降，边际 cap 仍未解决 OOP 多街亏损。
- 2026-01-13 raise_cap 改为 expected_edge_per_risk 驱动（revert29，5×2000，seeds=2000–2004）：
  - bb/100=49.92 / -30.79 / 2.71 / -31.61 / 10.05（均值≈0.06，std≈33.72，SE≈15.08）。
  - 分布极端：seed=2003 出现 BB Flat Postflop Facing Y 大幅负桶（FLOP/TURN/RIVER 负向显著），seed=2004 同类桶为正。
  - 结论：edge_per_risk 驱动 cap 引入更高方差，强依赖对局分布；核心弱点仍是 BB/SB OOP 多街价值实现不稳。
- 2026-01-13 防守 raise 份额加入 EV-soft cap（ev_raise_share_cap，revert30，5×2000，seeds=2000–2004）：
  - bb/100=49.92 / -30.79 / 2.71 / -31.61 / 10.05（均值≈0.06，std≈33.72，SE≈15.08）。
  - 与 revert29 结果完全一致，说明该 cap 未触发或未改变混合；BB Flat Postflop Facing Y 大负桶仍存在（seed=2003/2004 对照明显）。
  - 结论：当前 raise mix 仍由既有 target_raise/raise_cap 主导；需要更直接影响混合的机制（而非事后 cap）。
- 2026-01-13 防守 raise 目标改为 EV share（ev_raise_share_cap 作为 target_raise，revert31，5×2000，seeds=2000–2004）：
  - bb/100=32.68 / -14.25 / 7.29 / -26.00 / -5.60（均值≈-1.18，std≈22.50，SE≈10.06）。
  - 相比 revert29/30，极端负种子有所缓和，但整体仍显著弱于 v5v（18.86）。
  - 仍见 BB Flat Postflop Facing Y 在部分种子（2001/2003/2004）显著负，说明 OOP 多街价值实现仍不稳。
- 2026-01-13 防守目标引入 EV-based defend_share cap（defend_ev_share：call/raise net EV vs fold 的 softmax，revert32，5×2000，seeds=2000–2004）：
  - bb/100=32.68 / -14.25 / 7.29 / -26.00 / -5.60（均值≈-1.18，std≈22.50，SE≈10.06）。
  - 与 revert31 完全一致（说明当前 defend_target cap 仍未实质改变 mix，需检查 defend_ev_share 是否显著低于 defend_target 或被后续流程覆盖）。
  - 结论：新增 defend_ev_share 机制未生效；下一步应在 defense_trace 中对比 defend_target_ppm vs defend_ev_share_ppm，并检查后续 target_def/weights 是否被 focus_act 分支覆盖。
- 2026-01-13 raise share 进一步受“raise vs call EV 差”约束（target_raise=min(ev_raise_share_cap, raise_pref)，focus_act 同步受限；revert34，5×2000，seeds=2000–2004）：
  - bb/100=33.73 / -14.38 / 1.48 / -18.30 / 9.05（均值≈2.32，std≈20.84，SE≈9.32）。
  - 相比 revert31/32，均值小幅提升，负种子有所收敛，但仍显著低于 v5v（18.86）。
  - 结论：raise-share 约束开始生效但幅度不足；继续聚焦 BB/SB OOP 面对下注的 raise/call 比例与后续街 EV 兑现。
- 2026-01-13 面对下注引入“best_defend_net vs fold”EV gap 上限（defend_ev_cap）以收缩过度防守（revert35，5×2000，seeds=2000–2004）：
  - bb/100=31.17 / -11.44 / 7.73 / -18.60 / 9.53（均值≈3.68，std≈19.57，SE≈8.75）。
  - 与 revert34 相比均值小幅上升，但仍显著弱于 v5v（18.86）。
  - 汇总桶仍显示 BB Flat Facing=Y 在 FLOP/TURN/RIVER 大幅负（≈ -505 / -1099 / -570 bb/100），说明 OOP 多街面对下注的价值兑现仍未恢复。
- 2026-01-13 TURN/RIVER raise/call EV gap 软正则（raise_pref 在 TURN/RIVER 做幂次收缩；revert36，5×2000，seeds=2000–2004）：
  - bb/100=30.26 / -17.98 / 12.70 / -20.24 / 9.44（均值≈2.84，std≈21.56，SE≈9.64）。
  - 相比 revert35 均值略降，但 BB Flat Facing=Y 负桶有所改善：FLOP≈-318、TURN≈-915、RIVER≈-488 bb/100（仍显著为负）。
  - 结论：TURN/RIVER raise/call 正则开始缓和最差桶，但整体强度仍远低于 v5v；需进一步削减 BB/SB OOP 面对下注的过度 raise 与高价位跟注。
- 2026-01-13 TURN/RIVER raise 权重再抑制（raise_bias 叠加更陡 sigmoid；revert37，5×2000，seeds=2000–2004）：
  - bb/100=33.15 / -14.70 / 14.19 / -14.61 / 6.01（均值≈4.81，std≈20.31，SE≈9.08）。
  - 均值较 revert36 上升，但 BB Flat Facing=Y 仍显著负：FLOP≈-481、TURN≈-1121、RIVER≈-428 bb/100。
  - 结论：进一步抑制 raise 后均值回升，但核心 OOP 多街亏损仍在，下一步需直接压缩高价位跟注并强化 turn/river 的 call EV 兑现。
- 2026-01-13 TURN/RIVER call EV gap 软正则（call_pref 用 call_edge_ratio 生成并压缩 CALL 权重；revert38，5×2000，seeds=2000–2004）：
  - bb/100=33.10 / -14.70 / 12.08 / -15.42 / 6.23（均值≈4.26，std≈20.27，SE≈9.07）。
  - 与 revert37 均值略降，BB Flat Facing=Y 汇总未改善（FLOP≈-481、TURN≈-1121、RIVER≈-428 bb/100）。
  - 结论：call_pref 软正则影响不足，需更直接地限制 TURN/RIVER OOP 的“薄跟注”并提高 fold 权重或改进 call EV 估计。
- 2026-01-13 TURN/RIVER call_pref 反向收缩 defend_target（target_def 上限随 call_pref 收紧；revert39，5×2000，seeds=2000–2004）：
  - bb/100=33.31 / -24.22 / 17.62 / -8.61 / 6.23（均值≈4.87，std≈22.37，SE≈10.00）。
  - 汇总桶恶化：BB Flat Facing=Y FLOP≈-572、TURN≈-1108、RIVER≈-966 bb/100。
  - 结论：直接用 call_pref 压缩 defend_target 导致部分样本出现更深的河牌负桶；需回退此收缩方式，改用更细粒度的 OOP call risk 成本。
- 2026-01-13 TURN/RIVER OOP call 风险溢价（call_edge 用 call_ev_ref_call=call_ev_ref−risk_premium；revert43，5×2000，seeds=2000–2004）：
  - bb/100=33.34 / -14.80 / 9.45 / -14.74 / 6.23（均值≈3.90，std≈20.00，SE≈8.94）。
  - BB Flat Facing=Y 改善：FLOP≈-537、TURN≈-1008、RIVER≈-355 bb/100（相比 revert39/38 河牌明显好转）。
  - 结论：OOP call 风险溢价开始压缩薄跟注，河牌负桶缓和，但总体强度仍显著低于 v5v；需继续提升 turn/facing 的 EV 兑现并检查 preflop flat 结构。
- 2026-01-13 FLOP 也引入 OOP call 风险溢价（含 SPR/price/mw 调节；revert44，5×2000，seeds=2000–2004）：
  - bb/100=35.19 / -13.52 / 8.41 / -16.11 / 3.18（均值≈3.43，std≈20.63，SE≈9.23）。
  - BB Flat Facing=Y 继续改善：FLOP≈-403、TURN≈-874、RIVER≈-401 bb/100。
  - 结论：OOP call 风险溢价对 BB Flat Facing=Y 桶有效，但整体均值仍低；下一步需在 preflop flat 结构上减少进入弱 OOP 线。
- 2026-01-13 预翻 call 风险进一步放大（preflop_call_cost 乘 price 因子；revert45，5×2000，seeds=2000–2004）：
  - bb/100=35.19 / -13.52 / 9.64 / -16.11 / 3.18（均值≈3.68，std≈20.71，SE≈9.26）。
  - 与 revert44 基本一致，BB Flat Facing=Y 桶无显著变化（FLOP≈-403、TURN≈-874、RIVER≈-401 bb/100）。
  - 结论：preflop_call_cost 的微调未改变行为；下一步需更直接地改变 preflop flat/3bet 权重结构。
- 2026-01-13 预翻 call_realization 引入 price 折价（revert46，5×2000，seeds=2000–2004）：
  - bb/100=37.14 / -19.16 / 4.59 / -10.73 / 4.88（均值≈3.34，std≈21.51，SE≈9.62）。
  - BB Flat Facing=Y：FLOP≈-526、TURN≈-859、RIVER≈-354 bb/100（turn/river略改善，flop变差）。
  - 结论：preflop call_realization 折价对 turn/river 有些改善，但整体均值仍低；需要更直接的 preflop flat→3bet/ fold 重分配。
- 2026-01-13 预翻 flat→3bet 软迁移（按 raise_net vs call_net EV gap 重新分配；revert47，5×2000，seeds=2000–2004）：
  - bb/100=37.14 / -19.16 / 4.59 / -10.73 / 4.88（均值≈3.34，std≈21.51，SE≈9.62）。
  - BB vs open 分布几乎未变（BU/OTHERS/SB 的 call/3bet 比例稳定），说明迁移强度仍不足或被后续约束覆盖。
  - 结论：EV 迁移未改变实际 mix；需提高迁移强度或调整 call_floor/raise_cap 结构，或直接改动 preflop defend_target_pre 的 call_floor 生成方式。
- 2026-01-13 预翻 call_ceiling 加强（call_ceiling 受 price/edge 进一步压缩；revert52，5×2000，seeds=2000–2004）：
  - bb/100=30.46 / -10.92 / 1.18 / -14.13 / -7.79（均值≈-0.24，std≈18.09，SE≈8.09）。
  - BB vs open：call 明显下降、3bet 上升（BU/OTHERS/SB 的 call≈0.06–0.20，3bet≈0.24–0.32），但整体回报显著下滑。
  - BB Flat Facing=Y 桶恶化（FLOP≈-1167、TURN≈-1369、RIVER≈-521 bb/100，样本减少但质量更差）。
  - 结论：过强压缩 call_ceiling 伤害总体 EV，应回退该改动，改走更平滑的 preflop flat 结构或引入翻前先验。
- 2026-01-14 预翻频率先验调整（preflop_freq_v1：BB call 0.65→0.45 / 3bet 0.20→0.30；SB call 0.35→0.25 / 3bet 0.15→0.20；revert54，5×2000，seeds=2000–2004）：
  - bb/100=51.33 / 6.50 / 26.11 / 15.01 / 12.91（均值≈22.37，std≈17.66，SE≈7.90）。
  - BB Flat Facing=Y（均值，样本小波动大）：FLOP≈+114.64、TURN≈-434.35、RIVER≈-253.33 bb/100。
  - 结论：整体均值首次明显高于 v5v（18.86），但 TURN/RIVER 面对下注仍偏弱且样本稀疏；下一步应在维持 preflop 结构的同时，继续降低 OOP 多街 facing Y 的薄跟注并稳定河牌实现率。
- 2026-01-15 OOP facing 风险成本细分 + solver EV 差绑定（call_risk_premium 加入 price+SPR 平滑分桶；call/raise mix 绑定 solver_raise_ev−solver_call_ev；revert55，5×2000，seeds=2000–2004）：
  - bb/100=51.33 / 7.55 / 24.71 / 12.26 / 11.29（均值≈21.43，std≈17.92，SE≈8.01）。
  - BB Flat Facing=Y（合并均值）：TURN≈-434.35（合并率≈-462.56，95%CI≈±1438.45，hands=27），RIVER≈-253.33（合并率≈-492.46，95%CI≈±1231.23，hands=37）。
  - 结论：总体均值仍高于 v5v，但 TURN/RIVER facing Y 负桶未显著收敛（样本仍少、方差极大）；下一步需继续提高 turn/river 对高 price、深 SPR 的 fold 权重，或加大 call EV 置信修正以压缩薄跟注。
- 2026-01-15 TURN/RIVER call_pref 额外收缩（call_edge_ratio 加 spr/solver gap 调整；call_net_dominated margin 加 price+spr；revert57，5×2000，seeds=2000–2004）：
  - bb/100=38.52 / 8.86 / 24.14 / 12.27 / 12.88（均值≈19.33，std≈12.17，SE≈5.44）。
  - BB Flat Facing=Y（合并均值）：TURN≈-467.32（合并率≈-549.46，95%CI≈±1471.93，hands=28），RIVER≈-344.59（合并率≈-606.00，95%CI≈±1293.52，hands=36）。
  - 结论：均值较 revert55 下滑，且 facing Y 负桶未收敛；应回退本轮加压项，转向更稳定的“面对下注时 raise 权重上限与 call EV 置信度联动”或“preflop BB/SB flat 结构进一步重分配”。
- 2026-01-15 TURN/RIVER defend_target 乘 solver_gap 缩放（defend_target*=0.70+0.30*sigmoid(gap)；revert59，5×2000，seeds=2000–2004）：
  - bb/100=34.73 / 6.78 / 21.64 / 11.89 / 13.96（均值≈17.80，std≈10.87，SE≈4.86）。
  - BB Flat Facing=Y（合并均值）：TURN≈-325.56（合并率≈-529.93，95%CI≈±1671.83，hands=27），RIVER≈-336.35（合并率≈-599.14，95%CI≈±1304.68，hands=36）。
  - 结论：整体回报跌破 v5v（18.86），需回退该缩放；下一步应围绕 raise_cap 与 call EV 置信约束做更小步的局部调优。
- 2026-01-15 预翻频率再次下调（BB call 0.45→0.40 / 3bet 0.30→0.32；SB call 0.25→0.22 / 3bet 0.20→0.22；revert60，5×2000，seeds=2000–2004）：
  - bb/100=50.92 / 7.55 / 24.71 / 8.57 / 11.29（均值≈20.61，std≈18.29，SE≈8.18）。
  - BB Flat Facing=Y：TURN≈-434.35、RIVER≈-253.33（与 revert55 基本一致，合并率≈-462.56/-492.46）。
  - 结论：均值低于 revert55（21.43），且核心 facing Y 未改善；已回退到 revert55 的 preflop 先验。
