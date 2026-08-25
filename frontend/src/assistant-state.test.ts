import { describe, expect, it } from "vitest";

import { applyAssistantEvent, initialAssistantRun } from "./assistant-state";

describe("applyAssistantEvent", () => {
  it("accumulates streamed content and preserves trust metadata", () => {
    let state = initialAssistantRun();
    state = applyAssistantEvent(state, {
      event: "metadata",
      model: "deepseek-chat",
      trust: { confidence: "high" },
    });
    state = applyAssistantEvent(state, { event: "delta", content: "结论" });
    state = applyAssistantEvent(state, { event: "delta", content: "可靠" });
    state = applyAssistantEvent(state, { event: "done", content: "结论可靠" });

    expect(state).toEqual({
      status: "complete",
      content: "结论可靠",
      model: "deepseek-chat",
      trust: { confidence: "high" },
      error: "",
    });
  });
});
