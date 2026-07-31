# 数据来源

AIHR 使用 Kaggle 的 `1.3M LinkedIn Jobs & Skills 2024` 数据集作为真实外部职位市场数据来源。

## 本地文件

请将以下文件放在项目根目录或约定的数据目录中：

| 文件 | 作用 | 原始表 |
|---|---|---|
| `linkedin_job_postings.csv.zip` | 职位发布主数据 | `raw_linkedin_job_postings` |
| `job_skills.csv.zip` | 每个职位对应的技能数据 | `raw_job_skills` |
| `dataset.csv` | 候选人简历、面试、JD 决策样本 | `raw_candidate_decisions` |

LinkedIn 职位文件通过 `job_link` 关联。`dataset.csv` 是独立的算法评估数据源，不应和 LinkedIn 职位表直接等同为同一条招聘业务链路。

## 导入方式

只检查压缩包内容，不导入数据库：

```powershell
python -m aihr.data_sources.linkedin_kaggle --inspect-only
```

先导入少量本地样本：

```powershell
python -m aihr.data_sources.linkedin_kaggle --limit 10000
```

导入完整数据集：

```powershell
python -m aihr.data_sources.linkedin_kaggle
```

默认情况下，导入脚本会优先使用 `.env` 中的 `AIHR_DATABASE_URL`；如果没有配置，则使用 `sqlite+pysqlite:///./aihr.db`。如果要导入 MySQL 或 PostgreSQL，请在运行前设置数据库连接地址。

## 建模边界

Kaggle 文件是真实职位市场数据，适合用于：

- 职位数量分析。
- 公司和地区分析。
- 岗位级别和工作模式分析。
- 技能需求分析。
- 市场漂移监控。
- 推荐匹配实验。

`dataset.csv` 适合做简历、JD、面试文本建模，因为它包含决策标签。但它不能被当作完整企业 ATS 事件日志，因为它不包含推荐时间、顾问跟进时间、Offer 事件或入职事件。

LinkedIn 文件也不是真实 ATS 招聘漏斗数据。因此，在没有接入经过授权的企业 ATS 私有数据之前，AIHR 必须继续把推荐、面试、Offer 和入职漏斗结果标记为“合成数据”或“实验性结果”。

## 数据库层级

| 层级 | 对象 | 用途 |
|---|---|---|
| raw | `raw_linkedin_job_postings` | Kaggle 中每条职位发布记录一行 |
| raw | `raw_job_skills` | 通过 `job_link` 关联到职位的技能字符串 |
| raw | `raw_candidate_decisions` | `dataset.csv` 中每条候选人决策样本一行 |
| staging | `stg_linkedin_jobs` | 清洗和关联后的职位发布视图 |
| mart | `mart_job_market_daily` | 按国家、城市、岗位、级别和工作模式统计的每日职位市场数据 |

当前导入脚本使用 pandas `to_sql` 创建 raw 表。SQL 文件记录的是面向 MySQL 风格部署时的目标表结构和下游视图设计。
