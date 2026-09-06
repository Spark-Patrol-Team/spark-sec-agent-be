# 场景知识模块开发说明
负责人: development

## 代码位置

当前未单独实现代码模块，后续根据知识增强方案确定。

## 接入方式

优先作为风险研判和深度调查 Agent 的辅助能力接入。

## 待补充

- 知识来源。
- 知识更新流程。
- 与 FastGPT/OpenClaw 的关系。

## 今日新增 (2026-09-06)
### 2. 案例信号提取标注 (Case 1-10)
已完成对 10 个测试案例的信号提取规则标注：

- **Case 1-3 (正向变体)**: 提取 ASPX/Godzilla/Beima 特征信号；标记为 Confirmed WebShell。
- **Case 4-5 (证据不足)**: 提取查询超时/缺少资产信息；标记为 `weak_signal`。
- **Case 6 (非 WebShell 对照)**: 提取 XSS/隐藏管理员创建；不得提取 WebShell 确认信号。
- **Case 7 (合法业务)**: 提取头像上传/Base64 用户名；不得误判为 WebShell，标记为 `weak_signal`。
- **Case 8 (弱信号)**: 提取 `shell.php` 文件名；无访问记录，标记为 `weak_signal`。
- **Case 9 (强组合)**: 提取异常 POST + 文件修改 + w3wp 创建 cmd 链条；标记为 Confirmed WebShell。
- **Case 10 (域外事件)**: 提取 SSH 爆破记录；排除 WebShell 信号。


