# AIHR: AI 招聘推荐效果评估与监控系统

AIHR 是一个面向招聘业务的分析型 MVP。它回答的不是“推荐量有多少”，而是：

> 在岗位、地区和候选人结构不同的情况下，AI 推荐相对人工推荐是否仍然表现更好；当结果变化时，问题来自模型、数据、招聘团队还是流程？

项目将招聘推荐事件、效果评估、数据质量和模型监控整合为一个可运行的 Streamlit + FastAPI 系统。公开 Demo 使用固定随机种子的合成招聘事件，不包含真实候选人或企业 ATS 数据。

## 当前 MVP

- 招聘漏斗：推荐、联系、回复、面试、Offer、入职的数量、转化率与损耗率。
- 趋势分析：按推荐来源观察 12 个月推荐量、面试率、入职率及滚动趋势。
- 效果评估：原始比例差、95% 置信区间、倾向得分 IPTW、共同支持区间和 SMD 平衡诊断。
- 模型监控：模型版本趋势、PSI、JSD、推荐分数漂移和结构化异常结论。
- 数据质量：重复、缺失、事件顺序、延迟、枚举值和队列成熟度检查。
- 机器学习洞察：逻辑回归转化预测、概率分层、校准、特征贡献、分群机会与 Isolation Forest 异常复核。
- AI 分析助手：未配置大模型时使用本地规则分析；配置兼容 OpenAI Chat Completions 的服务后，可基于当前页面数据追问。

## 系统架构

```text
Streamlit Dashboard
  首页 / 漏斗 / 趋势 / 效果评估 / 监控 / 质量 / ML 洞察
        |
        v
FastAPI Analytics API
  统一筛选、响应模型、只读分析接口
        |
        v
Analytics Service Layer
  漏斗、队列、IPTW、SMD、PSI/JSD、质量检查、预测与异常检测
        |
        v
SQLAlchemy + SQLite / MySQL
  维度表、推荐事实表、漏斗事件表、mart_* 汇总表
```

详细设计见 [架构与数据流](docs/架构与数据流.md)。

## 为什么这个项目不是普通招聘看板

招聘场景中，AI 与人工推荐并非随机分配。AI 可能优先推荐高经验候选人，最近推荐也可能尚未走完招聘流程。直接比较总体面试率会得出误导性结论。

AIHR 因此把分析顺序固定为：

```text
数据是否可信
  -> 队列是否成熟
  -> 原始效果差异
  -> 选择偏差调整与平衡诊断
  -> 漂移和异常归因
  -> 面向业务的下一步动作
```

完整方法、指标和限制见 [分析方法与指标体系](docs/分析方法与指标体系.md)。

## 演示数据与可验证场景

默认种子生成 100,000 条推荐、80,000 名候选人和 1,500 个岗位，并显式植入以下场景：

- AI 推荐人群平均经验更高，形成选择偏差。
- 2026 年第二季度 AI 模型在销售岗位的面试转化下降。
- 2026 年 5 月华东招聘团队的联系延迟增加。
- AI 推荐分数在模型版本切换后发生漂移。
- 最近推荐尚未满足 30 天面试观察窗口，形成未成熟队列。

这些场景让测试和看板能够验证“能否发现问题”，而不是只展示随机生成的图表。真实 LinkedIn 职位市场数据可通过导入脚本进入 raw/staging/mart 层，但当前主 Dashboard 的招聘漏斗结果仍明确标记为合成数据。

## 文档导航

| 文档 | 适合谁读 | 内容 |
|---|---|---|
| [项目复盘](docs/项目复盘.md) | 面试官 | 从问题定义到 MVP 的设计取舍、已解决问题与局限 |
| [架构与数据流](docs/架构与数据流.md) | 技术面试官、开发者 | 前端、API、服务层、数据模型、SQL 与部署关系 |
| [分析方法与指标体系](docs/分析方法与指标体系.md) | 数据分析面试官 | 指标口径、队列成熟度、IPTW、SMD、监控与 ML 方法 |
| [运行与验证](docs/运行与验证.md) | 使用者、开发者 | 本地启动、Docker、数据导入、测试和常见问题 |
| [项目简介与设计](docs/项目简介与设计.md) | 希望深入了解背景的人 | 业务问题、用户、数据模型和页面设计 |
| [指标字典](docs/metric_dictionary.md) | 需要核对口径的人 | 指标分子、分母、时间归因与成熟窗口 |

## 快速开始

前置条件：Python 3.10+。建议在独立虚拟环境中运行。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

启动 API：

```powershell
uvicorn aihr.api.main:app --reload
```

另开一个终端启动 Dashboard：

```powershell
$env:AIHR_API_URL="http://localhost:8000/api/v1"
streamlit run app/首页.py
```

- Dashboard: `http://localhost:8501`
- API Docs: `http://localhost:8000/docs`
- Health Check: `http://localhost:8000/api/v1/health`

Docker、数据导入和完整验证步骤见 [运行与验证](docs/运行与验证.md)。

## 可选：配置 AI 分析助手

复制 `.streamlit/secrets.example.toml` 为 `.streamlit/secrets.toml`，填写自己的 API Key：

```toml
AIHR_ASSISTANT_PROVIDER = "kimi"
AIHR_ASSISTANT_BASE_URL = "https://api.moonshot.ai/v1"
AIHR_ASSISTANT_MODEL = "kimi-k3"
AIHR_ASSISTANT_API_KEY = "replace-with-your-api-key"
```

不配置时，助手仍会使用本地规则对当前页面已加载的结构化指标进行解释；它不会自行计算或编造指标。

## 验证

```powershell
pytest
ruff check .
```

测试覆盖固定种子可复现性、事件顺序、植入场景、数据集市契约、Kaggle 导入、配置加载及 API 响应结构。

## 数据与隐私边界

- 公开版本不提交候选人身份信息、企业 ATS 数据、数据库备份、Token 或密码。
- 招聘推荐、面试、Offer 和入职事件为合成演示数据，不能解释为真实企业招聘效果。
- 外部职位市场数据仅用于真实公开市场分析，不能被包装为真实企业漏斗数据。
