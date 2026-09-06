# Case1-10 门禁可读取信号标注（WebShell Gatekeeper）

> 标注版本：2026-09-06.gatekeeper-v1
> 标注人：自动运行 WebShellGatekeeper（确定性规则，不使用 LLM）
> 适用门禁三档：in_scope_confirmed / in_scope_weak / out_of_scope + benign_like（杨嘉琪三档门禁可直接使用 signal_summary 字段）
> 约定：不得从知识内容反向补入事件证据；所有信号均来自 event_type / alerts / evidence / triage 四字段。

---

## 案例: case1 (TC-KNOWLEDGE-001)
读取字段: alerts、confidence、event_type、evidence、initial_verdict、severity、source_ip、target_ip、triage

提取信号（按强度）：
1. event_type=WebShell（标签）           信号性质: weak_signal    来源: event_type
2. 告警 WebShell通信行为告警              信号性质: weak_signal    来源: alerts
3. 告警 可疑文件上传告警                  信号性质: weak_signal    来源: alerts
4. AntSword UA / antsword 工具特征        信号性质: weak_signal    来源: evidence
5. 无业务上下文文件上传                   信号性质: weak_signal    来源: evidence
6. 文件内容 Process.Start 高危函数        信号性质: weak_signal    来源: evidence
7. w3wp.exe 创建 cmd.exe 子进程           信号性质: weak_signal    来源: evidence
8. triage 上游恶意判定参考                信号性质: weak_signal    来源: triage
9. [强组合命中] 高危执行代码 + Web进程spawn子进程   信号性质: confirmed_webshell  来源: evidence
10. multipart/form-data 上传形式（非WebShell特有，合法业务辅助） 信号性质: non_webshell   来源: evidence

信号汇总: 1 confirmed_webshell + 9 weak_signal + 1 non_webshell → IN_SCOPE_CONFIRMED
不得提取: 已确认WebShell、已建立持久化、攻击成功、已植入后门、攻击者已取得控制
输入问题: 无
样例数据性质: synthetic_regression（典型正向组合案例）

---

## 案例: case2 (TC-KNOWLEDGE-002)
读取字段: alerts、confidence、event_type、evidence、initial_verdict、severity、source_ip、target_ip、triage

提取信号:
1. event_type=WebShell                       weak_signal  event_type
2. 告警 可疑文件上传告警                      weak_signal  alerts
3. 无业务上下文文件上传                       weak_signal  evidence
4. 可疑文件名 cmd.php × 3处出现               weak_signal  evidence
5. 菜刀特征 z0=/z1= POST 参数                 weak_signal  evidence

信号汇总: 0 confirmed + 10 weak → IN_SCOPE_WEAK（缺文件内容+进程执行记录，必须进入调查）
不得提取: 同上
输入问题: 无
样例数据性质: synthetic_regression（落地文件+工具参数但未执行的典型弱信号）

---

## 案例: case3 (TC-KNOWLEDGE-003)
读取字段: alerts、confidence、event_type、evidence、initial_verdict、severity、source_ip、target_ip、triage

提取信号:
1. event_type=WebShell                       weak_signal  event_type
2. 告警 可疑文件上传告警                      weak_signal  alerts
3. 无业务上下文文件上传 × 5处                 weak_signal  evidence
4. 双扩展名 .jpg.php + .gif.php              weak_signal  evidence
5. 合法业务 头像上传/avatar 背景（第一次上传是合法头像）  non_webshell  evidence

信号汇总: 0 confirmed + 9 weak + 1 non_ws → MIXED（必须调查，甄别上传目录与真实内容）
不得提取: 同上
输入问题: 无
样例数据性质: synthetic_regression（混合场景：合法头像+伪装双扩展名上传）

---

## 案例: case4 (TC-KNOWLEDGE-004)
读取字段: confidence、event_type、evidence、initial_verdict、severity、source_ip、target_ip、triage

