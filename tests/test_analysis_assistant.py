from app.analysis_assistant import (
    _format_structured_answer,
    answer_question,
    assistant_config_summary,
    format_streamed_answer,
    prepare_analysis_context,
    split_assistant_answer,
)


def test_assistant_config_summary_reads_backend_status(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.analysis_assistant.get_assistant_status",
        lambda: {"configured": True, "provider": "deepseek", "model": "deepseek-chat"},
    )

    summary = assistant_config_summary()

    assert summary["provider"] == "deepseek"
    assert summary["model"] == "deepseek-chat"


def test_answer_question_uses_backend_and_formats_schema(monkeypatch) -> None:
    monkeypatch.setattr("app.analysis_assistant.assistant_configured", lambda: True)
    monkeypatch.setattr(
        "app.analysis_assistant.analyze_assistant",
        lambda context, messages, force_refresh=False: {
            "conclusion": "Interview rate declined",
            "evidence": ["Sample size is 100"],
            "risks": ["This is not a causal result"],
            "recommendations": ["Check data quality"],
        },
    )

    answer = answer_question({}, [{"role": "user", "content": "Analyze"}])

    assert "Interview rate declined" in answer
    assert "Check data quality" in answer


def test_structured_answer_has_four_business_sections() -> None:
    answer = _format_structured_answer(
        {
            "conclusion": "Conclusion value",
            "evidence": ["Evidence value"],
            "risks": ["Risk value"],
            "recommendations": ["Recommendation value"],
        }
    )

    assert answer.index("Conclusion value") < answer.index("Evidence value")
    assert answer.index("Evidence value") < answer.index("Risk value")
    assert answer.index("Risk value") < answer.index("Recommendation value")


def test_structured_answer_displays_scope_freshness_and_observational_confidence() -> None:
    answer = _format_structured_answer(
        {
            "conclusion": "Association found",
            "evidence": [],
            "risks": [],
            "recommendations": [],
            "model": "deepseek-chat",
            "trust": {
                "sample_size": 120,
                "period_start": "2026-01-01",
                "period_end": "2026-06-30",
                "data_updated_at": "2026-07-01T08:00:00",
                "data_quality_status": "warn",
                "confidence": "medium",
                "confidence_note": "Use cautiously.",
                "analysis_type": "observational_association",
                "causal_claim": False,
                "filters": {"source": "ai", "region": "east"},
            },
        }
    )

    summary, details, body = split_assistant_answer(answer)

    assert summary == "置信度：中｜样本量：120｜数据质量：需关注"
    assert "分析来源：DeepSeek" in details
    assert "时间范围：2026-01-01 至 2026-06-30" in details
    assert "数据更新时间：2026-07-01T08:00:00" in details
    assert "分析类型：观察性关联分析" in details
    assert "不支持因果结论" in details
    assert "推荐来源=AI 推荐" in details
    assert body.startswith("**结论**")
    assert "Association found" in body


def test_embedded_context_is_normalized_with_current_filter_scope() -> None:
    context = prepare_analysis_context(
        {
            "data": {
                "effectiveness": {
                    "ai_sample_size": 40,
                    "human_sample_size": 60,
                    "analysis_type": "observational_association",
                },
                "data_quality": {
                    "summary": {"failed_checks": 0, "warning_checks": 1},
                    "layers": [],
                },
            }
        },
        {
            "start_date": "2026-01-01",
            "end_date": "2026-06-30",
            "filters": {"source": "ai"},
        },
    )

    assert context["effectiveness"]["ai_sample_size"] == 40
    assert context["data_quality"]["summary"]["warning_checks"] == 1
    assert context["analysis_scope"]["filters"] == {"source": "ai"}


def test_streamed_answer_keeps_chinese_trust_metadata_collapsible() -> None:
    answer = format_streamed_answer(
        "## 结论\n当前结果仅支持观察性判断。",
        {
            "model": "deepseek-chat",
            "trust": {
                "sample_size": 120,
                "confidence": "medium",
                "data_quality_status": "warn",
                "period_start": "2026-01-01",
                "period_end": "2026-06-30",
                "filters": {"source": "ai"},
                "confidence_note": "结论需要谨慎使用。",
            },
        },
    )

    summary, details, body = split_assistant_answer(answer)

    assert summary == "置信度：中｜样本量：120｜数据质量：需关注"
    assert "因果声明：不支持因果结论" in details
    assert "推荐来源=AI 推荐" in details
    assert body.startswith("## 结论")
