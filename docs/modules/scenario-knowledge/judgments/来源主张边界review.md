# 知识卡来源—主张边界 Review（闫昱硕）

> 本文件是 T0905-03 交付物 #3：对沈洪旭提供的知识卡（`src/sec_agent/deep_agent/knowledge/webshell-knowledge.md`）与其来源 URL/等级做结论边界核验，确认“来源能支持到什么程度”，并在此收口来源—主张对应关系。
>
> 评审原则：来源支持“某公开事件曾出现某技术”，不等于支持 synthetic 案例 JSON 里的每个字段；知识包可提供调查方向/启发性特征，但不能把一般规律升级为本事件已发生的事实。

## 1. 知识条目级来源核验

| 知识ID | 关键主张 | 来源 | 来源级别 | 是否直接支持 | 允许表述强度 | 修改意见 |
|---|---|---|---|---|---|---|
| `K-WEBSHELL-PRINCIPLE` | WebShell 是被植入 Web 服务器的恶意脚本，经 HTTP/HTTPS 通信获得与 Web 进程同权限的命令执行能力；常混入 80/443 正常流量；利用上传/RCE/配置错误植入 | MITRE ATT&CK T1505.003 | 官方标准/通用定义 | ✅ 直接支持（通用定义） | 仅用于解释与调查方向，不得用于断言本事件已发生 | 无；保留“通用定义”定位 |
| `K-WEBSHELL-FEATURES` | 攻击特征速查表（上传/通信/持久化的常见特征与调查方向） | MITRE ATT&CK T1505.003；NSA/CISA 联合报告 | 官方标准/厂商研究 | ✅ 直接支持通用特征模式 | 作为调查方向与启发式；不是本事件确认证据 | 补充“仅为通用特征，需结合事件证据”限定 |
| `K-WEBSHELL-TOOLS-TRAFFIC` | 中国菜刀/蚁剑/冰蝎/哥斯拉/Weevely 等默认流量特征 | MITRE ATT&CK S0020；CSDN | 厂商经验/启发式 | ⚠️ 部分支持；仅为“默认配置”启发线索 | 只能标记“可疑”，不可作为唯一判定证据或家族归属依据 | 保持“仅可疑线索，可被绕过”限定；不得据 AES/RSA 确认 Godzilla/Behinder |
| `K-WEBSHELL-EVIDENCE-CHECKLIST` | 检查 Web 目录可疑脚本、双扩展名、Web 异常 POST/固定参数、web 进程拉起命令行、异常外连 | NSA/CISA 联合报告；CISA Eliminate Web Shells (CM0106) | 官方标准/方法论 | ✅ 直接支持检查方法论 | 作为调查清单 | 无；用于“该查什么” |
| `K-WEBSHELL-RESPONSE-TEMPLATE` | 隔离→保全证据→删除 WebShell→改密→查根因→恢复→修复加固 | CISA Eliminate Web Shells (CM0106) | 官方运营指南 | ✅ 直接支持处置流程 | 仅在确认/高置信时引用；弱信号不得无条件套用 | 明确“高风险处置需审批”；弱信号 case 禁套用 |
| `K-WEBSHELL-MANUAL-TAKEOVER` | 停止条件与人工接管条件（证据足够/达上限/工具无数据；高风险+关键证据不足+工具失败→人工接管） | 《最小 WebShell 知识包》使用约定 | 内部约定（非外部来源） | ✅ 作为内部规则 | 作为过程规则，不属外部证据事实 | 无；属于过程约束 |

> 关键结论：知识包唯一的“级别低”条目是 `K-WEBSHELL-TOOLS-TRAFFIC`（厂商经验/启发式），它**只能**把工具特征标记为“可疑”，不能作为确认或家族归属证据。这一点直接决定了 case2（Godzilla）与 case3（Beima）的结论上限。

## 2. 案例级来源—主张核验（基于 `knowledge-test-cases/来源矩阵.md` 与陈敏 case1-10 输入）