提取信号:
1. event_type=WebShell                       weak_signal  event_type
（说明：Base64 长参数本可作为 weak_signal，但证据中出现“文档未声明 Base64 编码入参”后紧跟“未检测到…/不支持…”等否定语句，且该 Base64 缺乏文件落地/进程执行配套证据 → 本轮仅保留 event_type 为惟一弱信号；其余被否定句过滤机制屏蔽，保证不放大为确定性结论。）

信号汇总: 0 confirmed + 1 weak → IN_SCOPE_WEAK（证据明显不足，必须调查解码）
不得提取: 同上
输入问题: 无
样例数据性质: synthetic_regression（参数编码异常但多维证据均缺失的典型证据不足案例）

---

## 案例: case5 (TC-KNOWLEDGE-005)
读取字段: alerts、confidence、event_type、evidence、initial_verdict、severity、source_ip、target_ip、triage

提取信号:
1. event_type=WebShell                       weak_signal  event_type
2. 告警 WebShell通信行为告警                  weak_signal  alerts
3. 文件内容 eval(base64_decode(...)) 高危函数  weak_signal  evidence
4. apache 创建 bash 子进程                    weak_signal  evidence
5. triage 上游恶意判定参考                    weak_signal  triage
6. [强组合命中] 高危执行代码 + apache创建bash → confirmed_webshell  evidence
7. “无正常业务页面响应结构” 句式中的正常业务片段 →  non_webshell  evidence

信号汇总: 1 confirmed + 5 weak + 1 non_ws → IN_SCOPE_CONFIRMED
不得提取: 同上
输入问题: 无
样例数据性质: synthetic_regression（冰蝎加密流+落地+执行+持久化痕迹的强正向组合）

---

## 案例: case6 (TC-KNOWLEDGE-006)
读取字段: alerts、confidence、event_type、evidence、initial_verdict、severity、source_ip、target_ip、triage

提取信号:
1. triage 上游恶意判定参考                    weak_signal  triage（仅分诊通用判定，不含 WebShell 具体证据）
2. OR 1=1 注入载荷、UNION SELECT、sleep(5)、@@version  → 4 条 out_of_scope  evidence（SQL 注入专用攻击特征，WebShell知识库必须拒绝纳入）

信号汇总: 0 ws_confirmed + 1 weak_triage + 4 out_of_scope → OUT_OF_SCOPE（纯SQL注入，非WebShell域）
不得提取: 同上
输入问题: 无
样例数据性质: synthetic_regression（纯非WebShell负向案例，不混入WebShell弱信号以降低门禁难度，符合设计要求）
特别备注: 本案例明确不提供任何 WebShell 文件名、上传、执行、通信线索，用于验证门禁不会因为 triage=malicious 就误落入 WebShell 调查路径。

---

## 案例: case7 (TC-KNOWLEDGE-007)
读取字段: confidence、event_type、evidence、initial_verdict、severity、source_ip、target_ip

提取信号:
1. event_type=WebShell                       weak_signal  event_type（标签误报）
2. 2 处 Base64 长参数（头像业务中 userId 编码，与WebShell无关） weak_signal  evidence
3. 合法业务标识: avatar × 3处、image/png、正常调用记录 × 1 → 5 条 non_webshell  evidence

信号汇总: 0 confirmed + 3 weak + 5 non_ws → MIXED → 实际调查后应落 BENIGN_LIKE
不得提取: 同上
输入问题: 无
样例数据性质: synthetic_regression（合法头像上传，验证出现上传/Base64不自动判恶意）
特别备注: 符合“体现合法上传/合法Base64业务，不因上传/Base64默认恶意”要求。

---

## 案例: case8 (TC-KNOWLEDGE-008)
读取字段: confidence、event_type、evidence、initial_verdict、severity、source_ip、target_ip

提取信号:
1. event_type=WebShell                       weak_signal  event_type
2. 可疑文件名 shell.php                      weak_signal  evidence
3. Base64（仅文件创建时间戳格式长串，非payload） weak_signal  evidence
4. 未检测到对应的HTTP请求记录                non_webshell  evidence
5. 未检测到该文件被访问或执行记录            non_webshell  evidence

