from sec_agent.domain.models import ToolRequest, ToolResult


def handle_xdr_query(request: ToolRequest) -> ToolResult:
    """
    MVP XDR原始日志查询工具
    依据平台定向验证统一结论，只返回已经验证通过的字段
    MVP：优先使用本地内置样例，暂不强依赖真实XDR OpenAPI接口
    """
    # params拿到入参，例如查询时间、事件过滤条件
    params = request.params

    # ========== MVP 演示：内置样例数据，后续可以对接仓库里的样例json文件 ==========
    mock_xdr_records = [
        {
            "event_time": "2026-08-20T10:22:30Z",
            "rule_name": "STA-SQL注入攻击",
            "risk_level": "high",
            "src_ip": "192.168.1.100",
            "dst_ip": "10.0.0.5",
            "src_port": 54321,
            "dst_port": 8080,
            "origin_log": "HTTP请求携带SQL注入payload",
            "asset_info": "web‑server‑01"
        }
    ]

    return ToolResult(
        call_id=request.call_id,
        trace_id=request.trace_id,
        event_id=request.event_id,
        tool_name=request.tool_name,
        action_name=request.action_name,
        success=True,
        error_message=None,
        data=mock_xdr_records
    )
