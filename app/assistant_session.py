def append_unique_question(messages: list[dict[str, str]], question: str) -> bool:
    if any(
        message.get("role") == "user" and message.get("content") == question
        for message in messages
    ):
        return False
    messages.append({"role": "user", "content": question})
    return True


def conversation_for_regeneration(
    messages: list[dict[str, str]],
) -> list[dict[str, str]]:
    if not messages:
        return []
    regenerated = [dict(message) for message in messages]
    if regenerated[-1].get("role") == "assistant":
        regenerated.pop()
    while regenerated and regenerated[-1].get("role") != "user":
        regenerated.pop()
    return regenerated


def clear_conversation(messages: list[dict[str, str]]) -> None:
    messages.clear()
