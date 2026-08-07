from app.assistant_session import (
    append_unique_question,
    clear_conversation,
    conversation_for_regeneration,
)


def test_quick_question_is_not_appended_twice() -> None:
    messages = [
        {"role": "user", "content": "Summarize"},
        {"role": "assistant", "content": "Answer"},
    ]

    appended = append_unique_question(messages, "Summarize")

    assert appended is False
    assert len(messages) == 2


def test_conversation_can_be_cleared_and_regenerated() -> None:
    messages = [
        {"role": "user", "content": "First"},
        {"role": "assistant", "content": "Old answer"},
        {"role": "user", "content": "Latest"},
        {"role": "assistant", "content": "Latest answer"},
    ]

    regeneration = conversation_for_regeneration(messages)

    assert regeneration[-1] == {"role": "user", "content": "Latest"}
    assert all(message["content"] != "Latest answer" for message in regeneration)
    clear_conversation(messages)
    assert messages == []
