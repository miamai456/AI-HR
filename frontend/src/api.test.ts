import { describe, expect, it } from "vitest";

import { consumeSseResponse } from "./api";

describe("consumeSseResponse", () => {
  it("reassembles assistant events split across network chunks", async () => {
    const encoder = new TextEncoder();
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoder.encode('event: metadata\ndata: {"model":"deepseek-chat"}\n\n'));
        controller.enqueue(encoder.encode('event: delta\ndata: {"content":"招聘漏'));
        controller.enqueue(encoder.encode('斗"}\n\nevent: done\ndata: {"content":"招聘漏斗"}\n\n'));
        controller.close();
      },
    });
    const events: Array<{ event: string; content?: string; model?: string }> = [];

    await consumeSseResponse(new Response(stream), (event) => events.push(event));

    expect(events).toEqual([
      { event: "metadata", model: "deepseek-chat" },
      { event: "delta", content: "招聘漏斗" },
      { event: "done", content: "招聘漏斗" },
    ]);
  });
});
