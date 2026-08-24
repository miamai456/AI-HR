# 第 6 课：API 与工程实践（技术面试必答）

## 一、技术栈总览

| 模块 | 技术 | 面试怎么说 |
|---|---|---|
| 后端 API | FastAPI + Pydantic | "FastAPI 自带 OpenAPI 文档，Pydantic 保证响应结构" |
| 数据访问 | SQLAlchemy 2.0（Mapped/mapped_column） | "ORM 建模，查询走统一筛选函数" |
| 数据库 | PostgreSQL（本地可 SQLite） | "生产 PostgreSQL，Alembic 管理迁移" |
| 前端看板 | Streamlit + Plotly | "Streamlit 快速迭代，Plotly 交互图表" |
| 数据处理 | pandas + NumPy | "统计计算用 NumPy 向量化" |
| 统计/ML | scikit-learn（LogisticRegression、IsolationForest）、SciPy | "在线训练，保证交互速度" |
| 工程验证 | pytest + ruff | "行为测试 + 代码风格检查" |
| 容器化/运维 | Docker Compose、Redis、RQ、Prometheus、Grafana、OpenTelemetry | "可部署、可观测" |

## 二、API 端点清单（面试可列出）

| 端点 | 返回 | 用途 |
|---|---|---|
| `GET /api/v1/health` | 数据库/后端状态 | 健康检查 |
| `GET /api/v1/ready` | 依赖就绪 + 服务版本 | 就绪检查 |
| `GET /api/v1/meta/filters` | 各筛选维度可选值 | 前端筛选项 |
| `GET /api/v1/overview` | KPI、12 月趋势、成熟队列、开放告警 | 首页/趋势 |
| `GET /api/v1/funnel` | AI/人工各阶段计数 | 漏斗页 |
| `GET /api/v1/effectiveness/unadjusted` | 原始差异、CI、IPTW、SMD | 效果评估页 |
| `GET /api/v1/monitoring` | 基准/当前比较、PSI/JSD、版本趋势、诊断 | 模型监控页 |
| `GET /api/v1/data-quality` | 层级信息 + 结构化质量检查 | 数据质量页 |
| `GET /api/v1/prediction-insights` | 逻辑回归预测、特征贡献、异常（分页） | 机器学习页 |
| `GET /api/v1/dashboard/overview` | 预热快照（无 ML 载荷） | 首页快 |
| `GET /api/v1/assistant/context` | 单筛选范围分析快照（缓存 60s） | AI 助手上下文 |
| `POST /api/v1/assistant/analyze` | 结构化结论/证据/风险/建议 | 助手非流式 |
| `POST /api/v1/assistant/analyze/stream` | SSE 流式（metadata/delta/done/error） | 助手流式 |
| `GET /api/v1/metrics/performance`、`/metrics` | 性能指标、Prometheus 指标（需 Bearer Token） | 运维 |

**统一筛选参数**（几乎所有分析接口都有）：`start_date, end_date, source, job_category, region, model_version, recruiter_team`。

## 三、代码分层规范（面试讲"我写代码的习惯"）

- API 层（`api/main.py`）只做：生命周期、参数、Pydantic 响应、缓存、遥测；**不做计算**。
- 服务层（`services/analytics_core.py`）承担所有统计/ML；纯函数（`_psi`、`_jsd`、`_smd`、`_weighted_rate`）便于单测。
- 边界模块（`analytics_effectiveness.py` 等）只是转发，保持 API 命名整洁。
- 数据访问统一入口 `_recommendation_query(session, **filters)` → 筛选口径只有一份代码。
- 响应用 Pydantic 模型校验（`schemas.py`），前端拿到的字段结构稳定。

## 四、测试与质量（面试必问"怎么验证"）

```powershell
pytest        # 行为测试
ruff check .  # 代码风格与导入检查
```

测试覆盖（`tests/`）：
- 配置文件与环境变量覆盖（`test_config.py`）；
- 固定种子可复现 + 5 类植入异常能被检测（`test_seed.py`）；
- API 响应结构、统一筛选、效果诊断、监控、质量、ML 洞察（`test_api.py` 等）；
- `mart_*` 集市契约与幂等刷新（`test_marts.py`）；
- AI 助手服务与流式接口（`test_assistant_*.py`）；
- 迁移、缓存、指标、鉴权等工程组件。

> 面试金句："我习惯用测试固定指标口径——比如'30 天成熟面试率'的分子分母写进测试，改代码不怕口径漂移。"

## 五、配置管理

- 分层配置：`config/config.ini`（默认）→ `Test.ini` → `Online.ini`；环境变量 `AIHR_*` 覆盖。
- 敏感信息（API Key、数据库密码）不提交仓库，走环境变量或 `.streamlit/secrets.toml`、`config.local.ini`。
- 本地启动：`uvicorn aihr.api.main:app --reload` + `streamlit run app/首页.py`，首次启动自动 seed。

## 六、Docker 与运维（了解，面试可提）

- `compose.yaml`：PostgreSQL + FastAPI API + Streamlit，health check 控制启动顺序。
- Redis：共享 JSON 缓存（上下文快照/助手答案），RQ 预热常见分析范围（全量/AI/人工）。
- Prometheus 指标 + Grafana 看板（AIHR overview dashboard），OpenTelemetry 链路。
- 操作端点（`/metrics`、`/api/v1/metrics/performance`、`/assistant/context/status`）需要 Bearer Token。
- Alembic 管理 PostgreSQL schema 迁移（`migrations/versions/`）。

## 七、性能与缓存（面试可能问"数据量大了怎么办"）

- 页面级：`@st.cache_data(ttl=60)` 前端缓存；API 侧 60 秒上下文快照缓存 + 进程内预测缓存（64 项 LRU）。
- 分析快照：`mart_analysis_context_snapshot` 按"数据版本 + 筛选范围"物化，数据版本（`system_data_version`）作为失效边界。
- ML 在线只采样最近 5000 条，保证约 1 秒返回。
- 事件级表加复合索引（如 `ix_recommendation_analysis_filters`、`ix_funnel_event_analysis_lookup`）。

## 八、自查清单

- [ ] 能报出技术栈表格？
- [ ] 能列出 6 个主要分析端点 + 统一筛选参数？
- [ ] 能讲清 API 层/服务层/数据层的职责边界？
- [ ] 知道 pytest 测什么、ruff 查什么？
- [ ] 能说出 2~3 个性能优化手段？
