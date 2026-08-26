# WebShell 知识问答样本

> 说明：本文件为 WebShell 场景的知识问答评测样本，共 5 题。每题包含问题、预期答案、参考资料和难度等级，用于评测深度调查 Agent 的知识检索与理解能力。


  ## 样本 1

  - **问题**：根据 MITRE ATT&CK 框架，WebShell 归属于哪个战术（Tactic）？其完整的技术编号是什么？
  - **预期答案**：WebShell 归属于持久化（Persistence，TA0003）战术。完整技术编号为 **T1505.003**（Server Software Component: Web Shell）。
  - **参考资料**：MITRE ATT&CK, T1505.003 - Server Software Component: Web Shell, https://attack.mitre.org/techniques/T1505/003/ （"Detailed Description"段落）[reference:0]
  - **难度**：简单


  ## 样本 2

  - **问题**：请列举 3 个已知使用过 WebShell 的攻击组织。
  - **预期答案**：至少包括：
    - **Sandworm Team（G0034）** —— 在 2022 年乌克兰电力攻击中部署了 Neo-REGEORG WebShell
    - **APT29（G0016）** —— 在受攻击的 Microsoft Exchange 服务器上安装 WebShell
    - **Agrius（G1030）** —— 在初始访问后部署 ASPXSpy WebShell 变种
  - **参考资料**：MITRE ATT&CK, T1505.003 - Procedure Examples, https://attack.mitre.org/techniques/T1505/003/#procedure-examples （"Procedure Examples"章节完整列表）[reference:1]
  - **难度**：中等


  ## 样本 3

  - **问题**：根据 MITRE ATT&CK 的官方检测策略（Detection Strategy），检测 WebShell（T1505.003）时，应重点监控哪些服务器行为？
  - **预期答案**：MITRE ATT&CK 针对 WebShell 的检测策略（DET0394）定义了多个分析维度（Analytics），主要包括：
    1. **异常文件创建 + 进程创建（AN1108）** ：Web 目录中异常创建文件后，Web 服务器进程（如 `w3wp.exe`）紧接着启动了命令行解释器（如 `cmd.exe`、`powershell.exe`）；
    2. **非法脚本创建 + 系统工具执行（AN1109）** ：在 Web 根目录（如 `/var/www/html`）中创建了未授权的脚本文件（如 `.php`、`.sh`），随后 Apache/Nginx 进程执行了非预期的系统工具（如 `curl`、`bash`、`nc`）；
    3. **异常网络流量** ：入站 HTTP POST 请求带有可疑的 payload 大小或 User-Agent；或对 `.php`、`.jsp`、`.aspx` 文件的 POST 请求 body 具有高熵值（可能是 Base64 或 XOR 编码的 WebShell 通信）。
  - **参考资料**：MITRE ATT&CK, Detection Strategy DET0394 - Web Shell Detection via Server Behavior and File Execution Chains, https://attack.mitre.org/detectionstrategies/DET0394/ [reference:2]
  - **难度**：中等


  ## 样本 4

  - **问题**：检测 WebShell 时应采用哪些具体方法？
  - **预期答案**：CISA 官方指南（CM0106）建议将以下检测逻辑作为深度防御策略的组成部分：
    1. **文件对比**：将 Web 服务器上的文件与已知良好版本进行对比，可使用 Microsoft Windiff 或 NSA Cyber 开发的 dirChecker 工具；
    2. **日志分析**：检测 Web 服务器日志中的异常 User-Agent、Referrer 头和 IP 地址（需注意此方法可能产生较高误报，应持续监控和优化）；
    3. **主机特征检测**：使用 YARA 及 NSA 提供的核心 WebShell 检测签名（core.webshell_detection.yara）扫描主机上的 WebShell 特征；
    4. **网络特征检测**：检测常见 WebShell 的网络侧特征，以及异常的网络流量。
  - **参考资料**：CISA, Eliminate Web Shells (CM0106) - "Detecting Web Shells" 章节, https://www.cisa.gov/eviction-strategies-tool/info-countermeasures/CM0106 [reference:3]
  - **难度**：中等


  ## 样本 5

  - **问题**：根据 CISA 的《Eliminate Web Shells》（CM0106）指南，发现 WebShell 后的标准消除流程包含哪些步骤？
  - **预期答案**：CISA 官方指南（CM0106）规定的消除流程如下：
    1. **隔离** ：将受感染的 Web 服务器隔离，减少横向移动的可能性；
    2. **保全证据** ：保留磁盘和内存工件，以及操作系统、Web 应用、访问、错误、WAF、反向代理、CDN、DMZ 防火墙和数据库等各类日志；
    3. **删除 WebShell** ；
    4. **修改密码**：修改 Web 管理员、数据库用户、托管账户和远程访问（FTP、SSH 等）的密码；
    5. **调查根本原因**：调查导致入侵的底层漏洞或原因；
    6. **从干净备份恢复** ；
    7. **修复和加固**：在确认根本原因后，通过打补丁和加固 Web 应用及 Web 服务器进行修复。
  - **参考资料**：CISA, Eliminate Web Shells (CM0106) - "Eliminating Web Shells" 章节, https://www.cisa.gov/eviction-strategies-tool/info-countermeasures/CM0106 [reference:4]
  - **难度**：中等

  

  

  ## 样本统计

| 维度            | 题号 |
| --------------- | ---- |
| ATT&CK 框架基础 | 1, 3 |
| 攻击组织识别    | 2    |
| 检测方法        | 4    |
| 应急响应与消除  | 5    |

  ## 参考资料索引

| 编号          | 来源                                                         |
| ------------- | ------------------------------------------------------------ |
| [reference:0] | MITRE ATT&CK, T1505.003 - Server Software Component: Web Shell, https://attack.mitre.org/techniques/T1505/003/ （"Detailed Description"段落） |
| [reference:1] | MITRE ATT&CK, T1505.003 - Procedure Examples, https://attack.mitre.org/techniques/T1505/003/#procedure-examples （"Procedure Examples"章节完整列表） |
| [reference:2] | MITRE ATT&CK, Detection Strategy DET0394 - Web Shell Detection via Server Behavior and File Execution Chains, https://attack.mitre.org/detectionstrategies/DET0394/ |
| [reference:3] | CISA, Eliminate Web Shells (CM0106) - "Detecting Web Shells" 章节, https://www.cisa.gov/eviction-strategies-tool/info-countermeasures/CM0106 |
| [reference:4] | CISA, Eliminate Web Shells (CM0106) - "Eliminating Web Shells" 章节, https://www.cisa.gov/eviction-strategies-tool/info-countermeasures/CM0106 |
