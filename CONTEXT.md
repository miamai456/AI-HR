# AIHR 项目上下文

## 项目目标

AIHR 是一个用于评估和监控 AI 招聘推荐效果的分析系统。当前产品比较 AI 推荐和人工推荐在招聘漏斗中的表现，支持按日期、岗位、地区、推荐来源、模型版本和顾问团队进行分群分析，并提供效果评估、模型监控、异常诊断、数据质量和机器学习洞察能力。

## 核心术语

- **推荐来源**：候选人推荐的来源，例如 AI 推荐或人工推荐。
- **招聘漏斗**：推荐、联系、回复、面试、Offer、入职等招聘阶段序列，用于比较不同来源的转化表现。
- **推荐效果**：推荐在面试、Offer、入职等业务结果上的质量或价值。
- **模型监控**：持续检查关键指标变化、特征漂移和推荐分数漂移。
- **模型版本**：推荐模型或人工规则版本，用于分群分析和监控。
- **顾问团队**：负责候选人跟进的招聘顾问或团队，用于分析运营执行差异。
- **成熟队列**：已经经过足够时间窗口、可以公平观察后续转化结果的推荐队列。
- **30 天合格面试率**：推荐后 30 天内进入面试阶段的成熟推荐数，除以成熟推荐总数。
- **未解决告警**：仍处于 open 状态的监控信号，例如面试率明显下降。
- **倾向得分调整**：一种观察性分析方法，用可观测变量估计推荐来自 AI 的概率，再比较 AI 与人工推荐表现。
- **共同支持**：AI 和人工推荐在倾向得分区间上的重叠部分，用于避免不可比样本强行比较。
- **极端权重处理**：对逆概率权重进行截尾，避免少数极端样本主导调整结果。
- **标准化均值差（SMD）**：衡量调整前后协变量平衡程度的诊断指标。
- **总体稳定性指数（PSI）**：比较基准期和当前期数值特征分布变化的漂移指标。
- **詹森-香农散度（JSD）**：比较基准期和当前期类别特征分布变化的漂移指标。
- **推荐分数漂移**：比较基准期和当前期推荐分数水平变化的监控信号。
- **诊断结论**：包含问题分类、证据指标、时间范围、样本量和维度拆解的监控发现。
- **问题分类**：诊断结论的解释类别，包括数据问题、流量结构、模型、顾问操作或招聘流程问题。
- **数据质量检查**：结构化 API 返回的数据可靠性规则结果，包含状态、严重程度、证据指标、影响数量、样本量、时间范围和详情。
- **层级新鲜度**：维表、事实表和集市表的记录数与最新更新时间，用于判断分析数据是否完整、及时。
- **转化概率**：某条推荐进入目标漏斗阶段的预测概率，当前目标阶段是已完成面试。
- **特征贡献**：由模型特征值和系数计算得到的可解释方向信号，用于解释哪些因素提高或降低预测转化概率。
- **异常发现**：结合异常特征组合和预测/实际结果不一致的推荐级机器学习信号。
- **合成演示数据**：当前应用使用的固定随机种子生成的招聘推荐事件数据。
- **真实职位市场数据**：外部职位数据，用于表示招聘市场，不包含真实候选人漏斗结果。
- **实验性漏斗结果**：在缺少真实 ATS 授权导出时，用于方法验证的隐私安全推荐、面试、Offer 和入职结果。
- **指标字典**：分析字段和指标定义见 `docs/metric_dictionary.md`。
- **可信度信封**：服务端附加到每条助手结论的样本量、时间范围、数据更新时间、质量状态、置信提示和分析类型。
- **探索性判断**：样本不足、质量检查失败或质量未知时允许输出的弱结论，不可表述为稳定效果或因果关系。

## 系统结构

- `src/aihr/api/main.py` 提供 FastAPI 分析接口。
- `src/aihr/services/analytics.py` 封装基于推荐事件事实表的分析逻辑，让各页面共享日期、来源、岗位、地区、模型版本和顾问团队筛选。
- `src/aihr/services/marts.py` 生成可复用的数据集市，包括每日漏斗、成熟队列、AI 效果、特征漂移和监控告警汇总。
- `src/aihr/models.py` 和 `src/aihr/schemas.py` 定义数据库模型和 API 返回结构。
- `app/` 包含 Streamlit 前端看板和 API 客户端。
- `app/pages/6_机器学习洞察.py` 展示机器学习预测、解释、分群表现和异常发现。
- `tests/` 包含 API、分析逻辑和种子数据的自动化测试。

## 反馈命令

- 运行 `pytest` 做自动化测试。
- 运行 `ruff check .` 做代码风格和导入检查。
- 使用 Docker Compose 验证 API、前端和数据库的集成启动路径。

## Assistant Architecture

- PostgreSQL is the production database; Alembic versions its schema and does not replace the
  database engine.
- RQ workers prewarm common analysis scopes through Redis, with a local-thread fallback.
- Online operations endpoints require an operations Bearer token.
- Prometheus evaluates API latency, 429, assistant failure, and cache-hit alerts; Grafana provides
  the AIHR operations dashboard.
- Persistent Compose data and deployment secrets are bound to E:\\AIHRData. Docker Desktop's
  engine data location must be moved to E before the stack is started.
- The assistant provider is DeepSeek and is called only by the FastAPI service.
- Streamlit uses the internal assistant API and never receives the provider key.
- Assistant responses use the structured fields `conclusion`, `evidence`, `risks`, and `recommendations`.
- The API owns retry, timeout, provider error mapping, short-lived response caching, and usage logging.
- The API owns the trust envelope and forces low-confidence answers to exploratory findings.
- `/api/v1/ready` reports dependency readiness and the running service version.
- Prediction insights expose paged anomaly findings through `anomaly_limit` and `anomaly_offset`.
- `/api/v1/assistant/context` returns one filter-consistent analysis snapshot and caches it for 60 seconds.
- `/api/v1/assistant/analyze/stream` uses SSE events named `metadata`, `delta`, `done`, and `error`.
- Streamed answers use Chinese Markdown sections while the non-streaming API retains the JSON response contract.
- Analysis snapshots and structured assistant answers use a shared JSON cache; Compose provides Redis with AOF persistence.
- Local development falls back to an in-process cache and can prewarm common unfiltered, AI, and human scopes.
- `/api/v1/metrics/performance` reports request and assistant latency percentiles, cache hit rates, tokens, and errors.
- `scripts/run-assistant-eval.py` runs the fixed assistant quality cases against a live API.
- Common assistant analysis scopes are materialized in `mart_analysis_context_snapshot` and keyed by the hiring-facts dataset version.
- `system_data_version` is the cache invalidation boundary for hiring recommendation and funnel facts.
- `/api/v1/assistant/context/status` reports dataset version, prewarm progress, materialized snapshot counts, and cache backend.

## 决策记录

重要且难以回退的架构决策应记录到 `docs/adr/`。
