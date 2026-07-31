# 数据来源规划

AIHR 的数据层分为两部分：真实职位市场数据和实验性招聘结果数据。

## 数据源选择

主要数据源：Kaggle `1.3M LinkedIn Jobs & Skills 2024` 压缩包。

已接收的本地文件：

| 文件 | 原始表 | 已加载行数 |
|---|---:|---:|
| `data/raw/linkedin_job_postings.csv.zip` | `raw_linkedin_job_postings` | 1,348,454 |
| `data/raw/job_skills.csv.zip` | `raw_job_skills` | 1,296,381 |

选择该数据源的原因：

- 数据规模足够大，适合展示数据库存储、SQL 分层和数据集市建设能力。
- 包含真实职位市场字段，例如职位名称、公司、地点、职位描述和技能。
- 即使没有企业私有 ATS 数据，也能支持有价值的分析：市场需求、技能趋势、地区趋势、公司招聘需求、薪资覆盖率和推荐匹配实验。

数据边界：

- 公开职位发布数据是真实的。
- 候选人身份、推荐、面试、Offer 和入职结果仍然是实验性或合成数据，除非项目获得真实 ATS 授权导出。
- 看板标签不能把实验性漏斗结果描述为真实企业招聘结果。

## 本地文件约定

下载后的 Kaggle 压缩包建议放在：

```text
data/raw/linkedin_job_postings.csv.zip
data/raw/job_skills.csv.zip
```

`data/raw/` 已被 Git 忽略，因此大型原始文件只保留在本地，不进入代码仓库。

## 加载流程

1. 检查压缩包内容：

```powershell
python scripts/import_kaggle_jobs.py data/raw/linkedin_jobs_skills_2024.zip --list
python scripts/import_kaggle_jobs.py data/raw/linkedin_job_postings.csv.zip data/raw/job_skills.csv.zip --list
```

2. 将 CSV 文件加载到数据库 raw 表：

```powershell
python scripts/import_kaggle_jobs.py data/raw/linkedin_jobs_skills_2024.zip --load
python scripts/import_kaggle_jobs.py data/raw/linkedin_job_postings.csv.zip data/raw/job_skills.csv.zip --load
```

3. 构建 staging 和后续模型：

```text
raw_*
  -> raw_linkedin_job_postings / raw_job_skills
  -> stg_job_postings / stg_job_skills
  -> dim_job / dim_company / dim_skill / bridge_job_skill
  -> 面向看板和推荐匹配的数据集市
```

历史版本中，raw 表曾加载到本地 SQLite 数据库 `aihr.db`。当前项目已经迁移到 PostgreSQL，后续本地分析应优先使用 PostgreSQL。相同导入脚本也可以通过传入 `--database-url` 或设置 `AIHR_DATABASE_URL` 指向其他数据库。

本地验证结果：

- raw 表加载成功。
- `raw_linkedin_job_postings.job_link`、`raw_linkedin_job_postings.first_seen` 和 `raw_job_skills.job_link` 已建立索引。
- staging 视图可以从真实职位数据中返回样本。
- 在百万级数据规模下，完整 `mart_job_market_overview` 聚合对 SQLite 较重；用于生产风格演示时，建议在 PostgreSQL 或 MySQL 中构建该集市，或者在看板读取前先物化为表。

## 后续可解锁的分析

加载真实职位数据后，AIHR 可以继续建设：

- 真实职位数量趋势。
- 岗位类别和地区分布图。
- 技能需求排行榜。
- 公司招聘活跃度视图。
- 基于 TF-IDF 或向量表示的职位匹配。
- 岗位类别、地区、技能和推荐分数的漂移分析。
