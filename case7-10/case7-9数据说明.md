# case7–10 数据来源说明

## case7：合法上传或Base64业务

**数据性质**：synthetic（合成案例）
**设计目的**：验证系统不会因为出现文件上传或Base64编码就自动判为WebShell
**核心信号**：文件上传 + Base64编码参数
**来源URL**：

- https://developer.mozilla.org/zh-CN/docs/Web/HTTP/Basics_of_HTTP/MIME_types/Common_types
- https://datatracker.ietf.org/doc/html/rfc4648

**刻意保留的弱信号**：Base64编码参数、文件上传行为（容易与WebShell上传混淆）
**刻意排除的强证据**：无文件内容高危函数（eval、Process.Start等），无进程创建，无响应体敏感信息

**需要检查的输入问题**：

1. `source_ip` 为内网地址（10.88.32.101），是否符合 `SecurityEventInput` 的 IP 字段约束？是否需要改成公网 IP？

2. `event_type` 为 `WebShell`，但事件本身无 WebShell 恶意信号，是否应该用其他 `event_type`？还是保持 `WebShell` 用于测试误报场景？

3. `evidence` 中包含了足够多的业务上下文（接口路径、文件大小、调用记录），是否会让 Agent 直接判定为合法业务而跳过调查？设计目的是"不会自动判为WebShell"，而非"直接判为合法"，当前表述是否平衡？

4. `initial_verdict` 为"待调查"，`confidence` 为 0.25，是否符合事件描述中的证据强度？





## case8：只有可疑脚本名

**数据性质**：synthetic（合成案例）
**设计目的**：验证单一弱信号不会被知识增强放大为确定性结论
**核心信号**：文件名为 `shell.php`，无其他证据
**来源URL**：

- https://attack.mitre.org/techniques/T1505/003/
**刻意保留的弱信号**：文件名为 `shell.php`（高危命名），与业务无关联引用
**刻意排除的强证据**：无HTTP访问记录、无文件内容分析、无进程关联、无时间链条对应

**需要检查的输入问题**：


1. `source_ip` 为内网地址（192.168.10.55），是否符合字段约束？

2. `severity` 为 `LOW`，但 `event_type` 为 `WebShell`，是否存在严重等级与事件类型不匹配的问题？

3. `evidence` 中仅有一条实质性内容（文件名为 `shell.php`），其余均为"未检测到"，这种以否定性描述为主的证据列表是否能被下游正常解析和理解？

4. `initial_verdict` 为"待调查"，`confidence` 为 0.15，是否与"仅文件名可疑"的弱信号定位一致？





## case9：Web进程与异常POST强证据组合

**数据性质**：synthetic（合成案例）
**设计目的**：为 `in_scope` 提供较明确的正向组合证据
**核心信号**：IIS异常POST + 文件修改 + w3wp.exe创建cmd.exe子进程
**来源URL**：

- https://attack.mitre.org/techniques/T1505/003/#detection

**刻意保留的强证据**：POST请求含Base64长参数、文件修改时间对齐、文件内容含高危函数、IIS进程创建子进程、响应体含编码系统信息
**刻意排除的内容**：未写入最终结论（如"攻击成功"），未虚构超出案例范围的工具查询结果



**需要检查的输入问题**：

1. `evidence` 中包含了进程 PID（2844）和精确到秒的时间戳（14:20:03、14:20:05、14:20:10），这些细节是否符合当前输入模型的粒度？是否会过于具体导致与真实平台工具的字段风格不一致？

2. 7 条证据之间存在强时间关联和因果关系，是否属于"在输入中预设了关联链条"？Agent 应当自己建立关联还是可以直接利用输入中已排列好的证据顺序？

3. `initial_verdict` 为"疑似真实攻击"，`confidence` 为 0.82，是否过高？是否会引导 Agent 跳过独立判断直接接受该结论？





## case10：完全非WebShell安全事件

**数据性质**：synthetic（合成案例）
**设计目的**：验证 `out_of_scope` 拒绝WebShell知识，数据为无关的域外负向事件
**核心信号**：SSH暴力破解
**来源URL**：

- https://attack.mitre.org/techniques/T1110/
- https://attack.mitre.org/techniques/T1505/003/

**刻意排除的WebShell信号**：无Web日志异常、无Web目录文件操作、无Web进程异常行为、无HTTP请求、无脚本执行


**需要检查的输入问题**：



1. `event_type` 为 `WebShell`，但事件实际为 SSH 暴力破解（与 WebShell 完全无关），`event_type` 是否应该改回其他类型？还是保持 `WebShell` 用于测试 `out_of_scope` 拒绝？

2. `severity` 为 `MEDIUM`，但 15 分钟 847 次登录失败，在高强度暴力破解场景下是否应该为 `HIGH` 或 `CRITICAL`？

3. `initial_verdict` 为"误报或无关告警"，`confidence` 为 0.95，是否在输入中预先写入了"结论"（而非仅描述事实）？是否需要降低 confidence 或将 verdict 改为更中性的表述？

4. 该事件的 `target_ip`（192.168.5.60）与 case9 的 `target_ip`（192.168.5.50）在同一网段，是否需要区分以避免跨案例关联？

##

## 使用说明

1. 以上URL均经过访问验证，可作为案例设计的来源支撑。
2. 四个案例均为 **synthetic**（合成数据），不涉及真实平台事件或未脱敏响应。
3. 案例输入中不包含预期答案、评测说明或最终结论。
4. 闫昱硕编写判据时，可结合以上来源URL验证案例设计是否符合实际攻击/业务模式。
