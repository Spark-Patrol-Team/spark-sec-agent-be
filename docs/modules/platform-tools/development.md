# 平台工具模块开发说明

## 代码位置

- `src/sec_agent/platforms/base.py`
- `src/sec_agent/platforms/fixed_sample.py`

## 接入方式

新增真实平台能力时优先新增适配器文件，不要让业务 service 直接依赖平台 SDK 或 HTTP 路径。

## 待补充

- `xdr_openapi.py`
- `mcp.py`
- `fastgpt.py`
- 错误码转换规则。

