# AIHR Railway 部署手册

本文档用于把 AIHR 的公开合成数据演示版部署到 Railway。生产或真实 ATS 数据不在此部署范围内。

## 服务清单

在一个 Railway Project 中创建五个服务，名称建议保持如下：

| 服务 | 来源 | 是否公开 |
|---|---|---|
| `Postgres` | Railway PostgreSQL | 否 |
| `Redis` | Railway Redis | 否 |
| `api` | 当前 GitHub 仓库，`deploy/Dockerfile.api` | 是 |
| `dashboard` | 当前 GitHub 仓库，`deploy/Dockerfile.dashboard` | 是 |
| `worker` | 当前 GitHub 仓库，`deploy/Dockerfile.worker` | 否 |

Railway 不直接运行本仓库的 `compose.yaml`。Compose 是本机完整验证环境；云上每个服务独立部署。

## 人工步骤 1：连接 GitHub

1. 登录 Railway，创建 Empty Project。
2. 连接 GitHub 账号并授权 AIHR 仓库。
3. 分别创建 `api`、`dashboard`、`worker` 三个服务。
4. 在每个服务的 Variables 中填写下文对应的 `RAILWAY_DOCKERFILE_PATH`。

这一步需要仓库所有者在浏览器中完成 OAuth 授权，不能由本地脚本代替。

## 人工步骤 2：创建数据库与 Redis

在同一 Project 中添加 Railway PostgreSQL 和 Redis，并保留服务名 `Postgres`、`Redis`。不要给它们生成公网域名。

## API 变量

在 `api` 服务中配置：

```text
RAILWAY_DOCKERFILE_PATH=/deploy/Dockerfile.api
RAILWAY_HEALTHCHECK_TIMEOUT_SEC=300
PORT=8000
AIHR_CONFIG_FILE=config/config.Online.ini
AIHR_ENVIRONMENT=online
AIHR_DATABASE_URL=${{Postgres.DATABASE_URL}}
AIHR_CACHE_URL=${{Redis.REDIS_URL}}
AIHR_CACHE_PREFIX=aihr
AIHR_SEED_DEMO_DATA=true
AIHR_SYNTHETIC_SEED_RECOMMENDATIONS=10000
AIHR_SYNTHETIC_SEED_CANDIDATES=8000
AIHR_SYNTHETIC_SEED_JOBS=300
AIHR_ANALYSIS_PREWARM=true
AIHR_ANALYSIS_QUEUE_ENABLED=true
AIHR_ANALYSIS_QUEUE_NAME=aihr
AIHR_ASSISTANT_PROVIDER=deepseek
AIHR_ASSISTANT_BASE_URL=https://api.deepseek.com
AIHR_ASSISTANT_MODEL=deepseek-chat
AIHR_ASSISTANT_API_KEY=<在 Railway 中填写，不要提交到 GitHub>
AIHR_OPERATIONS_TOKEN=<生成一个至少 32 字节的随机值>
AIHR_CORS_ORIGINS=<dashboard 的 HTTPS 公网地址>
AIHR_API_PUBLIC_URL=<api 的 HTTPS 公网地址>
```

`postgresql://` 形式的 Railway 连接串会由应用规范化为 `postgresql+psycopg://`。

API 健康检查路径：

```text
/api/v1/ready
```

在 API 服务的 Healthcheck 设置中填写该路径，并确认重启策略为默认的
`On Failure`。`RAILWAY_HEALTHCHECK_TIMEOUT_SEC=300` 会为首次启动留出 300 秒；
首次启动会执行数据库迁移，启用合成数据初始化时会比后续发布慢。

## Dashboard 变量

在 `dashboard` 服务中配置：

```text
RAILWAY_DOCKERFILE_PATH=/deploy/Dockerfile.dashboard
RAILWAY_HEALTHCHECK_TIMEOUT_SEC=120
PORT=8501
AIHR_CONFIG_FILE=config/config.Online.ini
AIHR_ENVIRONMENT=online
AIHR_API_URL=http://api.railway.internal:8000/api/v1
```

Dashboard 健康检查路径：

```text
/_stcore/health
```

在 Dashboard 服务的 Healthcheck 设置中填写该路径，并把重启策略设为失败时
重启。Worker 没有 HTTP 端口，不配置公网域名或 HTTP 健康检查；通过部署状态和
日志中是否持续监听 `aihr` 队列来验收。

## Worker 变量

在 `worker` 服务中配置：

```text
RAILWAY_DOCKERFILE_PATH=/deploy/Dockerfile.worker
AIHR_CONFIG_FILE=config/config.Online.ini
AIHR_ENVIRONMENT=online
AIHR_DATABASE_URL=${{Postgres.DATABASE_URL}}
AIHR_CACHE_URL=${{Redis.REDIS_URL}}
AIHR_CACHE_PREFIX=aihr
AIHR_ANALYSIS_CONTEXT_CACHE_TTL_SECONDS=300
AIHR_ANALYSIS_QUEUE_NAME=aihr
```

Worker 不生成公网域名。

## 人工步骤 3：生成域名并回填变量

1. 给 `api` 生成 Railway 域名，写入 `AIHR_API_PUBLIC_URL`。
2. 给 `dashboard` 生成 Railway 域名，写入 API 的 `AIHR_CORS_ORIGINS`。
3. 重新部署 API 和 Dashboard。

## 人工步骤 4：配置 DeepSeek 密钥

在 DeepSeek 控制台创建 API Key，将它只填入 Railway 的 `AIHR_ASSISTANT_API_KEY`。不要通过聊天、截图、Git 提交或普通文档传递密钥。

没有 DeepSeek Key 时，其余分析页面仍应可用，助手状态会显示为 optional。

## 发布验收

按顺序检查：

1. `https://<api-domain>/api/v1/ready` 返回 `status=ready`。
2. `https://<api-domain>/docs` 可以打开。
3. Dashboard `/_stcore/health` 返回健康状态。
4. Dashboard 首页、漏斗、效果评估、监控、数据质量和机器学习页面有合成数据。
5. `/api/v1/assistant/knowledge/search?query=面试率指标口径` 返回非空引用。
6. Worker 日志显示正在监听 `aihr` 队列。
7. API 的分析上下文状态最终进入 ready；任务没有持续卡在 queued。
8. 日志中没有密码、Token、真实姓名、电话或邮箱。

## 费用与停机

首次演示建议设置 Railway 使用量提醒。面试季结束后可以停止 `api`、`dashboard` 和 `worker`，但删除数据库前必须确认不再需要其中的数据。不要把合成演示数据库误当作唯一备份。
