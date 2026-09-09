# WSK 知识卡（1-15）来源—主张边界 Review（闫昱硕）

> 本文件是基于「交闫昱硕」给出的 15 张 WSK 知识卡（`知识卡1-15.zip` 解压为 `知识卡1.md` ~ `知识卡15.md`）的来源—主张边界 Review。用途：编写 10 份正式判据并完成来源—主张边界 Review。
>
> 评审原则：来源支持“某公开事件/某产品曾出现某技术”，**不等于**支持 synthetic 案例 JSON 里的每个字段；知识卡里的“调查步骤/常见处置建议”是操作指引，不是事件事实；卡内“禁止推断”条款是 Agent 引用时必须遵守的边界。

## 1. WSK 卡总体定位

15 张卡是对原 `webshell-knowledge.md` 的细化和扩展，分三类：

- **正向调查**（WSK-001/002/003/004/005/006/007/013/014）：识别 WebShell 的多类证据与特征；
- **误报与弱信号**（WSK-008/009/010）：把“静态特征/编码特征/单一弱信号”与“确认攻击”区分开；
- **处理策略与处置边界**（WSK-011/012/015）：工具失败、空集、证据强度分级与响应动作。

## 2. WSK ↔ 旧知识组 ↔ 10 判据 映射

冻结评测汇总 Schema 的 `matched_knowledge_ids` 仍用 6 个 `K-WEBSHELL-*` 组。WSK 卡是更细的粒度，映射如下（后续若 L 雨妍扩 Schema 为 WSK 级，判据知识 ID 可直接下钻）：

| WSK | 主题 | 关联案例 | 对应旧知识组（K-WEBSHELL-*） | 证据强度口径 |
|---|---|---|---|---|
| WSK-001 | 多证据组合关联识别 | case9、case3 | `PRINCIPLE` | 确认（组合） |
| WSK-002 | 文件证据检查 | case9、case8 | `EVIDENCE-CHECKLIST` | 强/弱视内容 |
| WSK-003 | Web 日志证据检查 | case9、case7 | `EVIDENCE-CHECKLIST` | 强/弱视关联 |
| WSK-004 | 进程证据检查 | case9 | `EVIDENCE-CHECKLIST` | 确认（进程） |
| WSK-005 | PHP 识别特征 | case9、case8 | `FEATURES` | 弱（需内容分析） |
| WSK-006 | JSP 识别特征 | case9 | `FEATURES` | 弱（需输入可控） |
| WSK-007 | ASPX 识别特征 | case9、case3 | `FEATURES` | 弱（需输入可控） |
| WSK-008 | 合法业务误报 | case7、case8 | `EVIDENCE-CHECKLIST` | 弱/误报排除 |
| WSK-009 | 编码/加密参数误报 | case7、case9 | `TOOLS-TRAFFIC` | 弱（需解码验证） |
| WSK-010 | 弱信号与证据不足 | case8、case7 | `EVIDENCE-CHECKLIST` | 弱 |
| WSK-011 | 工具查询失败 | case8、case9 | `MANUAL-TAKEOVER` | 弱/人工接管 |
| WSK-012 | 查询返回空集 | case8、case10 | `MANUAL-TAKEOVER` | 弱/人工接管 |
| WSK-013 | WebShell 植入方式 | case9、case10 | `PRINCIPLE` | 弱（需植入证据） |
| WSK-014 | 网络证据检查（外连/C2） | case9、case10 | `TOOLS-TRAFFIC` | 弱（需流量内容） |
| WSK-015 | 处置建议边界 | case8、case9、case10 | `RESPONSE-TEMPLATE` | 分级响应 |

> 结论：`K-WEBSHELL-*` 六组是 15 张 WSK 卡的上层归类。10 份判据里的 `allowed/required/forbidden_knowledge_ids` 使用这六组是**兼容冻结 Schema** 的正确做法；WSK 卡用于“该查什么、能推到什么程度”的来源边界，与判据不冲突。

## 3. 每卡边界确认

我把 `交yys.md` 第 4、5 节的清单与卡片内容逐条比对，全部一致。以下为每卡“只属调查建议”与“绝对不能升级成事实”的汇总确认：

