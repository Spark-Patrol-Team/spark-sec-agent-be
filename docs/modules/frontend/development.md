# 前端模块开发说明

## 代码位置

当前仓库为后端项目（FastAPI），前端代码位置待确认。

## 如何打开"前端页面"

当前没有独立前端工程，交互入口为后端自带的 **Swagger UI**（把接口当页面用，可点击按钮驱动完整链路）：

```powershell
$env:PYTHONPATH = "src"; python -m uvicorn sec_agent.api.app:app --host 127.0.0.1 --port 8000
```

启动后在浏览器打开：

- **Swagger UI**（推荐，可交互调试）：http://127.0.0.1:8000/docs
- ReDoc 文档：http://127.0.0.1:8000/redoc

浏览器里用 Swagger 操作一遍完整链路：

1. `POST /runs` → body `{"source":"fixed_sample","sample_id":"webshell-001"}` → 返回 `event_id`。
2. `GET /events/{event_id}` 查看状态；若停在 `APPROVAL_REQUIRED`，用 `POST /events/{event_id}/approval` 审批（body 用 ASCII 字段，Windows curl 对中文 JSON 有编码问题）。
3. `GET /events/{event_id}/timeline` 看 9 步时间线；`GET /events` / `GET /metrics` 看汇总。

> 后端 CORS 已默认放行 `localhost:3000` / `localhost:5173`，真正的 Web 前端指向上述 REST 接口即可对接。

## 接入方式

后端最小接口（前端所需全部能力）：

- `GET /health`
- `POST /runs`
- `GET /events`
- `GET /events/{event_id}`
- `GET /events/{event_id}/timeline`
- `POST /events/{event_id}/approval`
- `GET /metrics`

## 联调记录（2026-08-26，真实 REST API）

- **tool_mock 后端**：`POST /runs` 全链走通至 COMPLETED（`APPROVAL_REQUIRED` → 审批 → 执行 → 验证），时间线 9 步完整。
- **auto 后端（真实 LLM deep_agent）**：真实调用 LLM + dbproxy MCP，8 次工具调用后证据不足，按设计停在 HUMAN_REQUIRED（转人工，不自动处置）。
- 详见 `docs/modules/investigation-agent/development.md`「前后端联调记录」。

## 待补充

- 前端仓库或目录。
- 页面字段需求。

