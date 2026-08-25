import type { SseEvent } from "./api";

export type AssistantRun = {
  status: "idle" | "streaming" | "complete" | "error";
  content: string;
  model: string;
  trust: Record<string, unknown>;
  error: string;
};

export function initialAssistantRun(): AssistantRun {
  return { status: "idle", content: "", model: "", trust: {}, error: "" };
}

export function applyAssistantEvent(state: AssistantRun, event: SseEvent): AssistantRun {
  if (event.event === "metadata") {
    return {
      ...state,
      status: "streaming",
      model: event.model ?? state.model,
      trust: event.trust ?? state.trust,
    };
  }
  if (event.event === "delta") {
    return { ...state, status: "streaming", content: state.content + (event.content ?? "") };
  }
  if (event.event === "done") {
    return {
      ...state,
      status: "complete",
      content: event.content ?? state.content,
      model: event.model ?? state.model,
      trust: event.trust ?? state.trust,
    };
  }
  return { ...state, status: "error", error: event.detail ?? "Assistant request failed" };
}