| WSK | 只属于调查建议（可引用为指引） | 绝对不能升级成事实（引用即越界） |
|---|---|---|
| WSK-001 | 三类证据关联、时间差 ≤5 分钟关联、汇总时间线 | 三类证据“同时出现”≠攻击成功；“时间接近”≠因果；调查建议≠已发生处置；通用攻击手法≠本事件攻击者行为 |
| WSK-002 | stat/fsutil、哈希比对、权限/所有者检查 | 文件名可疑≠已执行；高危函数≠恶意（需排除 CMS 合法 eval） |
| WSK-003 | 日志筛选、频率统计、URI 关联、UA 对比 | POST 存在≠WebShell 通信；Base64/编码≠恶意 payload；单条日志≠完整攻击链 |
| WSK-004 | 进程树、命令行参数、时间关联、写入行为 | Web 进程建子进程≠WebShell（需为命令行解释器）；单次进程事件不能独立判定 |
| WSK-005 | 高危函数扫描、路径/文件名检查、可否 HTTP 访问 | 单个高危函数≠WebShell；文件名可疑≠恶意；混淆特征≠攻击成功 |
| WSK-006 | 关键字扫描、反射/类加载检查、路径检查 | Runtime.exec()≠WebShell（需输入可控）；ProcessBuilder 单独≠恶意 |
| WSK-007 | PowerShell/find 扫描、IIS 日志/事件日志关联 | Process.Start()≠WebShell（需接收外部输入）；ValidateRequest=false 不能单独作为恶意证据 |
| WSK-008 | MD5/SHA256 比对官方包、文件类型/权限核对 | 特征匹配告警≠攻击成功；文件名含敏感词≠恶意；误报场景通用特征≠WebShell |
| WSK-009 | Base64/十六进制解码、业务上下文核对、响应体检查 | Base64/编码≠WebShell payload（必须解码验证）；Accept-Charset 的 Base64≠恶意；编码特征不能独立判定 |
| WSK-010 | 扩展调查范围（前后 5 分钟）、检查业务解释、列证据缺口 | 单一弱信号≠攻击成功/已植入；无跨源关联≠攻击路径；无证据缺口补充≠高置信；跳过清单直接清理/隔离 |
| WSK-011 | 记录错误、检查环境/权限/网络、补救方案 | 工具执行失败≠未发现风险/环境安全；超时≠目标不存在 |
| WSK-012 | 检查查询条件/数据源/轮转/采集状态；扩大范围验证 | 单次查询空集≠攻击未发生/环境安全；空集≠整体安全 |
| WSK-013 | 记录路径/时间、查上传/日志、比对已知漏洞、查计划任务 | 文件名/文件修改时间≠植入时间；单漏洞存在≠已被利用；未查日志/漏洞≠推断植入方式 |
| WSK-014 | netstat/ss/lsof 抓连接、威胁情报碰撞、流量/DNS 检查 | 外连≠C2 通信（需流量内容+进程发起者）；威胁情报匹配≠攻击成功；未验流量≠WebShell 命令 |
| WSK-015 | 证据强度分级（Level 0-4）→ 对应响应动作 | 通用处置原则（发现即隔离）不能套用所有强度；Level1 仅文件特征≠严重攻击；Level0 无有效证据≠需响应 |

## 4. 待 Review 主张核验结论（8 项）

| # | 待 Review 主张 | 来源等级 | 我的核验结论 |
|---|---|---|---|
| 1 | WSK-001：三类证据关联 + “时间差 ≤5 分钟”阈值 | B（厂商规则） | **阈值属操作启发，非来源直接规定**。MITRE 只给框架；Splunk/CraftedSignal 是检测规则，未规定 5 分钟。应保持为“调查建议/启发”，不得作为固定事实或硬性判据阈值。 |
| 2 | WSK-004：Sigma 规则中 w3wp.exe 创建 cmd.exe 的检测逻辑 | B | **直接支撑（已核实规则原文）**。知识卡给出的具体路径 `proc_creation_win_webshell_susp_process_spawned_from_webserver.yml`（规则标题 “Suspicious Process By Web Server Process”）确认存在：`ParentImage` 命中 `\w3wp.exe` 等 Web 进程，`Image`（异常子进程）命中 `\cmd.exe`/`\powershell.exe`/`\bash.exe`/`\sh.exe` 等，`condition: 1 of selection_webserver_* and selection_anomaly_children`。即 `w3wp.exe → cmd.exe` 检测项**确实存在**（level: high，tag T1505.003/T1190）。注意：这是检测规则，属“可升级为高置信告警的启发式”，不等于攻击已成功。 |
| 3 | WSK-008：CoreRuleSet 中 Windows Defender 将规则文件误报为 PHP 后门的具体案例 | B（项目方一手技术分析） | **支撑**（更正：此前判为“不支撑”偏严）。2025-06-30 CoreRuleSet 项目维护者（龚格成）原文明确：Windows Defender 将 `RESPONSE-955-WEB-SHELLS.conf`（ModSecurity 检测 WebShell 的规则文件）**误报为 `Backdoor:PHP/Dirtelti.MTJ`**。可保留该具体案例；但属**单一项目观察**，不应推广为普遍规律。 |
| 4 | WSK-010：“扩展调查范围，检查同一时间窗口（前后 5 分钟）”阈值 | B | **阈值属操作启发**。安全内参未规定 5 分钟；应保留为“调查建议”，不写成固定规则。 |
| 5 | WSK-011：Apache Knox Jira 中 WebShell 连接超时的具体场景 | A | ❌ **来源错挂/关联不成立**。KNOX-2872 标题为 “Webshell does not work with loadbalancer”，但 Apache Knox 的 “Webshell” 指 **Knox 网关自带的 Web 终端 / WebSocket shell（配合 KnoxSSO / SSH 访问）**，**不是恶意 WebShell 后门**。该来源**不能**支撑安全应急场景“恶意 WebShell 工具查询超时”的处理策略。建议：改为通用“连接超时/负载均衡”运维建议，或替换为真正针对恶意 WebShell 工具失败的来源并注明。 |
| 6 | WSK-013：“第三方代码/插件预置后门”植入方式分类 | B | **部分支撑**。腾讯云文章分类覆盖该方式；但缺一手漏洞记录。应标注为“植入方式枚举/启发”，不得据此断言某个案例就是该方式。 |
| 7 | WSK-014：“出站流量大小异常”的具体判定基准 | B | **阈值属操作启发**。卡巴斯基/FreeBuf 未规定流量阈值；应保留为“启发”，不写成固定基准。辅以“威胁情报/进程发起者/流量内容”三重确认。 |
| 8 | WSK-015：证据强度分级 Level 0-4 的分级框架 | B/C | **综合提炼，非单一来源现成分类**。分级逻辑合理（与门禁 6 级/三档可对应），但需注明是“评价框架”，不是标准。建议：与门禁 `OUT_OF_SCOPE/IN_SCOPE_WEAK/IN_SCOPE_CONFIRMED` 及三档 `out_of_scope/weak_signal/in_scope` 对齐，避免多套分级并存。 |

