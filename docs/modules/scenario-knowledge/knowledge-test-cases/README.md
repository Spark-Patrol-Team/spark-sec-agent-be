# 知识评测案例

本目录保存6个**synthetic（人工构造/由公开材料改编）评测输入**，用于验证：

1. JSON能否被当前`SecurityEventInput`直接加载；
2. `knowledge_query`是否命中唯一运行时知识正文；
3. Agent是否把命中知识用于报告，同时避免把知识模板扩写成输入中不存在的事实；
4. 纯非WebShell负向输入是否会被错误套用WebShell知识。

这些JSON不是XDR原始响应，不是运行A/运行B，也不能作为真实平台事件证据。事件ID、IP、时间和置信度均为评测构造值。

## 唯一运行时知识源

- 知识正文：`src/sec_agent/deep_agent/knowledge/webshell-knowledge.md`
- 查询入口：`src/sec_agent/deep_agent/tools/knowledge.py::knowledge_query`
- 本目录不复制PR #8中的第二份知识正文。
- PR #8的5个问答样本不重复复制；其当前覆盖关系由`tests/test_knowledge_tool.py::TestKnowledgeQaCoverage`验证。

## 文件

| 文件 | 用途 |
|---|---|
| `case1.json`—`case3.json` | WebShell正向synthetic案例 |
| `case4.json`—`case5.json` | 证据不足/模拟工具失败案例 |
| `case6.json` | 纯非WebShell负向对照；不得补出WebShell结论 |
| `案例描述.md` | 输入性质、逐案判据和执行记录 |
| `来源矩阵.md` | 公开来源能够支持与不能支持的主张 |

## 输入字段

6个JSON均使用`SecurityEventInput.from_dict()`可直接读取的顶层结构。关键字段为：

```text
event_id, event_type, severity, timestamp,
source_ip, target_ip, alerts, evidence,
initial_verdict, confidence, triage, trace_id, run_id
```

## 可复制验证命令

在仓库根目录使用PowerShell：

```powershell
$env:PYTHONPATH = "src"
python -m unittest tests.test_knowledge_case_inputs -v
python -m unittest tests.test_knowledge_tool -v
```

前一条命令会实际用`SecurityEventInput.from_dict()`加载全部6案，并检查关键标识、唯一性以及case6不含WebShell证据；不是肉眼检查JSON字段。

本机LLM配置可用时，按最终PR头提交运行2个正向案例和case6负向对照：

```powershell
$env:PYTHONPATH = "src"
$env:TOOL_MODE = "mock"
python -m sec_agent.deep_agent.main --event docs/modules/scenario-knowledge/knowledge-test-cases/case1.json -o reports/case1.json
python -m sec_agent.deep_agent.main --event docs/modules/scenario-knowledge/knowledge-test-cases/case2.json -o reports/case2.json
python -m sec_agent.deep_agent.main --event docs/modules/scenario-knowledge/knowledge-test-cases/case6.json -o reports/case6.json
```

Agent运行必须记录最终PR头提交、退出码、生成的报告文件、工具调用和判定。`TOOL_MODE=mock`只证明本地代码契约与知识消费，不代表真实MCP或真实XDR成功。
