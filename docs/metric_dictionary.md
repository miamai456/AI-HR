# AIHR 指标字典

本文档固定 MVP 的指标口径。核心原则：所有效果、队列、漂移分析都从事件级表出发，`mart_*` 只作为展示和查询加速层。

## 公共约定

| 项目 | 定义 |
|---|---|
| 分析主键 | `recommendation_id`，一条推荐只计一次 |
| 推荐时间 | `fact_recommendation.recommended_at` |
| 推荐月份 | `DATE_FORMAT(recommended_at, '%Y-%m-01')` |
| 来源 | `fact_recommendation.source`，取值 `ai` / `human` |
| 模型版本 | `dim_model_version.model_version` |
| 岗位类别 | `dim_job.job_category` |
| 地区 | 优先使用 `dim_job.region` |
| 去重规则 | 同一 `recommendation_id + stage` 只保留一条事件；SQL 层用唯一约束保证 |
| 未成熟数据 | 成熟窗口未结束的推荐不进入成熟率分母，单独标记为 `immature` |

## 漏斗指标

| 指标 | 分子 | 分母 | 时间字段 | 成熟窗口 |
|---|---|---|---|---|
| 推荐量 | `fact_recommendation` 记录数 | 不适用 | `recommended_at` | 无 |
| 触达率 | `contacted` 阶段 `status = 'completed'` 的推荐数 | 推荐量 | `recommended_at` | 7 天 |
| 回复率 | `replied` 阶段 `status = 'completed'` 的推荐数 | 推荐量 | `recommended_at` | 14 天 |
| 面试率 | `interviewed` 阶段 `status = 'completed'` 的推荐数 | 推荐量 | `recommended_at` | 30 天 |
| Offer 率 | `offered` 阶段 `status = 'completed'` 的推荐数 | 推荐量 | `recommended_at` | 60 天 |
| 入职率 | `hired` 阶段 `status = 'completed'` 的推荐数 | 推荐量 | `recommended_at` | 90 天 |

说明：漏斗展示默认使用推荐日期归因，即一条 1 月推荐在 2 月面试，仍计入 1 月推荐 cohort 的面试结果。

## 成熟队列指标

| 指标 | 分子 | 分母 | 成熟判定 |
|---|---|---|---|
| 30 天面试成熟率 | 30 天内完成 `interviewed` 的推荐数 | 推荐后已满 30 天的推荐数 | `recommended_at <= as_of_date - 30 days` |
| 90 天入职成熟率 | 90 天内完成 `hired` 的推荐数 | 推荐后已满 90 天的推荐数 | `recommended_at <= as_of_date - 90 days` |
| 未成熟推荐数 | 成熟窗口尚未结束的推荐数 | 不适用 | `recommended_at > as_of_date - window` |
| 招聘周期 | `hired.event_at - recommended_at` | 已入职推荐 | 仅 completed hire |

## 效果评估指标

| 指标 | 定义 |
|---|---|
| 原始差异 | `AI 面试率 - Human 面试率` |
| 倾向得分 | 使用岗位类别、地区、候选人经验、学历、岗位级别、推荐月份等变量预测 `source = ai` 的概率 |
| 共同支持区域 | 保留 AI 与 Human 倾向得分重叠区间内样本 |
| 调整后差异 | 在共同支持样本上使用加权或匹配后的 `AI 面试率 - Human 面试率` |
| SMD | 调整前后各协变量的标准化均值差，目标绝对值小于 0.1 |
| 95% CI | 二项比例差或回归稳健标准误估计 |

## 漂移和异常指标

| 指标 | 字段 | 对比方式 |
|---|---|---|
| 推荐分数 PSI/JSD | `recommendation_score` | 基准期 vs 当前期 |
| 经验分布 PSI/JSD | `experience_years` 分箱 | 基准期 vs 当前期 |
| 岗位类别 PSI/JSD | `job_category` | 基准期 vs 当前期 |
| 地区 PSI/JSD | `region` | 基准期 vs 当前期 |
| 模型版本归因 | `model_version` | 按版本拆分效果与分布变化 |

PSI 解释：`< 0.1` 正常，`0.1 - 0.25` 轻度漂移，`>= 0.25` 明显漂移。