> 共性结论：① 带“分钟/秒”的**时间阈值**（WSK-001/010）与**流量/大小阈值**（WSK-014）都属于操作启发，来源未直接规定；只能作为调查建议，不得写成固定判据或事实。② **C 级来源**（WSK-007 的 Idocdown、WSK-015 的 CSDN）只能作灵感，不能作已核实案例；WSK-008 的 CoreRuleSet 为项目方一手分析（B），可支撑该具体案例，但不推广为普遍规律。③ 有 **A 级官方/厂商来源**（WSK-007 的加拿大 Cyber Centre、趋势科技；WSK-002/003/004/005/006 的 MITRE/CISA/PHP 手册；WSK-014 的卡巴斯基）可直接支撑调查方法论与行为特征。

## 4.1 来源在线核验补充（2026-09-06 实测）

| 来源 | 实测结果 |
|---|---|
| WSK-007 加拿大 Cyber Centre（SharpViewStateKing） | ✅ 可访问。强支撑 ASP.NET/ViewState 植入框架、`w3wp.exe` 子进程监控、文件上传/命令执行插件、Base64/加密通信、`__VIEWSTATE` 等 ASPX 行为。 |
| WSK-007 趋势科技 Managed XDR | ✅ 可访问。真实 ASPX WebShell 事件：`w3wp.exe` 启动 `cmd.exe`/`powershell.exe`、`Request.Form["command"]`、FileUpload 未清理上传、C2 外连。强支撑 ASPX 识别特征。 |
| WSK-008 CoreRuleSet（GitCode） | ✅ 可访问。项目维护者一手分析，明确 Defender 将规则文件误报为 `Backdoor:PHP/Dirtelti.MTJ`。支撑“静态特征匹配易误报”及具体案例。卡片自标 C，实为一线维护者源码级一手分析，建议更正为 B（仍属单一项目观察，不推广为普遍规律）。 |
| WSK-008 IEEE 11513222 | ⚠️ 需权限/支付墙，页面为反机器人验证，无法读取正文。仅可引用其泛化结论（静态检测误报率高），勿引用具体数值/结论细节。 |
| WSK-011 Apache Knox KNOX-2872 | ✅ 可访问。**确认 “Webshell”= Knox Web 终端（安全 shell 访问），非恶意后门**——来源错挂。 |
| WSK-004 Sigma 规则 | ✅ 已核实规则原文（Phoenix / Sigma 镜像）。标准路径 `proc_creation_win_webshell_susp_process_spawned_from_webserver.yml`，标题 “Suspicious Process By Web Server Process”：`ParentImage` 含 `\w3wp.exe`，`Image` 含 `\cmd.exe`/`\powershell.exe`/`\bash.exe`/`\sh.exe` 等，condition 为“Web 服务父进程 + 异常子进程”命中 → 确含 `w3wp.exe → cmd.exe` 检测逻辑。 |

## 5. 与 10 份正式判据的关系

