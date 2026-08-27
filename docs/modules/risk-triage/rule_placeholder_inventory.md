# 风险研判 · 规则 / 占位清单（T0827-07 收口）

> 负责人：闫昱硕　|　日期：2026-08-27　|　基线代码：`src/sec_agent/services/triage.py`
> 目的：把「研判临时项收口」，明确当前哪些是**正式规则基线**、哪些仍是**固定值 / 经验阈值（占位）**，并特别标出 `VERDICT_CONFIDENCE` 固定档位，为 8/28 真实数据校准做准备。

## 0. 结论先行

第一版研判是「确定性规则评分」基线，代码里每个可调项可归为三类：

| 类别 | 含义 | 处置 |
|---|---|---|
| **A 正式规则基线** | 决定输出如何推导的结构 / 映射契约，与 `TriageResult` 模型对齐、被测试断言 | 保持不变（属契约） |
| **B 固定值 / 经验阈值** | 当前写死的数值，尚未用真实平台数据校准 | 属于占位，需在 8/28 用真实数据校准 |
| **C 缺失 / 未知处理** | 对缺失、未知输入的回退规则；回退值本身是经验性选择 | 回退逻辑属契约，回退值待校准 |

**核心判断：正式规则只有 4 类结构（合成公式、结论映射、置信度档位对应、证据规则）与「非 benign 一律调查」这条不变量；其余所有数值（严重度分、攻击类型分、关联加成、三档置信度、两条阈值）都是待校准占位。**

其中 `VERDICT_CONFIDENCE` 是**纯占位固定档位**：它只按 `verdict` 给一个死值，没有任何推导公式，也不随证据、关联强度、风险分变化。它是 8/28 校准优先级最高的项。

---

## 1. A 类：正式规则基线（结构 / 映射契约）

| # | 规则点 | 代码位置 | 内容 | 是否测试断言 |
|---|---|---|---|---|
| A1 | 合成公式 | `triage()` / `_rule_score()` | `rule_score = max(严重度分) + max(攻击类型分)`；若 `alert_count_before >= 2` 则 `rule_score += 关联加成`；`risk_score = min(100, max(rule_score, seed 或 0))` | 是 |
| A2 | 结论映射 | `_decide()` | `risk_score >= 70` → `malicious / high / 调查`；`40 <= risk_score < 70` → `uncertain / medium / 调查`；`risk_score < 40` → `benign / low / 不调查` | 是 |
| A3 | 置信度档位对应 | `triage()` | `confidence = VERDICT_CONFIDENCE[verdict]`，即 confidence 是 verdict 的函数（档位取值本身属 B 类） | 是 |
| A4 | 证据规则 | `triage()` | `supporting_evidence_refs` = 各告警 `evidence_refs` 的并集；`opposing_evidence_refs` 恒为空；证据缺口：无证据 →「缺少可定位的原始证据引用」，`verdict=uncertain` →「需要补充平台侧日志或上下文」 | 是 |
| A5 | 非良性一律调查 | 结论映射 | `should_investigate = True` 当且仅当 `verdict != benign` | 是 |
| A6 | 缺失 / 未知回退 | `_rule_score()` / `_max_seed()` | 严重度 / 攻击类型未映射 → 计 0 分；`risk_score_seed` 缺失或非 `0~100` 整数 → 不参与 | 是 |

> A1–A6 构成「到底怎么算、怎么划档、怎么给置信度、怎么收集证据、何时进调查」的契约，属于正式规则；改动它们属于改行为，而非校准数值。

---

## 2. B 类：固定值 / 经验阈值（占位，待校准）

| 常量 | 当前取值 | 定义 | 性质 | 8/28 校准方法 |
|---|---|---|---|---|
| 严重度分 `SEVERITY_POINTS` | `critical=60 / high=40 / medium=20 / low=10` | 严重度对风险分的贡献 | 经验权重 | 用真实样例分档重估 |
| 攻击类型分 `ATTACK_TYPE_POINTS` | `webshell=30 / unauthorized_access=25 / sql_injection=20 / lateral_movement=20` | 攻击类型对风险分的贡献 | 经验权重 | 用真实样例分档重估 |
| 关联加成 `CORRELATION_BONUS` | `15` | `alert_count_before >= 2` 时的加分 | 经验值 | 用真实关联样例标定 |
| 高风险阈值 `HIGH_RISK_THRESHOLD` | `70` | 判定 `malicious / high` 的分数界 | 经验阈值 | 用真实正负样例标定 |
| 中风险阈值 `MEDIUM_RISK_THRESHOLD` | `40` | 判定 `uncertain / medium`（需调查）的分数界 | 经验阈值 | 用真实样例标定 |
| **`VERDICT_CONFIDENCE`** | `malicious=0.85 / uncertain=0.65 / benign=0.70` | 结论 → 置信度固定档位 | **纯固定档位占位** | **最优先**：用真实样本 + 人工/平台结论回归校准 |

> `VERDICT_CONFIDENCE` 三个取值没有任何推导依据，属于「拍脑袋占位」。在真实数据进入前，它会让所有 `malicious` 都输出 0.85、所有 `uncertain` 都输出 0.65、所有 `benign` 都输出 0.70，**与证据充分度无关**——这是当前最大的一块「临时项」。

---

## 3. C 类：缺失 / 未知输入处理

| 输入 | 当前行为 | 说明 |
|---|---|---|
| `raw_severity` 未映射（如空串、`"高危"`、`"未知"`、大小写 / 空白差异） | 严重度计 0 分 | 依赖 `AlertRecord` 已标准化为英文等级；真实中文等级会被当成 0 分 |
| `alert_type` 未映射（如 `"other"`、未知值） | 攻击类型计 0 分 | 未映射类型不贡献风险分 |
| `risk_score_seed` 缺失 / 非法（非 int 或越界） | 不参与，`risk_score` 取 `rule_score` | 仅 `0~100` 整数种子分被采纳 |
| `attack_status` / `attack_state`（真实性轴字段） | **未接入** verdict / confidence | 设计稿已定义，但当前三轴合一，`verdict` 由 `risk_score` 阈值代理 |

---

## 4. 待收口临时项（与「收口」直接相关）

1. **两轴分离未落地**：设计稿要求 `verdict`（真实性轴，由证据 / `attack_state` 决定）与 `risk_score`（影响轴）正交；当前代码仍是「单分数 → 结论」，`verdict` 由 `risk_score` 阈值代理，属尚未收口的临时项。
2. **置信度无公式**：`confidence` 是固定档位，不随证据充分度、命中规则数、`attack_state` 变化。
3. **`opposing_evidence_refs` 恒空**：尚无反对证据模型。
4. **模型辅助未接入**：`model_note` 设计允许但未实现，不参与 `verdict / confidence / risk_score`。
5. **`risk_score_seed` 语义**：上游为「平台种子分」，仅当 `0~100` 整数才被采纳；其与规则分的权重关系待真实数据确认。

---

## 5. 下一步（8/28 真实数据）

- 进入真实数据后，按 `calibration_template.md` 逐条记录「原始字段 → 标准化字段 → 当前规则期望输出 → 真实 / 人工结论 → 差异」。
- 优先校准 `VERDICT_CONFIDENCE`，再协同校准 `SEVERITY_POINTS` / `ATTACK_TYPE_POINTS` / `CORRELATION_BONUS` / 两条阈值。
- 任一常量调整后，跑 `pytest tests/test_triage.py tests/test_state_flow.py` 并同步更新 `design.md`、`test.md`。