| case / 主张 | 来源来源 URL | 来源级别 | 来源直接支持什么 | 是否支撑判据中的关键主张 | 不支持/待确认 | 结论 |
|---|---|---|---|---|---|---|
| case1：混淆 ASPX WebShell 可用加密 HTTP 通信并提供命令/文件等能力 | fortinet.com（FortiGuard Labs） | 官方厂商研究 | UpdateChecker.aspx 使用 HTTP POST、`application/octet-stream`、Base64 编码加密数据、JSON 命令与命令/文件管理能力 | ✅ 支撑“存在加密通信弱信号”，但**不支撑 AES 算法确认** | 原文未指明算法为 AES；不支持 JSON 的 IP/时间/置信度；不得确认冰蝎 Behinder | 判据允许“弱信号 + 保留不确定性”，禁止“确认冰蝎 / 确认攻击成立” ✅ |
| case2：PassiveNeuron 活动中攻击者经 Microsoft SQL 获远程执行后尝试部署 ASPX WebShell | securelist.com（Kaspersky GReAT） | 官方厂商研究 | Windows Server 场景 SQL 远程执行、Base64/hex 载荷、PowerShell/VBS 解码写入、安全产品阻止多次部署尝试；**不证明部署成功** | ⚠️ **冲突**：陈敏 case2 输入改为“Godzilla 已确认”（含 ViewState 反序列化、Wingtb.sys、进程隐藏、AES/RSA、initial_verdict=疑似真实攻击） | 来源不支持 Godzilla、MachineKey、ViewState、Wingtb.sys，也不支持“部署成功”；与沈洪旭 case2“部署尝试未成功”亦不一致 | **必须 Review**：判据允许复述输入事实，但禁止“Godzilla 家族 / 内核 Rootkit 持久化 / 部署成功”；建议陈敏修正 case2 输入使其与来源一致 |
| case3：Beima PHP WebShell 使用加密命令并面向 WordPress/cPanel | mallory.ai（二手聚合） | 二手聚合页面 | 仅作为寻找 Cyderes 原始研究的线索与案例灵感 | ⚠️ 部分支撑：只支撑“存在 PHP WebShell/加密命令/JSON 通信”类信号 | RSA 细节、感染数量、时间戳篡改、归属未核实 | 判据收口为 weak_signal，禁止“Beima 家族 / 已攻陷”；RSA 强关键词导致的 CONFIRMED 视为判据缺陷 |
| case4：单条 WebShell 文件告警但缺上下文 | 无特定外链 | 通用 synthetic | 用于验证证据不足 | ✅ 支撑“证据不足”判据 | 非真实事件；不支持任何攻击者/来源/处置效果事实 | 判据：weak_signal + 人工接管 ✅ |
| case5：模拟超时/权限不足/空数据 | 无特定外链 | 通用 synthetic | 验证失败条件下不编造工具返回并建议人工接管 | ✅ 支撑 | JSON 告警文字不是一次真实 XDR 调用 | 判据：weak_signal + 人工接管；禁止“未发现风险/调查成功” ✅ |
| case6：WordPress 插件/供应链异常但无 WebShell 证据 | radar.offseq（二手聚合） | 二手安全聚合 | 只作为供应链/插件异常场景灵感 | ✅ 支撑“非 WebShell 域” | 不支持 WebShell 植入/持久化/最终目标 | 判据：out_of_scope，禁止任何 WebShell 命中与事实 ✅ |

## 3. 需要三方对齐的核心冲突

### 3.1 case2 输入与来源矩阵冲突（最严重）

- 沈洪旭/R主线的 case2（`knowledge-test-cases/case2.json`）：PassiveNeuron 部署**尝试**，安全产品阻止，**尚无部署成功证据**，`evidence` 为空、信号放在 `alerts`。
- 陈敏 PR#43 的 case2（`tests/fixtures/gatekeeper_cases/case2.json`）：Godzilla **已确认**，含 `ViewState反序列化`、`Wingtb.sys`、`进程隐藏`、`AES/RSA加密通信`，`initial_verdict=疑似真实攻击`，信号放在 `evidence`。
- `来源矩阵.md` 明确：来源**不支持 Godzilla、MachineKey、ViewState、Wingtb.sys**，且原文是“部署尝试被阻止”。

**结论**：两条 case2 是**同一 case_id/event_id 下的两套互斥事实**。判据只能以“输入事实”为准复述，但不得把不被来源支持的家族/持久化写成确认事实。**建议**：交由陈敏确认 case2 是否回归“部署尝试未成功”，或补充直接来源后再保留“已确认”口径；在来源补齐前，判据按 weak_signal（保守）收口并标注冲突。

### 3.2 证据字段位置冲突（alerts vs evidence）

- 沈洪旭 case1-6：信号放在 `alerts`，`evidence=[]`。
- 陈敏 case1-10：信号放在 `evidence`，部分 case 无 `alerts`。

`gatekeeper.py` 同时读取 `alerts` 与 `evidence`，因此两种字段都能被门禁识别；但判据/评测若只检查其中一个字段，会产生口径漂移。**建议**：冻结统一字段（建议以 `evidence` 为准，`alerts` 作为原始告警），或要求两套 fixture 字段一致。

### 3.3 门禁 `triage` 字段实现点（陈敏侧需确认）

`SecurityEventInput` 的 dataclass 恒含 `triage` 字段（即使输入未给），而门禁白名单未包含它，`_extract_triage_signal` 以 `"triage" in forbidden` 判断，导致：**每个 case 恒产生 `forbidden_triage_read`，且 `initial_verdict` 的 verdict 信号实际上永远不会被生成**（因为函数提前 return）。这使“初步研判”这一弱信号来源失效。

**建议**：陈敏确认是否改为以 `used_dict`（过滤后实际字段）判断 triage 是否越界，而非 `all_names`；否则 `initial_verdict` 信号形同虚设。

## 4. 收口结论

- 知识卡整体来源等级：`PRINCIPLE/FEATURES/CHECKLIST/RESPONSE` 为官方标准或厂商研究，可直接用于“调查方向/处置流程/启发”；`TOOLS-TRAFFIC` 为厂商经验/启发式，只能标“可疑”。
- 判据的结论上限已按来源边界收紧：case2（Godzilla）不允许据知识定家族，case3（Beima）收口 weak_signal，case6/case10 为 out_of_scope 且禁止 WebShell 结论。
- 需三方跟进：① case2 输入与来源冲突（陈敏）；② alerts/evidence 字段位置统一（陈敏）；③ 门禁 triage 判断实现（陈敏）；④ Beima/Cyderes 原始来源补充（沈洪旭）。
