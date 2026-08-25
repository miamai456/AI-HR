# MongoDB文档中心与React工作台

## 数据职责

| 存储 | 数据 | 约束 |
|---|---|---|
| PostgreSQL | 候选人、岗位、推荐事实、漏斗事件、指标集市 | 结构化分析的唯一事实源 |
| MongoDB | 脱敏简历、JD、知识分块、会话、工具审计 | `(document_type, source_id)` 幂等写入 |

MongoDB不可用时，API会回退到非持久化内存存储，并通过 `/api/v1/documents/status` 返回 `degraded`。该降级不会中断PostgreSQL指标接口。

## 启动与初始化

```bash
bash scripts/start-stack.sh
```

脚本启动PostgreSQL、MongoDB、Redis、FastAPI、RQ、Streamlit和React工作台，完成健康检查后，将指标字典和架构文档按Markdown标题切分并幂等写入MongoDB。

单独初始化知识分块：

```bash
docker compose exec -T api python scripts/index_knowledge_documents.py
```

## 文档接口

```text
POST /api/v1/documents
GET  /api/v1/documents/{document_id}
GET  /api/v1/documents/search?query=...&document_type=knowledge_chunk
GET  /api/v1/documents/status
```

文档写入在线环境需要运维Bearer Token。写入前自动处理邮箱、中国大陆手机号和身份证号；生产接入真实数据时仍需在上游执行字段级权限和数据最小化。

## 备份

```bash
bash scripts/backup-mongodb.sh
```

备份默认输出到 `backups/mongodb/<UTC时间>/`，包括gzip归档与SHA-256校验文件。恢复前应在隔离数据库中验证归档，而不是直接覆盖线上数据。

## 前端验证

```bash
cd frontend
npm ci
npm test
npm run build
```

React工作台地址为 `http://localhost:5173`。页面从FastAPI读取同一分析上下文，并消费 `metadata`、`delta`、`done`、`error` 四种SSE事件。