- 判据 1-10 的 `allowed/required/forbidden_knowledge_ids` 使用 `K-WEBSHELL-*` 六组（兼容冻结 Schema），其详细边界由对应 WSK 卡支撑（见第 2 节映射表）。
- 判据中的 `forbidden_conclusions` 与 WSK 卡的“禁止推断”一一对应（如 case7 禁止“自动判恶意” ↔ WSK-008/009；case6/10 禁止 WebShell 事实 ↔ WSK-015 Level 0；case9 禁止横向/持久化 ↔ WSK-001/013/014）。
- WSK-010/011/012 支撑弱信号与证据不足案例（case4/5/8/7）的“只给检查清单/缺口/人工接管”口径；WSK-015 支撑弱信号禁高风险处置、确认级才可引用处置模板的口径。

## 6. 结论与需跟进

- ✅ 15 张 WSK 卡的“来源等级、关联案例、只属调查建议、不能升级成事实”已核对，与 `交yys.md` 及卡片正文一致。
- ⏳ 8 项待 Review 主张均已给出核验结论；其中 3 项（#1/#4/#7 的阈值）应明确降为“操作启发”，1 项（#3）由“不支撑”更正为“支撑（B，项目方一手）”，1 项（#5）改判为“来源错挂、需换来源”，#2（WSK-004 Sigma）**已核实为直接支撑**，#6（WSK-013 第三方预置后门）与 #8（Level 0-4 分级框架）为“部分支撑/综合提炼”，需一手来源或与门禁三档对齐后才有充分把握。
- 需沈洪旭：补 WSK-007（ASPX）的 `ValidateRequest=false` 业务合理场景、WSK-008 的官方误报案例、WSK-013 的官方根因；需陈敏：case2/case10 输入口径（见 `来源主张边界review.md`）。
- 知识 ID 体系建议：冻结 Schema 保持 `K-WEBSHELL-*` 六组（兼容）；后续如需 WSK 级下钻，需与李雨妍升级汇总 Schema，勿在本批另起一套。

## 7. 给沈洪旭的明确整改反馈（2026-09-09 交办）

> 以下为本次 Review 确认、需要**沈洪旭处理**的三类问题（知识卡来源/内容整改），与陈敏的 case 输入口径问题互相独立。

### 7.1 WSK-011 来源错挂（必须换来源或改口径）

WSK-011 引用 `Apache Knox Jira KNOX-2872`（标题 “Webshell does not work with loadbalancer”），其 **“Webshell” 指 Knox 网关自带的 Web 终端 / WebSocket shell（配合 KnoxSSO / SSH 访问）**，是安全的下发通道，**不是恶意 WebShell 后门**。因此该来源**不能**支撑安全应急场景“恶意 WebShell 工具查询超时”的处理策略（见第 4 节 #5、4.1 实测）。

**建议**：改为通用“连接超时/负载均衡”运维建议，或替换为**真正针对恶意 WebShell 工具调用失败**的一手来源并注明；否则按“引用即越界”记缺陷，不允许 Agent 据此把“工具超时”写成对恶意 WebShell 的处置依据。

### 7.2 部分知识卡来源 URL 缺失 / 不可在线核验

若干知识卡的来源字段**未给出可核验 URL，或仅有机构名/二手聚合页**，导致无法按来源等级在线核实：

- WSK-007 的 Idocdown、WSK-015 的 CSDN：属 **C 级**，只能作灵感，不能作已核实案例；
- WSK-008 的 IEEE 11513222：需权限/支付墙，无法读取正文，只能引用泛化结论；
- WSK-008 的 CoreRuleSet（GitCode）：虽然可访问且为项目方一手分析（建议由 C 更正为 **B**），但属**单一项目观察**，不推广为普遍规律。

**建议**：请沈洪旭为每张 WSK 卡补齐一手、可在线核验的 URL（或明确标注为“灵感来源/二手聚合”），以便判据按来源等级收口；无法补齐的卡不得作为 A 级来源引用。

### 7.3 启发式阈值问题（不得写成固定规则/事实）

以下带“分钟/秒/大小”的阈值，**来源均未直接规定**，只能作为调查建议/启发，不得写成固定判据或事实（见第 4 节共性结论）：

- WSK-001／WSK-010：“时间差 / 同一时间窗口 ≤5 分钟”；
- WSK-014：“出站流量大小异常”的具体判定基准。

**建议**：将上述阈值统一降为“操作启发”；如需硬性阈值，需给出直接来源或注明“项目内定、非外部标准”。同时把 WSK-015 的 **Level 0-4** 与门禁 `OUT_OF_SCOPE / IN_SCOPE_WEAK / IN_SCOPE_CONFIRMED` 及三档 `out_of_scope / weak_signal / in_scope` 对齐，避免多套分级并存。