信号汇总: 0 confirmed + 3 weak + 2 non_ws → MIXED（典型只有文件名的弱信号）
不得提取: 同上
输入问题: 无
样例数据性质: synthetic_regression（只有可疑脚本名的典型弱信号，必须调查不能直接定性）
特别备注: 符合“只有可疑脚本名，应是典型弱信号”要求。

---

## 案例: case9 (TC-KNOWLEDGE-009)
读取字段: confidence、event_type、evidence、initial_verdict、severity、source_ip、target_ip

提取信号:
1. event_type=WebShell                       weak_signal  event_type
2. Base64 长参数 × 多条证据                  weak_signal  evidence
3. 文件内容 System.Runtime.InteropServices + Process.Start  →  weak_signal  evidence
4. w3wp.exe 创建 cmd.exe /c whoami           weak_signal  evidence
5. [强组合A] 高危执行代码 + w3wp创建cmd      confirmed_webshell  evidence
6. [强组合B] 异常POST Base64 + 响应体返回编码系统信息  confirmed_webshell  evidence

信号汇总: 2 confirmed + 4 weak → IN_SCOPE_CONFIRMED（双组合双重锁定）
不得提取: 同上
输入问题: 无
样例数据性质: synthetic_regression（符合“IIS异常POST + 文件修改 + 进程创建的强证据组合”要求）
特别备注: 本案例设计为 confirmed_webshell 数量=2 作为上限参考，后续若新增案例不应随意超过该强度。

---

## 案例: case10 (TC-KNOWLEDGE-010)
读取字段: confidence、event_type、evidence、initial_verdict、severity、source_ip、target_ip

提取信号:
1. event_type=WebShell                       weak_signal  event_type（仅平台标签用于 out_of_scope 测试）
2. SSH × 2、暴力破解 × 1 → 合计 3 条        out_of_scope  evidence（身份认证暴力破解非WebShell域）

信号汇总: 0 ws_confirmed + 1 weak_label + 3 out_of_scope → OUT_OF_SCOPE
不得提取: 同上
输入问题: ["event_type=WebShell 但证据主体为 SSH 暴力破解，需确认 event_type 标注是否为测试 out_of_scope 用（按设计要求：本 case 仅用于检验域外拒绝，并非第二攻击场景支持）"]
样例数据性质: synthetic_regression（完全非WebShell事件，仅用于检验域外拒绝）
特别备注: 符合“完全非WebShell事件，只用于检验域外拒绝，不代表项目支持了第二攻击场景”的要求。

---

## 附录：三档门禁映射（供杨嘉琪直接绑定 knowledge_query 事件）

| 最终 summary 类型               | 三档门禁 | 后续处理 | knowledge_query 绑定策略 |
|---|---|---|---|
| OUT_OF_SCOPE                    | GATE-OUT | 结束 WebShell 调查路径，切换对应攻击域知识 | 不绑定 WebShell 知识包 |
| IN_SCOPE_CONFIRMED              | GATE-3（强放行进入调查） | 调查直接按强证据维度展开（处置前置）| 绑定 WebShell 全部 4 个知识章节（攻击原理/特征/证据清单/处置建议） |
| IN_SCOPE_WEAK                   | GATE-2（弱信号，必须调查） | 必须走调查清单 + 误报条件 + 证据缺口三件套 | 绑定“攻击特征速查表 + 证据检查清单”2 章即可 |
| MIXED（弱>合法）                | GATE-2 | 同上 | 同上 |
| MIXED（合法≥弱）/ BENIGN_LIKE   | GATE-1（误报倾向）| 走误报条件优先核验，必要时驳回至分诊 | 绑定“误报条件+证据缺口”仅输出结构化说明 |
| INDETERMINATE                   | GATE-0 人工接管 | 打 evidence_gaps 进入人工复核 | 不绑定知识包，输出“请补齐字段/补充平台日志” |

> 以上三档均由确定性信号计数决定，不依赖 LLM 做基础分类。
