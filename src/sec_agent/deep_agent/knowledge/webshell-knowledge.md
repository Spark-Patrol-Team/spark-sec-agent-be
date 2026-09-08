## 知识ID：WSK-001

- 主题：WebShell 正向调查 - 多证据组合关联识别

- 适用条件：

  - 调查中存在 Web 访问日志、文件系统、进程行为三类数据源中的至少两类
  - 不同数据源之间可通过时间（相差不超过 5 分钟）、源 IP、目标 URI 或进程 PID 建立关联 
  - 不适用于仅有单个弱信号（如仅一个可疑文件名）的场景

- 必要证据：

  - Web 日志中存在针对脚本文件（.php/.jsp/.aspx/.ashx）的异常 POST 请求，且请求参数包含 Base64、十六进制或密文特征 
  - 文件系统中对应 URI 路径下存在新增或最近修改的脚本文件，修改时间与 POST 请求时间差在 5 分钟以内
  - 脚本文件内容包含高危函数（如 PHP 的 `eval(`、`assert(`、`system(`；JSP 的 `Runtime.exec(`、`getRuntime()`；ASPX 的 `Process.Start(`、`Evaluate(`）
  - Web 进程（如 httpd、nginx、w3wp、java）创建了非预期的子进程（如 cmd.exe、bash、sh、powershell），且子进程启动时间与上述 POST 请求时间接近

- 调查步骤：

  1. 从 Web 日志中筛选目标时间窗口内的所有 POST 请求，标记参数中含编码/加密特征的条目
  2. 对每个可疑请求，提取 URI 路径，在文件系统中定位对应物理文件
  3. 检查该文件的创建/修改时间、大小变化、文件权限变化
  4. 读取文件内容，搜索高危函数关键字
  5. 检查 Web 进程的进程树，查找 POST 请求时间前后是否有新增子进程
  6. 若子进程存在，检查其命令行参数是否包含下载、反弹 Shell、信息收集等异常指令
  7. 汇总时间线，确认三类证据是否在同一时间窗口内形成关联链条

- 常见误报：

  - 业务系统使用 Base64 传输图片或序列化数据，会产生编码特征但属于正常功能
  - CMS 或框架自动生成的缓存/编译文件（如 PHP 的 opcache、JSP 的编译 class）可能被误认为新增脚本
  - 管理员通过 Web 终端插件或运维平台执行命令，会产生进程子进程但属于合法运维
  - 部分调试接口使用 eval 解析 JSONP 或模板表达式，需确认是否属于已知业务功能

- 禁止推断：

  - 禁止仅凭三类证据同时出现即自动判定为"攻击成功"，必须确认文件内容包含实际恶意功能
  - 禁止将时间接近推断为因果关系，需确认各证据指向同一资产和同一攻击时间窗口
  - 禁止在没有文件内容分析的情况下推断恶意功能类型
  - 禁止将调查建议（如"建议隔离主机"）作为已经发生的事实写入事件描述
  - 禁止将通用知识中的攻击手法直接填充为当前案例的攻击者行为

- 来源URL：

  - https://attack.mitre.org/techniques/T1505/003/
  - https://www.prophetsecurity.ai/blog/sharepoint-zero-day-vulnerability
  - https://beta.splunkresearch.com/endpoint/2d4470ef-7158-4b47-b68b-1f7f16382156/
  - https://feed.craftedsignal.io/briefs/2026-06-web-server-command-execution/

- 来源等级：

  - MITRE ATT&CK：A
  - 安全厂商技术分析/安全厂商检测规则：B

- 关联案例：

  - case9（强证据组合正向案）
  - case3（已有案例中含 IIS + ASPX 场景）



## 知识ID：WSK-002

- 主题：文件证据检查 - 可疑脚本文件识别

- 适用条件：

  - 已获取目标 Web 服务器的文件系统访问权限
  - 已知 Web 根目录路径（如 /var/www/html、C:\inetpub\wwwroot、/usr/local/tomcat/webapps）
  - 已有可疑文件路径或文件名线索（来自告警、日志或扫描结果）
  - 不适用于无法访问文件系统的场景

- 必要证据：

  - 文件路径位于 Web 根目录或其子目录下，可通过 HTTP 直接访问
  - 文件扩展名为 Web 脚本类型：.php、.jsp、.aspx、.asp、.ashx、.asmx、.jspx
  - 文件创建或修改时间与已知攻击时间窗口吻合（差异不超过 30 分钟）
  - 文件内容包含以下高危函数之一：
  - PHP：`eval(`、`assert(`、`system(`、`exec(`、`shell_exec(`、`passthru(`、`popen(`、`proc_open(` 
  - JSP：`Runtime.exec(`、`getRuntime(`、`ProcessBuilder(`
  - ASPX：`Process.Start(`、`Evaluate(`、`ScriptControl`
  - 文件权限异常（如 777、可写可执行）

- 调查步骤：

  1. 根据线索定位文件完整路径，确认其在 Web 根目录下的位置
  2. 使用 `stat`（Linux）或 `fsutil`（Windows）获取文件的创建时间、修改时间、访问时间
  3. 检查文件权限，确认是否被设置为可执行
  4. 使用 `cat`/`type` 读取文件内容，搜索高危函数关键字 （evidence3）
  5. 对比文件哈希值与已知 WebShell 样本库（如能找到）
  6. 检查同一目录下是否存在其他可疑文件（时间接近的批量落盘）
  7. 检查文件所有者，确认是否与 Web 进程用户（如 www-data、IUSR）一致

- 常见误报：

  - CMS 系统核心文件包含 `eval(` 但属于正常功能（如 WordPress 的 `eval` 用于模板解析）
  - 框架缓存文件（如 Twig、Smarty 编译模板）包含可执行代码片段
  - 日志或备份文件（.log、.bak）包含 HTTP 请求正文快照，其中可能记录攻击 payload 但不具备执行能力
  - 管理员上传的调试工具（如 phpinfo.php、test.jsp）包含系统函数

- 禁止推断：

  - 禁止仅凭文件名可疑（如 shell.php）即判定为 WebShell，必须有内容分析支撑
  - 禁止将文件存在等同于文件已被执行，执行需要 HTTP 请求记录支撑
  - 禁止将高危函数出现等同于恶意攻击，需排除合法业务用途

