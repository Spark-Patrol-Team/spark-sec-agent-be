from typing import Dict, Any
from sec_agent.domain.models import ToolRequest, ToolResult

# 内存存储状态：key = session_id，value = 当前会话保存的状态数据
SESSION_STATE: Dict[str, Dict[str, Any]] = {}


def handle_stateful_mock(request: ToolRequest) -> ToolResult:
    """
    MVP有状态Mock工具
    session_id从params获取，不改动ToolRequest模型
    同session_id多次调用会保留会话状态；不同session互相隔离
    """
    params = request.params
    session_id = params.get("session_id")
    if not session_id:
        return ToolResult(
            call_id=request.call_id,
            trace_id=request.trace_id,
            event_id=request.event_id,
            tool_name=request.tool_name,
            action_name=request.action_name,
            success=False,
            error_message="stateful_mock缺少params.session_id",
            data=None
        )

    # 会话不存在就初始化空状态
    if session_id not in SESSION_STATE:
        SESSION_STATE[session_id] = {}

    current_state = SESSION_STATE[session_id]

    # ========== Mock业务逻辑 ==========
    input_data = params.get("input_data", {})
    # 把输入合并进会话状态，实现“记忆”
    current_state.update(input_data)
    # 写回内存
    SESSION_STATE[session_id] = current_state

    return ToolResult(
        call_id=request.call_id,
        trace_id=request.trace_id,
        event_id=request.event_id,
        tool_name=request.tool_name,
        action_name=request.action_name,
        success=True,
        error_message=None,
        data={
            "session_id": session_id,
            "current_session_state": current_state
        }
    )
