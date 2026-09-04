# CD 部署说明

## 结论

当前仓库使用 GitHub Actions 完成持续交付：

- 推送到 `main` 时，先跑测试和 OpenAPI 一致性检查，再构建 Docker 镜像并推送到 GHCR，然后自动通过 SSH 部署到服务器。
- 推送 `v*` tag 时，只测试、构建镜像并推送到 GHCR，不自动部署。
- 手动触发 `CD` workflow 且勾选 `deploy=true` 时，也会通过 SSH 登录服务器，上传生产 compose 文件，拉取指定镜像并重启 `api` 服务。
- 生产部署只负责后端 API 容器，不在生产 compose 中内置 MySQL 默认密码；生产数据库、XDR 联动码、LLM Key 等敏感配置必须由服务器 `.env` 或密钥系统提供。

## 触发规则

| 触发方式 | 行为 |
|---|---|
| push 到 `main` | 测试、检查 OpenAPI、构建镜像、推送 `latest` 和 `sha-<短SHA>`，然后自动 SSH 部署 |
| push `v*` tag | 测试、检查 OpenAPI、构建镜像、推送 tag 镜像和 `sha-<短SHA>`，不自动部署 |
| 手动 workflow_dispatch，`deploy=false` | 测试、构建并推送镜像，不部署 |
| 手动 workflow_dispatch，`deploy=true` | 测试、构建并推送镜像，然后 SSH 部署 |

## GitHub Secrets

部署到服务器前，需要在仓库 Settings -> Secrets and variables -> Actions 中配置：

| Secret | 必需 | 说明 |
|---|---|---|
| `CD_SSH_HOST` | 是 | 部署服务器 IP 或域名 |
| `CD_SSH_USER` | 是 | 部署用户，需要具备 Docker 和 docker compose 权限 |
| `CD_SSH_KEY` | 是 | 部署用户的 SSH 私钥 |
| `CD_SSH_PORT` | 否 | SSH 端口，未配置时默认 `22` |
| `CD_DEPLOY_PATH` | 是 | 服务器部署目录，例如 `/opt/spark-sec-agent-be` |
| `GHCR_USERNAME` | 是 | 服务器拉取 GHCR 镜像使用的用户名 |
| `GHCR_TOKEN` | 是 | 服务器拉取 GHCR 镜像使用的 token，需要 `read:packages` 权限 |

`GITHUB_TOKEN` 由 GitHub Actions 自动提供，用于 workflow 内部推送镜像到 GHCR。

## 服务器前置条件

服务器需要提前准备：

- 已安装 Docker 和 Docker Compose v2。
- `CD_SSH_USER` 可以执行 `docker compose`。
- `CD_DEPLOY_PATH` 下存在生产 `.env` 文件。
- `.env` 中已配置真实运行所需变量，例如 `APP_ENV=prod`、`STORAGE_BACKEND`、MySQL、XDR、LLM 或 MCP 配置。

生产 `.env` 示例结构：

```text
APP_ENV=prod
STORAGE_BACKEND=mysql
PLATFORM_BACKEND=xdr_openapi
INVESTIGATION_BACKEND=tool_mock

MYSQL_HOST=<生产数据库地址>
MYSQL_PORT=3306
MYSQL_USER=<生产数据库用户>
MYSQL_PASSWORD=<生产数据库密码>
MYSQL_DATABASE=sec_agent
MYSQL_AUTO_CREATE_SCHEMA=false

XDR_BASE_URL=<真实 XDR 地址>
XDR_AUTH_TYPE=auth_code
XDR_AUTH_CODE=<真实联动码>
XDR_ALERTS_PATH=/api/xdr/v1/alerts/list
XDR_ALERT_PAGE_SIZE=50
XDR_ALERT_MAX_PAGES=20
XDR_ALERT_START_TIMESTAMP=1787155200
XDR_VERIFY_SSL=false
XDR_ALLOW_FIXED_SAMPLE_FALLBACK=false
```

真实密钥和内网地址不要提交到仓库。

## 手动部署步骤

1. 进入 GitHub Actions 的 `CD` workflow。
2. 点击 `Run workflow`。
3. `deploy` 选择 `true`。
4. `image_tag` 可留空，默认部署当前提交对应的 `sha-<短SHA>` 镜像；也可以填写已有镜像 tag。
5. workflow 完成后，在服务器检查服务状态：

```text
cd /opt/spark-sec-agent-be
APP_IMAGE=ghcr.io/<owner>/<repo>:<tag> docker compose ps
APP_IMAGE=ghcr.io/<owner>/<repo>:<tag> docker compose logs --tail=100 api
```

## 回滚方式

回滚时重新手动触发 `CD` workflow：

- `deploy=true`
- `image_tag` 填写上一个稳定镜像 tag，例如 `sha-xxxxxxx` 或 `v0.1.0`

workflow 会拉取该镜像并重启 `api` 服务。

## 验收检查

部署完成后至少检查：

```text
curl -s http://<server-host>:<api-port>/health
```

如果是 XDR 真实告警输入联调，再调用：

```text
curl -s -X POST 'http://<server-host>:<api-port>/runs' \
  -H 'Content-Type: application/json' \
  -d '{"source":"xdr","xdr_event_id":"alert-9fd0c034-ba09-4311-8360-cf1787206450"}'
```

预期结果：

```text
status=APPROVAL_REQUIRED
requested_source=xdr
effective_source=xdr_openapi
fallback_source=null
errors=[]
```

## 当前边界

- CD 已覆盖测试、OpenAPI 一致性检查、镜像构建、GHCR 推送和手动 SSH 部署。
- CD 不负责创建生产数据库，不负责写入真实 `.env`，不负责管理 XDR 联动码生命周期。
- 当前生产 compose 只启动 `api` 服务；MySQL 建议使用独立数据库或由运维单独管理。
- 真实 MCP 调查和真实处置动作尚未闭环时，生产 `.env` 不应开启真实高风险处置。