- 来源URL：

  - [Server Software Component: Web Shell, Sub-technique T1505.003 - Enterprise | MITRE ATT&CK&reg;](https://attack.mitre.org/techniques/T1505/003/)（MITRE ATT&CK Web Shell 技术框架）
  - https://www.cisa.gov/eviction-strategies-tool/info-countermeasures/CM0106?utm_source=openai)（CISA 官方 Web Shell 检测与清除指南）
  - https://safeguard.sh/resources/blog/php-webshell （PHP WebShell 检测方法）

- 来源等级：
  - MITRE ATT&CK：A
  - CISA 官方指南：A
  - Safeguard 技术分析：B

- 关联案例：

  - case9（强证据组合，涉及文件修改 + 进程创建）
  - case8（仅文件名可疑，无文件内容分析）



## 知识ID：WSK-003

- 主题：Web日志证据检查 - 异常请求识别

- 适用条件：

  - 已获取 Web 服务器访问日志（Apache access.log、IIS W3C 日志、Nginx access.log）
  - 已知目标时间窗口（来自告警时间或事件发生时间）
  - 已知 Web 根目录路径，用于关联日志中的 URI 与文件系统
  - 不适用于无日志记录或日志轮转已覆盖的场景

- 必要证据：

  - 针对脚本文件（.php、.jsp、.aspx、.ashx）的异常 POST 请求
  - 请求参数包含编码/加密特征：Base64 长字符串、十六进制、高熵值密文
  - 请求 User-Agent 异常（如固定为 `Mozilla/4.0`、包含 `AntSword`、`Weevely` 等工具标识）
  - 请求频率异常（单 IP 短时间大量请求、状态码多为 200）
  - 请求 URI 指向非业务路径或非常规文件名
  - 响应体大小异常（返回大量数据或编码数据）
  - 请求来源 IP 与正常业务流量模式不符

- 调查步骤：

  1. 按时间窗口筛选目标时间段内的所有 HTTP 请求
  2. 筛选针对可执行脚本文件的 POST 请求
  3. 检查请求参数中是否包含 Base64、十六进制或加密特征
  4. 统计单 IP 的请求频率和访问模式，识别异常集中度
  5. 关联日志中的 URI 与文件系统中的对应文件，确认文件是否存在及修改时间
  6. 检查响应状态码和响应体大小，识别数据外传特征
  7. 对比 User-Agent 与正常业务流量基线，识别异常

- 常见误报：

  - API 接口使用 Base64 传输图片或序列化数据，产生编码特征但属于正常功能
  - 搜索引擎爬虫或扫描器产生大量请求，但无后续恶意行为
  - 业务系统的长参数请求（如 JSON 序列化数据）被误认为加密 payload
  - 管理后台的批量操作产生高频 POST 请求

- 禁止推断：

  - 禁止仅凭 POST 请求存在即判定为 WebShell 通信，需确认请求与文件落地的关联
  - 禁止将 Base64/编码特征直接等同于恶意 payload，需确认解码后的内容
  - 禁止将单一日志条目放大为完整攻击链

- 来源URL：

  - [Web Shell Detection via Server Behavior and File Execution Chains, Detection Strategy DET0394 | MITRE ATT&CK&reg;](https://attack.mitre.org/detectionstrategies/DET0394/#pane-Windows#1)（MITRE Web Shell 检测策略，含日志分析）
  - https://www.cisa.gov/eviction-strategies-tool/info-countermeasures/CM0106 （CISA 日志检测方法）

- 来源等级：

  - MITRE ATT&CK：A
  - CISA 官方指南：A

- 关联案例：

  - case9（异常 POST + 文件修改 + 进程创建组合）
  - case7（Base64 编码参数但无恶意行为，用于排除误报）



## 知识ID：WSK-004

- 主题：进程证据检查 - Web进程异常行为识别

- 适用条件：

  - 已获取目标 Web 服务器的进程列表或进程创建日志
  - 已识别 Web 服务进程（如 w3wp.exe、httpd、nginx、java、php-cgi.exe）
  - 已知可疑时间窗口（来自日志告警或文件修改时间）
  - 不适用于无法获取进程信息的容器化或无进程审计环境

- 必要证据：

  - Web 服务进程（如 w3wp.exe、httpd.exe、nginx.exe、php.exe、tomcat.exe）创建了非预期的子进程
  - 子进程为命令行解释器或脚本解释器：cmd.exe、powershell.exe、bash、sh、python、cscript.exe、wscript.exe
  - 子进程启动时间与 Web 日志中的异常 POST 请求时间接近（差异不超过 10 秒）
  - 子进程命令行参数包含可疑指令（如 whoami、ipconfig、net user、curl、wget、nc）
  - Web 进程的文件写入行为（如 w3wp.exe 向 Web 目录写入脚本文件）

- 调查步骤：

  1. 使用进程监控工具（如 Sysmon、auditd）获取 Web 服务进程的进程树
  2. 筛选 Web 进程（w3wp.exe、httpd、nginx、php-cgi.exe、tomcat.exe）创建的子进程
  3. 检查子进程名称是否为命令行/脚本解释器
  4. 提取子进程的命令行参数，识别敏感指令
  5. 将子进程启动时间与 Web 日志中的异常请求时间进行关联
  6. 检查 Web 进程是否有向 Web 目录写入文件的操作
  7. 确认子进程的执行结果是否通过 HTTP 响应返回

- 常见误报：

  - CMS 系统的后台任务通过 Web 进程调用脚本（需确认是否为已知计划任务）
  - 管理员通过 Web 终端插件或运维平台执行命令
  - Web 应用调用外部工具处理上传文件（如图片处理调用 ImageMagick）
  - 调试或监控工具的正常行为

- 禁止推断：

  - 禁止将 Web 进程创建任何子进程即判定为 WebShell，需确认子进程为命令行解释器
  - 禁止将单次进程创建事件独立判定，需与日志和文件证据关联
  - 禁止在无命令行参数的情况下推断攻击意图

- 来源URL：

  - https://www.cisa.gov/eviction-strategies-tool/info-countermeasures/CM0106 （CISA 官方 WebShell 检测与清除策略指南）
  - https://github.com/SigmaHQ/sigma/tree/master/rules/windows/process_creation/proc_creation_win_webshell_susp_process_spawned_from_webserver.yml （Sigma 社区检测规则：Web 进程创建可疑子进程）

- 来源等级：

  - CISA 官方指南：A
  - Sigma 社区规则库：B

- 关联案例：

  - case9（w3wp.exe 创建 cmd.exe /c whoami，为核心进程证据）



## 知识ID：WSK-005

- 主题：PHP WebShell 识别特征

- 适用条件：

  - 目标 Web 服务器运行 PHP 环境（Apache + mod_php、Nginx + PHP-FPM、IIS + PHP）
  - 已获取文件系统访问权限，可读取 .php 文件内容
  - 已有可疑 PHP 文件路径或文件名线索
  - 不适用于无文件内容分析权限的场景

- 必要证据：

  - PHP 文件包含以下高危函数之一：`eval(`、`assert(`、`system(`、`exec(`、`shell_exec(`、`passthru(`、`popen(`、`proc_open(`
  - 动态变量函数调用：函数名来自请求参数（如 `$_GET['func']($_POST['cmd'])`）
  - 包含反引号执行（`` `$_POST['cmd']` ``）
  - 包含代码混淆特征：`base64_decode(`、`gzinflate(`、`str_rot13(` 链式调用
  - 文件位于非业务目录（如 uploads/、images/、tmp/、cache/）
  - 文件名伪装（如 avatar.jpg.php、wp-conf1g.php）

- 调查步骤：

  1. 使用 grep 扫描 Web 根目录下的 .php 文件，搜索高危函数关键字
  2. 检查文件是否包含 `base64_decode` 等混淆函数
  3. 检查文件路径是否位于 uploads、cache、tmp 等非代码目录
  4. 检查文件名是否使用双扩展名或伪装成非脚本文件
  5. 检查文件修改时间是否与已知攻击时间窗口吻合
  6. 检查文件是否可通过 HTTP 直接访问（尝试请求该文件）
  7. 若可访问，检查响应是否包含系统信息或命令执行结果

- 常见误报：

  - CMS（WordPress、Drupal、Joomla）核心文件包含 `eval(` 用于模板解析
  - 框架缓存/编译文件（Twig、Smarty）包含可执行代码片段
  - 日志或备份文件包含攻击 payload 但不具备执行能力
  - 合法的调试或性能监控工具使用系统函数

- 禁止推断：

  - 禁止仅凭单个高危函数出现即判定为 WebShell，需排除已知业务用途
  - 禁止仅凭文件名可疑即判定为恶意，需内容分析支撑
  - 禁止将混淆特征等同于攻击成功，需确认文件可被访问和执行

- 来源URL：

  - https://next.d3fend.mitre.org/offensive-technique/attack/T1505.003/ （MITRE ATT&CK 官方技术文档，提供 Web Shell 通用技术框架与检测原则）
  - https://www.php.net/manual/en/function.eval.php （PHP 官方手册，说明 eval() 函数可执行任意 PHP 代码，是高危风险函数）

- 来源等级：

  - MITRE ATT&CK：A
  - PHP 官方手册：A

- 关联案例：

  - case9（PHP 场景下的文件修改 + 进程创建组合）
  - case8（仅文件名 shell.php 可疑，需内容分析确认）



## 知识ID：WSK-006

- 主题：JSP WebShell 识别特征

- 适用条件：

  - 目标 Web 服务器运行 Java 环境（Tomcat、WebLogic、JBoss、Jetty）
  - 已获取文件系统访问权限，可读取 .jsp/.jspx 文件内容
  - 已有可疑 JSP 文件路径或文件名线索
  - 不适用于无文件内容分析权限的场景

- 必要证据：

  - JSP 文件包含 `Runtime.getRuntime().exec(` 或 `Runtime.exec(`
  - JSP 文件包含 `ProcessBuilder(` 类
  - JSP 文件包含 `request.getParameter(` 获取外部输入并传递给执行函数
  - 文件包含反射调用或类加载器操作：`getClassLoader()`、`defineClass(`
  - 文件包含 `<%@ page import=` 指令导入关键包
  - 文件位于 Web 应用目录（如 webapps/、ROOT/、/WEB-INF/ 上级目录）
  - 文件名伪装或使用非标准命名

- 调查步骤：

  1. 使用 grep 扫描 Web 应用目录下的 .jsp/.jspx 文件，搜索 `Runtime.getRuntime()` 关键字
  2. 搜索 `ProcessBuilder` 关键字
  3. 检查文件是否包含 `request.getParameter(` 与执行函数的组合
  4. 检查文件是否通过反射调用 `defineClass` 加载恶意字节码
  5. 检查文件路径是否位于可公开访问的 Web 目录
  6. 检查文件修改时间是否与已知攻击时间窗口吻合
  7. 检查访问日志中是否存在包含 `cmd=` 参数的 JSP 请求

- 常见误报：

  - 合法的管理后台或调试接口使用 Runtime.exec() 执行系统命令
  - 应用监控或健康检查功能调用系统命令获取状态信息
  - 运维自动化脚本部署的 JSP 文件包含进程调用

- 禁止推断：

  - 禁止仅凭 `Runtime.exec(` 出现即判定为 WebShell，需确认输入来源是否可控
  - 禁止将 `ProcessBuilder` 单独出现判定为恶意，需检查是否接收外部输入
  - 禁止在无文件内容分析的情况下仅凭文件名判定

- 来源URL：

  - https://www.anquanke.com/post/id/214435 （安全客技术文章，详细分析 JSP WebShell 的函数调用、反射调用及字节码加载技术）
  - http://netinfo-security.org/CN/abstract/abstract8097.shtml （《信息网络安全》2025年学术论文，提出专门针对 PHP 与 JSP 类型 WebShell 的高效检测方法，JSP 检测准确率达 98.93%）
  - https://wap.cnki.net/touch/web/Journal/Article/XXAQ202502008.html （知网收录论文，研究基于 BERT 语义特征的 AST 级 WebShell 检测方法，涵盖 JSP 类型检测）

- 来源等级：

  - 《信息网络安全》学术论文：B
  - 知网收录论文：B
  - 安全客技术分析：B

- 关联案例：

  - case9（JSP 场景下的异常 POST + 文件修改组合）



## 知识ID：WSK-007

- 主题：ASPX WebShell 识别特征

- 适用条件：

  - 目标 Web 服务器运行 IIS 且支持 ASP.NET 环境
  - 已获取文件系统访问权限，可读取 .aspx/.ashx/.asmx 文件内容
  - 已有可疑 ASPX 文件路径或文件名线索
  - 不适用于无文件内容分析权限的场景

- 必要证据：

  - ASPX 文件包含 `System.Diagnostics.Process.Start(`
  - ASPX 文件包含 `Request["` 或 `Request.QueryString[` 获取外部输入
  - 文件包含 `ProcessStartInfo` 类
  - 文件包含 `ValidateRequest="false"`（禁用请求验证）
  - 文件包含 `UnsafeLoadFrom` 或反射调用
  - 文件位于 IIS Web 根目录（如 C:\inetpub\wwwroot\）
  - 文件名伪装或使用非标准命名

- 调查步骤：

  1. 使用 PowerShell 或 find 扫描 Web 根目录下的 .aspx/.ashx/.asmx 文件
  2. 搜索 `Process.Start(` 关键字
  3. 检查文件是否包含 `Request["` 与 `Process.Start(` 的组合
  4. 检查文件是否包含 `ValidateRequest="false"` 指令
  5. 检查 IIS 日志中是否有针对该文件的请求记录
  6. 检查 Windows 事件日志中 w3wp.exe 是否创建了 cmd.exe 等子进程
  7. 检查 `C:\Windows\Microsoft.NET\Framework\[version]\Temporary ASP.NET Files\` 目录下是否存在对应的编译后 DLL 文件

- 常见误报：

  - 合法的 ASP.NET 应用使用 Process.Start() 调用外部工具（需确认输入来源）
  - 管理员上传的调试或运维工具
  - 业务系统使用 Base64 传输数据但不执行命令

- 禁止推断：

  - 禁止仅凭 `Process.Start(` 出现即判定为 WebShell，需确认是否接收外部输入
  - 禁止将 `ValidateRequest="false"` 单独作为恶意证据，某些业务功能确实需要禁用验证
  - 禁止在无 IIS 日志关联的情况下推断文件已被执行

- 来源URL：

  - https://www.cyber.gc.ca/en/news-events/sharpviewstateking-stealthy-implant-framework （加拿大网络安全中心官方报告，详细分析 .NET 后门框架的 FileUpload、FileDelete、命令执行等行为模式，是 ASPX WebShell 分析的权威政府来源）
  - https://www.trendmicro.com/zh_tw/research/25/a/investigating-a-web-shell-intrusion-with-trend-micro--managed-xd.html （趋势科技真实事件调查报告，详细记录了 IIS 工作进程 w3wp.exe 创建 cmd.exe 和 powershell.exe 的 ASPX WebShell 攻击行为[citation:6]）
  - https://idocdown.com/app/articles/blogs/detail/3824（IIS 下 .soap 扩展 WebShell 技术分析，覆盖 ASP.NET 环境下的 WebService 类型 WebShell 检测要点）

- 来源等级：

  - 加拿大网络安全中心（Cyber Centre）：A
  - 趋势科技（Trend Micro）官方研究报告：A
  - Idocdown 技术分析：C

- 关联案例：

  - case9（IIS + ASPX 场景，w3wp.exe 创建 cmd.exe）
  - case3（已有案例中的 IIS + ASPX 场景）



## 知识ID：WSK-008

- 主题：合法业务误报 - 常见误报场景识别
- 适用条件：
  - 检测系统（如WAF、主机安全扫描、文件完整性监控）产生WebShell告警
  - 告警依据为静态特征匹配（如文件名、函数名、代码片段）
  - 目标文件属于已知开源框架、CMS、插件或业务系统代码
  - 不适用于存在明确攻击行为证据（如异常进程、外连、文件落地后被执行）的场景
- 必要证据：
  - 告警文件位于已知第三方目录（如 vendor/、node_modules/、wp-includes/、wp-content/plugins/、ThinkPHP/）
  - 告警触发的特征为通用高危函数（如 eval()、system()、file_put_contents()）但函数位于框架核心逻辑中，非恶意调用
  - 文件哈希值与官方发布的原始文件一致（可通过官方源码包或GitHub仓库比对验证）
  - 告警文件路径为上传目录（如 uploads/、images/、avatars/）但文件扩展名为图片或压缩格式（.jpg/.png/.gif/.zip），非可执行脚本扩展名（.php/.aspx/.jsp）
  - 文件修改时间与系统更新或业务发布窗口一致
  - 文件所有者与已知运维账户或Web服务账户一致，无异常提权
- 调查步骤：
  1. 确认告警文件路径是否属于已知第三方目录
  2. 计算文件MD5/SHA256哈希值，与官方源码包或GitHub仓库比对
  3. 检查文件修改时间是否与业务发布窗口或系统更新时间吻合
  4. 确认文件扩展名和文件类型是否匹配（使用file命令或查看文件头）
  5. 检查文件中被标记为高危的代码是否实际接收外部输入
  6. 查看该文件在业务系统中的访问日志，确认是否为正常业务调用
  7. 检查同一目录下其他文件是否有异常时间修改或异常命名
- 常见误报：
  - WordPress/WooCommerce/Joomla/Drupal等CMS核心文件包含 eval() 用于模板解析或动态加载
  - ThinkPHP/Laravel等框架的缓存编译文件（如 template_c 目录下的 .php 文件）包含可执行代码
  - 日志或备份文件（.log、.bak）包含攻击请求payload但本身不具备执行能力
  - 业务系统通过上传图片马或序列化数据导致的静态特征匹配
  - 管理员部署的调试工具（phpinfo.php、test.php）未及时清理
  - 开源第三方库中已知但无害的代码片段被安全引擎标记为恶意
- 禁止推断：
  - 禁止仅凭文件名包含敏感词（如 upload、eval、shell）即判定为恶意
  - 禁止将特征匹配告警等同于攻击成功，必须结合行为证据
  - 禁止在未确认文件是否被远程访问的情况下推断攻击者已利用该文件
  - 禁止将误报场景中的通用特征（如文件上传）直接判为 WebShell
- 来源URL：
  - https://ieeexplore.ieee.org/document/11513222（IEEE 学术论文，系统性评估静态与动态 WebShell 检测工具的误报率差异，指出静态检测工具因特征覆盖范围广导致误报率高发）
  - https://blog.gitcode.com/19a35b69ea4cf0dbcb5afd18b63cc83e.html（CoreRuleSet 项目技术分析，Windows Defender 将 ModSecurity 规则文件误报为 PHP 后门的案例，说明静态特征匹配类安全产品的误报原理）
- 来源等级：
  - IEEE 学术论文（A类期刊会议）：B
  - CoreRuleSet 项目技术分析：C
- 关联案例：
  - case7（合法上传/Base64业务场景，含 Base64 参数但无恶意行为）
  - case8（仅文件名 shell.php 可疑，无其他证据支撑）



## 知识ID：WSK-009

- 主题：编码/加密参数的误报识别
- 适用条件：
  - 检测系统因请求参数包含Base64、十六进制、高熵值加密字符串等编码特征产生告警
  - 告警依据为静态特征匹配或参数内容形态异常，缺乏执行行为证据
  - 请求来源IP、时间、频次与正常业务流量模式相近
  - 不适用于同时存在异常进程创建、文件落地、外连等行为证据的场景
- 必要证据：
  - 请求参数包含Base64/十六进制编码的长字符串，但解码后为业务数据（如JSON结构、图片二进制、序列化对象），无恶意函数调用
  - 同一接口在业务时间窗口内有大量正常调用记录，编码参数格式一致
  - 请求响应为正常业务返回（如JSON状态码、HTML页面），无命令执行结果回显
  - 请求参数中的加密数据可被业务解密为合法内容（如JWT、加密的用户ID）
  - Accept-Charset字段包含Base64编码值，解码后无system()、exec()、echo()、certutil.exe等敏感关键字[citation:2]
  - 请求的URL路径为已知业务API端点，非可疑脚本文件路径
- 调查步骤：
  1. 对告警触发参数进行Base64/十六进制解码，检查解码后的内容
  2. 确认解码内容是否为业务数据结构（JSON、XML、序列化对象）
  3. 检查请求的URL路径是否属于已知业务API，而非可疑脚本文件
  4. 查询同一源IP在相似时间窗口内是否有相同接口的调用记录
  5. 检查请求响应体是否包含命令执行结果特征（如whoami、ipconfig输出）
  6. 确认请求参数中的加密数据是否能被业务正常解密
  7. 若解码后为混淆PHP/JSP代码，检查是否包含eval()、assert()、Runtime.exec()等恶意函数调用[citation:2]
- 常见误报：
  - 业务系统使用Base64传输图片、文件或序列化数据，产生编码特征但属于正常功能
  - JWT Token或加密的用户ID参数被WAF识别为高熵值加密字符串[citation:2]
  - API接口的JSON序列化数据包含Base64编码字段，被静态特征引擎误判为payload
  - 日志记录或错误调试信息中包含攻击payload的Base64编码快照，但文件本身不具备执行能力
  - 支付回调接口的测试环境使用内网地址，被SSRF检测算法误报[citation:7]
- 禁止推断：
  - 禁止将Base64/十六进制编码特征等同于WebShell恶意payload，必须解码验证内容
  - 禁止将Accept-Charset等请求头的Base64编码值直接判定为恶意，需解码检查敏感关键字[citation:2]
  - 禁止在未检查响应体的情况下推断命令已执行
  - 禁止将编码特征独立作为判定依据，须结合请求路径、业务上下文综合判断
- 来源URL：
  - https://www.topsec.com.cn/newsx/2251 （天融信威胁分析与响应报告，详细分析AntSword WebShell工具在Base64编码模式下的流量特征，说明如何区分正常编码与恶意编码）
  - https://mdr.skyeye.qianxin.com/forum/share/639 （奇安信攻防社区技术文章，从RFC4648标准出发，分析Base64编码在WAF绕过场景中的应用，帮助理解编码参数误报的技术根源）
- 来源等级：
  - 天融信官方技术分析：B
  - 奇安信攻防社区技术分析：B
- 关联案例：
  - case7（合法上传/Base64业务场景，含Base64编码参数但无恶意行为）
  - case9（强证据组合，编码参数配合进程创建等行为，与误报场景形成对比）



## 知识ID：WSK-010

- 主题：弱信号与证据不足 - 调查清单与处理策略
- 适用条件：
  - 调查仅存在单一或少量可疑线索（如一个可疑文件名、一次异常请求、一个可疑进程），缺乏完整的证据链
  - 已有线索不足以支撑正向判定，但也不能直接排除为误报
  - 需要一份标准化的调查清单来确定下一步动作
  - 不适用于已有明确正向证据组合的场景
- 必要证据：
  - 以下任一弱信号出现，且缺乏其他类别的证据支撑：
    - 文件层面：Web目录下出现新增脚本文件（.php/.jsp/.aspx），但无对应的HTTP请求记录或进程行为异常
    - 日志层面：Web日志中出现针对脚本文件的异常POST请求，但对应物理文件不存在或未被修改
    - 进程层面：Web服务进程（如w3wp.exe）创建了cmd.exe子进程，但无对应的文件修改或日志异常
    - 网络层面：Web服务器存在到外部IP的异常外连，但无法与特定文件或请求关联
    - 文件特征层面：仅通过静态特征匹配（如文件名包含`suspect`、`cmd`）产生告警，无行为证据
  - 调查时间窗口内仅有单一线索，跨数据源无法建立关联
  - 已有的线索可能来自扫描器、爬虫、正常业务或误报
- 调查步骤：
  1. 从触发告警的弱信号出发（如可疑文件路径、异常请求URL、可疑进程名），记录该线索的完整上下文
  2. 扩展调查范围：检查同一时间窗口（前后5分钟）内是否有其他关联事件：
     - 是否有针对同一URI的POST请求（如果线索来自文件）
     - 是否有文件修改或创建（如果线索来自日志）
     - 是否有进程创建或网络连接（如果线索来自文件）
     - 是否有计划任务、crontab或服务配置变更
  3. 检查该线索是否可被正常业务解释：
     - 文件是否为已知CMS/框架的核心文件
     - 请求是否来自已知业务API的正常调用
     - 进程是否属于已知的合法运维工具或计划任务
  4. 检查该线索是否与最近的业务发布、系统更新或运维操作时间吻合
  5. 若跨数据源关联后仍无其他发现，标记为“证据不足”，记录证据缺口清单
  6. 提供明确的下一步调查建议（见“处置建议边界”），而非直接判定为攻击或误报
- 常见误报：
  - 扫描器或爬虫产生异常请求日志，但未造成文件落地或进程执行
  - CMS更新或插件安装导致Web目录新增文件，被误判为WebShell落盘
  - 管理员通过Web终端或运维平台执行命令，产生进程创建事件
  - 业务系统调用外部API产生外连，被误判为C2通信
- 禁止推断：
  - 禁止将单一弱信号升级为“攻击成功”或“已植入WebShell”
  - 禁止在没有跨数据源关联的情况下推断攻击路径
  - 禁止在没有证据缺口补充的情况下给出高置信度判定
  - 禁止跳过调查清单直接进行清理或隔离操作
- 来源URL：
  - https://www.secrss.com/articles/10464 （安全内参译文，全面介绍WebShell检测与应急响应的完整流程，明确“证据关联是调查基础”的核心原则）
- 来源等级：
  - 安全内参（SecRSS）编译：B
- 关联案例：
  - case8（仅文件名`shell.php`可疑，无其他证据，典型的弱信号场景）
  - case7（合法Base64业务，仅有编码参数异常，需排除误报）



## 知识ID：WSK-011

- 主题：工具查询失败 - 处理策略
- 适用条件：
  - 调查过程中使用的安全工具（如WebShell查杀工具、日志分析脚本、进程监控工具）执行失败或返回错误
  - 失败原因可能为权限不足、路径不存在、依赖缺失、超时、环境配置问题等
  - 需要区分“工具失败”与“未发现风险”，避免将工具错误等同于安全结论
  - 不适用于工具正常运行但返回空结果的场景（见WSK-012）
- 必要证据：
  - 工具返回明确的错误码或错误信息（如“Connection Timeout”、“Permission Denied”、“Path Not Found”）
  - 工具执行环境与预期不符（如缺少/bin/bash、glibc版本不兼容、架构不匹配）
  - 目标路径不存在或无访问权限
  - 工具执行超时（如检测单个文件运行时长超过设定阈值）
  - 网络连接问题导致工具无法与目标通信
  - 工具依赖的组件或服务未正常运行
- 调查步骤：
  1. 记录工具返回的完整错误信息（错误码、错误描述）
  2. 检查工具执行环境：确认/bin/bash是否存在、glibc版本是否兼容、系统架构是否匹配
  3. 检查目标路径是否存在以及当前用户是否有读取/执行权限
  4. 检查网络连通性：确认工具与目标服务器/容器之间的网络是否正常
  5. 检查是否因负载均衡、代理或防火墙导致连接超时
  6. 检查工具版本是否与当前环境兼容
  7. 根据错误类型采取对应补救措施（见下方处置建议）
  8. 在调查报告中明确标注“工具失败”状态，不作为安全结论的依据
- 常见误报：
  - 工具返回的错误信息被误判为"目标不存在"或"无风险"，但实际是工具自身执行失败
  - 超时错误被误判为"目标无响应"，但实际是网络代理或防火墙问题
  - 权限错误被误判为"文件不存在"，但实际是当前用户权限不足
  - 容器环境中工具缺失被误判为"目标环境不存在"
- 禁止推断：
  - 禁止将工具执行失败等同于“未发现WebShell”或“环境安全”
  - 禁止在工具失败的情况下给出“无风险”结论
  - 禁止跳过失败工具对应的检测项而不做任何替代检查
  - 禁止将超时错误等同于目标不存在
- 来源URL：
  - https://cloud.tencent.com/developer/article/2345678 （腾讯云WebShell排查指南的技术文章，讲解WebShell检测工具失败时的替代排查方案）
- 来源等级：
  - 安全厂商技术分析：B
- 关联案例：
  - case8（仅有弱信号时，工具查询失败可能导致误判“无风险”，需注意）
  - case9（正向证据组合场景中，工具失败不应影响对已有证据的判断）



## 知识ID：WSK-012

- 主题：查询返回空集 - 处理策略
- 适用条件：
  - 调查过程中执行的查询（如文件搜索、日志检索、进程列表、网络连接检查）返回空结果
  - 空结果可能由以下原因导致：数据确实不存在、查询条件设置错误、数据源未正确采集、查询时间窗口或范围不匹配
  - 需要区分“空集”与“安全”，避免将查询无结果等同于“未发现风险”
  - 不适用于工具执行失败或返回错误的场景（见WSK-011）
- 必要证据：
  - 查询语句或工具返回空结果（0条记录、0个匹配、No results found）
  - 查询条件（时间范围、路径、关键字、PID、IP等）已明确记录
  - 查询的数据源（日志文件路径、数据库表、API端点）在目标系统上实际存在
  - 已知该数据源在目标时间窗口内应有数据的基线（如正常业务流量、日志轮转周期）
- 调查步骤：
  1. 检查查询条件是否设置正确：时间范围是否覆盖目标窗口、路径是否指向正确目录、关键字是否拼写正确
  2. 验证数据源本身是否可用：确认日志文件是否存在且可读、数据库表是否有数据、API接口是否响应正常
  3. 确认日志轮转策略：检查目标时间窗口的日志是否已被轮转或清理（如访问日志保留周期7天，但查询时间窗口为14天前）
  4. 检查数据采集状态：确认采集代理（如Filebeat、Sysmon、auditd）在目标时间窗口内是否正常运行
  5. 检查目标资产在查询时间窗口内是否处于运行状态（如虚拟机已关机、容器已销毁）
  6. 使用更宽泛的条件进行验证性查询（如扩大时间范围至前后24小时、使用通配符匹配），确认是否真无数据还是条件过严
  7. 若仍返回空结果，在调查报告中记录：查询内容、查询条件、数据源状态、以及“未在该维度发现证据”的结论
- 常见误报：
  - 查询条件过于严格导致空结果，实际数据存在（如时间范围仅覆盖了告警精确秒，但日志时间戳存在毫秒偏差）
  - 日志轮转策略导致目标时间窗口的日志已被归档，但未检查压缩日志文件
  - 采集代理在目标时间窗口内临时故障，导致数据缺失被误认为"无攻击流量"
  - 容器销毁后查询数据返回空集，但实际攻击已发生
- 禁止推断：
  - 禁止将单次查询空集直接解读为“攻击未发生”或“环境安全”
  - 禁止在没有验证数据源可用性和查询条件正确性的情况下得出结论
  - 禁止在空集时跳过替代数据源（如主要日志缺失时检查备份日志或归档）
  - 禁止将不同资产、不同时间窗口的空集合并为“整体安全”
- 来源URL：
  - https://www.secrss.com/articles/15591 （安全内参编译，完整展示WebShell检测与响应的十大策略，包括日志数据源状态检查和空结果处理流程）
  - https://www.freebuf.com/articles/network/393490.html （FreeBuf技术文章，详细阐述内存马注入WebShell的检测难点，强调无法定位来源、排查时过滤条件不准确等空结果场景的处理方法）
- 来源等级：
  - 安全内参编译：B
  - FreeBuf技术社区：B
- 关联案例：
  - case8（仅文件名可疑，查询访问日志返回空集，不能直接排除WebShell风险，需进一步检查文件内容和其他数据源）
  - case10（SSH暴力破解事件，查询Web日志返回空集，与预期一致，可支撑out_of_scope判定）



## 知识ID：WSK-013

- 主题：WebShell 植入方式
- 适用条件：
  - 调查需要追溯 WebShell 的初始入侵途径，以确定漏洞根因和修复范围
  - 已确认服务器上存在 WebShell 文件或内存马活动迹象
  - 需要根据 WebShell 特征推断可能的植入方式
  - 不适用于未发现任何 WebShell 痕迹的场景
- 必要证据：
  - 确认存在 WebShell 文件（.php/.jsp/.aspx/.asp 等）或内存马活动（如动态注册的 Filter/Servlet）
  - 记录 WebShell 文件在文件系统中的路径、创建/修改时间
  - 记录服务器上已知的漏洞信息（如未修复的 CVE、弱密码、过期软件版本）
  - 记录 Web 访问日志中 WebShell 文件创建前后的异常请求模式
  - 记录可疑的上传活动日志或数据库操作日志
  - 确认服务器是否存在异常的计划任务或启动项（持久化机制）
- 调查步骤：
  1. 记录 WebShell 文件的完整路径、文件名、创建时间、修改时间
  2. 检查 Web 访问日志，在文件创建时间前后查找针对上传接口、文件操作接口的异常请求
  3. 检查服务器上运行的服务版本（如 PHP、Tomcat、IIS），与已知存在漏洞的版本进行比对
  4. 检查应用配置（如 web.config、.htaccess），确认是否存在文件上传类型限制被篡改、禁用请求验证（ValidateRequest="false"）等异常配置
  5. 检查是否存在异常的计划任务（cron job）或启动项，这些可能被用于 WebShell 的持久化或重装机制
  6. 检查数据库操作日志，确认是否存在 SELECT ... INTO OUTFILE 等导出语句
  7. 若未发现明确的文件落地上传记录，结合服务器上的内存马特征（如无对应文件的恶意请求路径），推断是否通过反序列化漏洞注入
- 常见误报：
  - 文件上传功能被正常业务使用，但被误判为 WebShell 植入途径
  - 系统更新或运维操作导致文件时间变更，被误认为植入时间
  - 计划任务为正常的系统维护任务，被误判为持久化机制
  - 第三方库或框架自带的代码生成功能，被误认为 SQL 注入导出 Shell
- 禁止推断：
  - 禁止仅凭文件名（如 shell.php）推断植入方式，必须有对应的日志或漏洞证据支撑
  - 禁止将文件修改时间等同于植入时间，需排除正常业务操作、文件迁移、备份恢复等情况
  - 禁止在未检查服务器漏洞和日志的情况下，推断植入方式
  - 禁止将单个漏洞的存在等同于该漏洞已被用于植入 WebShell，必须有植入行为证据
- 来源URL：
  - https://nosec.org/home/detail/5049.html （白帽汇安全研究院文章，详解JavaWeb内存马的实现技术、分类与注入原理，帮助理解无文件落地的WebShell植入方式）
  - https://cloud.tencent.com.cn/developer/article/1522105 （腾讯云开发者社区，系统分类讲解WebShell常见植入方式，包括上传漏洞利用、后台功能滥用、SQL注入导出、第三方代码预置后门等）
- 来源等级：
  - 白帽汇安全研究院：B
  - 腾讯云开发者社区：B
- 关联案例：
  - case9（强证据组合案例，涉及POST请求 + 文件修改 + 进程创建，可能是文件上传漏洞或SQL注入导致植入）
  - case10（SSH暴力破解，可能获取后台权限后植入WebShell，与植入方式中的后台功能滥用相关）



## 知识ID：WSK-014

- 主题：网络证据检查 - 外连与C2通信识别
- 适用条件：
  - 已确认或高度怀疑服务器上存在 WebShell 活动
  - 需要识别 WebShell 与攻击者控制端（C2）之间的网络通信痕迹
  - 已获取网络连接日志、防火墙日志、NetFlow 或 PCAP 数据
  - 不适用于无法获取网络流数据的场景
- 必要证据：
  - 目标服务器存在向外部 IP 发起的主动外连请求，目标端口为非标准端口（如 4444、8080、8888、53 等）或标准端口（80/443）
  - 外连流量与文件修改时间或 Web 访问日志中的异常 POST 请求时间相近
  - 流量中包含 Base64 编码、加密数据或命令执行结果回传的特征
  - 外连目标 IP 与已知恶意 IP 威胁情报匹配
  - Web 进程（w3wp.exe、httpd、nginx、java）作为发起连接的进程，而非系统正常进程
  - DNS 请求中包含疑似 DNS 隧道特征的长子域名（如 2b41f5a32c.example.com）
  - 出站流量大小异常，如明显大于正常的业务请求响应
- 调查步骤：
  1. 使用网络连接监控工具（如 `netstat -an`、`ss -tunp`、`lsof -i`）获取当前服务器上的所有网络连接
  2. 筛选 Web 服务进程（w3wp.exe、httpd、nginx、java）发起的对外连接
  3. 检查连接目标的 IP 地址和端口，与威胁情报（如 AlienVault OTX、微步在线）进行碰撞
  4. 检查流量内容是否有 Base64 编码、加密数据或命令执行结果回传的特征
  5. 检查 DNS 日志中是否存在异常的长子域名请求，这可能表示 DNS 隧道
  6. 计算出站流量大小，识别非业务时间段的异常流量峰值
  7. 综合文件证据、进程证据和时间线，建立“请求 - 执行 - 外传”的完整通信链条
- 常见误报：
  - 业务系统调用外部 API（如支付接口、短信网关、地图服务），产生合法外连
  - 服务器操作系统或软件自动更新连接外部软件源（如 yum、apt、Windows Update）
  - 监控 Agent（如 Zabbix、Nagios、Datadog）定期向监控服务器上报数据
  - CDN 或云服务商 IP 被误判为恶意 C2
  - Web 应用通过外连获取资源（如远程图片、字体库、前端 CDN 脚本）
- 禁止推断：
  - 禁止仅凭外连行为即判定为 C2 通信，需确认流量内容和进程发起者
  - 禁止在未检查业务合法外连的情况下，直接判定外连为恶意
  - 禁止将威胁情报匹配结果等同于“攻击已成功”，需结合其他证据确认实际危害
  - 禁止在无流量内容验证的情况下推断通信数据为 WebShell 命令
- 来源URL：
  -
  - https://www.freebuf.com/articles/others-articles/331442.html （FreeBuf技术文章，详细讲解使用Volatility进行内存马检测及恶意网络连接分析的方法）
  - https://securelist.com/soc-files-web-shell-chase/115714/ （卡巴斯基安全实验室真实事件分析报告，详细剖析了冰蝎WebShell在IIS进程中的网络通信特征，包括Base64编码、加密流量和进程行为分析）
  - https://blog.csdn.net/weixin_34391445/article/details/91780357 （CSDN技术社区，实战解析WebShell流量特征和攻击链还原过程，涵盖HTTP请求分析、异常连接识别和内网穿透流量检测）
- 来源等级：
  - 卡巴斯基安全实验室（Securelist）：A
  - FreeBuf技术社区：B
  - CSDN技术社区：C
- 关联案例：
  - case9（强证据组合中可能包含网络外连，用于形成完整攻击链）
  - case10（SSH暴力破解事件可能涉及外连，但需确认是否与WebShell相关）



## 知识ID：WSK-015

- 主题：处置建议边界 - 不同证据强度对应的响应动作
- 适用条件：
  - WebShell调查已经完成证据收集和分析，需要根据证据强度确定处置方案
  - 已经完成证据链的评估，明确了证据组合的完整性和可信度
  - Agent需要在不同证据强度下输出对应的处置建议，避免过度响应或响应不足
  - 不适用于证据仍在收集中、尚未完成调查的场景
- 必要证据：
  - 已完成对文件、日志、进程、网络四类证据的收集和分析
  - 已确定证据链的完整性等级（见下方“证据强度分级”）
  - 已排除常见误报场景（参照WSK-008和WSK-009）
  - 已确认WebShell类型（PHP/JSP/ASPX）和植入方式（参照WSK-005/006/007/013）
  - 已确认受影响资产的范围和业务重要性
- 调查步骤：
  1. 评估当前证据组合，对照“证据强度分级”确定所处等级
  2. 确认是否已完成误报场景排除（参照WSK-008、WSK-009）
  3. 根据证据强度等级，对照“处置动作”表确定建议的响应级别
  4. 评估受影响资产的业务重要性，判断是否需要调整处置级别
  5. 在采取任何处置动作前，先完成证据固定（文件副本、日志切片、进程快照）
  6. 输出处置建议时，明确标注证据强度等级和对应的动作依据
  7. 若证据强度不足以支持当前告警级别，建议降级或关闭告警
- 常见误报：
  - 将仅文件特征（Level 1）误判为严重攻击，导致不必要的业务中断
  - 在误报排除前直接升级处置级别（如未确认文件是否为CMS核心文件即隔离服务器）
  - 跨案例混淆：将弱信号案例（case8）与强证据案例（case9）的处置建议互换
  - 未完成取证即清除文件，丢失后续溯源分析的关键依据
- 禁止推断：
  - 禁止在证据强度不足时给出高风险处置建议（隔离、下线、重装系统）
  - 禁止在完成误报排除前升级处置级别
  - 禁止在取证完成前清除文件或关闭服务器
  - 禁止在确认进程执行证据后将处置仅限定于文件清除
  - 禁止将通用处置原则（如“发现WebShell立即隔离服务器”）直接套用于所有证据强度场景
- 来源URL：
  - https://blog.csdn.net/yiyiyi0322/article/details/162815312 （CSDN技术博客，基于冰蝎WebShell真实应急响应案例，详细阐述“先取证后处置”的标准化处置闭环流程，包括内存镜像、网络隔离、日志分析和分级响应策略
  - https://ieeexplore.ieee.org/document/11582332 （IEEE Xplore学术论文，研究基于规则和CodeBERT的WebShell编码检测方法，为不同证据强度下的检测与处置决策提供学术支撑）
- 来源等级：
  - IEEE Xplore学术论文：B
  - CSDN技术博客（实战案例分析）：C
- 关联案例：
  - case8（仅文件名可疑，对应Level 1处置建议）
  - case9（强证据组合，对应Level 3或Level 4处置建议）
  - case10（完全无关事件，对应Level 0处置建议）

