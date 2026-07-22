# AIHR Analytics

AI 招聘推荐效果评估与模型监控系统，用于比较 AI 与人工推荐的招聘漏斗表现，并逐步扩展选择偏差调整、队列分析和数据漂移监控。

当前版本是可运行的工程骨架，公开演示使用固定随机种子生成的合成指标数据，不包含任何真实候选人信息或前公司数据。

## 当前功能

- FastAPI 健康检查、筛选项、总览、漏斗、效果评估和监控接口。
- MySQL 数据库与自动初始化的演示数据。
- Streamlit 总览、招聘漏斗、趋势、效果评估和监控页面。
- 按日期、推荐来源、岗位类别和地区筛选。
- Docker Compose 一键启动。
- SQLite 内存数据库 API 测试。

## 系统架构

```text
Streamlit Dashboard
        |
        v
FastAPI Analytics API
        |
        v
MySQL / SQLAlchemy
        |
        v
mart_daily_funnel
```

后续版本将在 `src/aihr/analysis` 和 `src/aihr/monitoring` 中增加倾向得分、SMD、PSI、JSD、队列成熟度和异常归因。

## Docker 启动

```powershell
Copy-Item .env.example .env
docker compose up --build
```

启动后访问：

- Dashboard: http://localhost:8501
- API 文档: http://localhost:8000/docs
- API 健康检查: http://localhost:8000/api/v1/health
- MySQL: `localhost:3307`

停止服务：

```powershell
docker compose down
```

如需同时删除本地 MySQL 演示数据卷：

```powershell
docker compose down --volumes
```

## 本地开发

本机 Python 3.10+ 可运行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
uvicorn aihr.api.main:app --reload
```

另开一个终端：

```powershell
$env:AIHR_API_URL="http://localhost:8000/api/v1"
streamlit run app/Home.py
```

默认本地模式使用项目目录下的 SQLite；Docker 模式使用 MySQL。

## 测试

```powershell
pytest
ruff check .
```

## 数据说明

- `data_origin=synthetic` 表示公开演示用合成数据。
- 前公司或候选人数据不得提交到仓库。
- 经授权真实数据应通过私有适配层接入，公开 Demo 继续使用合成数据。
- 完整数据边界见 `数据流设计.md`，完整需求见 `需求.md`。
