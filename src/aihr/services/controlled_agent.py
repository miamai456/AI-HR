from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from sqlglot import exp, parse
from sqlglot.errors import ParseError

from aihr.services.analytics_quality import get_data_quality
from aihr.services.knowledge import DocumentRetriever

ALLOWED_TABLES = frozenset(
    {
        "dim_candidate",
        "dim_job",
        "dim_recruiter",
        "dim_model_version",
        "fact_recommendation",
        "fact_funnel_event",
        "mart_daily_funnel",
        "mart_cohort_conversion",
        "mart_ai_effectiveness",
        "mart_feature_drift",
        "mart_monitoring_alert",
    }
)
SENSITIVE_TERMS = {"phone", "email", "手机号", "邮箱", "身份证", "password", "密码"}
INJECTION_PATTERNS = ("ignore previous", "system prompt", "忽略以上", "越过限制", "绕过限制")


@dataclass(frozen=True)
class AgentStep:
    tool: str
    output: object


def validate_readonly_sql(sql: str, max_rows: int = 100) -> str:
    candidate = sql.strip().rstrip(";").strip()
    try:
        statements = parse(candidate)
    except ParseError as exc:
        raise ValueError("SQL 解析失败。") from exc
    if len(statements) != 1 or not statements[0].find(exp.Select):
        raise ValueError("只允许单条 SELECT 查询。")
    tree = statements[0]
    forbidden = (exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop, exp.Alter, exp.Command)
    if any(tree.find(node) for node in forbidden):
        raise ValueError("禁止执行 DDL 或 DML。")
    tables = {table.name.lower() for table in tree.find_all(exp.Table)}
    unknown = tables.difference(ALLOWED_TABLES)
    if unknown:
        raise ValueError(f"数据表不在白名单中：{sorted(unknown)}")
    if tree.find(exp.Into):
        raise ValueError("禁止 SELECT INTO。")
    limit = tree.args.get("limit")
    if limit is None:
        candidate = f"{candidate} LIMIT {max_rows}"
    elif isinstance(limit.expression, exp.Literal) and int(limit.expression.this) > max_rows:
        raise ValueError(f"查询行数不能超过 {max_rows}。")
    return candidate


class ControlledAnalysisAgent:
    def __init__(self, retriever: DocumentRetriever) -> None:
        self.retriever = retriever

    def run(self, question: str, session: Session) -> dict:
        normalized = question.lower()
        if any(pattern in normalized for pattern in INJECTION_PATTERNS):
            raise ValueError("检测到提示注入指令，已拒绝执行。")
        if any(term in normalized for term in SENSITIVE_TERMS):
            raise ValueError("请求涉及敏感字段，已拒绝执行。")

        citations = [chunk.to_dict() for chunk in self.retriever.search(question)]
        steps: list[AgentStep] = [AgentStep("search_docs", citations)]
        if any(token in normalized for token in ("质量", "quality", "异常数据")):
            summary = get_data_quality(session)["summary"]
            steps.append(AgentStep("get_quality_status", summary))
        elif any(token in normalized for token in ("表结构", "字段", "schema")):
            inspector = inspect(session.get_bind())
            schema = {
                table: [column["name"] for column in inspector.get_columns(table)]
                for table in sorted(ALLOWED_TABLES)
                if inspector.has_table(table)
            }
            steps.append(AgentStep("inspect_schema", schema))
        elif any(token in normalized for token in ("推荐量", "recommendation count", "多少推荐")):
            sql = validate_readonly_sql(
                "SELECT source, COUNT(*) AS recommendation_count "
                "FROM fact_recommendation GROUP BY source ORDER BY source"
            )
            rows = [dict(row) for row in session.execute(text(sql)).mappings()]
            steps.append(AgentStep("run_readonly_sql", {"sql": sql, "rows": rows}))

        return {
            "question": question,
            "steps": [{"tool": step.tool, "output": step.output} for step in steps],
            "citations": citations,
            "answer": self._summarize(steps, citations),
        }

    @staticmethod
    def _summarize(steps: list[AgentStep], citations: list[dict]) -> str:
        data_steps = [step for step in steps if step.tool != "search_docs"]
        if data_steps:
            return (
                f"已通过受控工具 {data_steps[-1].tool} 获取结果；"
                f"引用 {len(citations)} 个知识片段。"
            )
        if citations:
            return f"已检索到 {len(citations)} 个相关知识片段，请根据引用核对口径。"
        return "知识库中没有足够证据，拒绝生成无依据答案。"
