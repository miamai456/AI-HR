export type SseEvent = {
  event: "metadata" | "delta" | "done" | "error";
  content?: string;
  model?: string;
  detail?: string;
  trust?: Record<string, unknown>;
};

export type DocumentSearchResult = {
  document: {
    document_id: string;
    document_type: string;
    source_id: string;
    title: string;
    content: string;
    metadata: Record<string, unknown>;
  };
  score: number;
};

const API_BASE = import.meta.env.VITE_AIHR_API_URL ?? "http://localhost:8000/api/v1";

export async function consumeSseResponse(
  response: Response,
  onEvent: (event: SseEvent) => void,
): Promise<void> {
  if (!response.ok) {
    throw new Error(`Assistant request failed with status ${response.status}`);
  }
  if (!response.body) {
    throw new Error("Assistant response did not include a stream");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const dispatch = (block: string) => {
    let eventName = "message";
    const dataLines: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) eventName = line.slice(6).trim();
      if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
    }
    if (!dataLines.length) return;
    const payload = JSON.parse(dataLines.join("\n")) as Omit<SseEvent, "event">;
    onEvent({ event: eventName as SseEvent["event"], ...payload });
  };

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done }).replaceAll("\r\n", "\n");
    let boundary = buffer.indexOf("\n\n");
    while (boundary >= 0) {
      dispatch(buffer.slice(0, boundary));
      buffer = buffer.slice(boundary + 2);
      boundary = buffer.indexOf("\n\n");
    }
    if (done) break;
  }
  if (buffer.trim()) dispatch(buffer);
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) throw new Error(`API request failed with status ${response.status}`);
  return response.json() as Promise<T>;
}

export function getAnalysisContext(): Promise<Record<string, unknown>> {
  return getJson("/assistant/context");
}

export async function searchDocuments(query: string): Promise<DocumentSearchResult[]> {
  const params = new URLSearchParams({ query, limit: "3" });
  const payload = await getJson<{ results: DocumentSearchResult[] }>(
    `/documents/search?${params.toString()}`,
  );
  return payload.results;
}

export async function streamAssistant(
  question: string,
  context: Record<string, unknown>,
  onEvent: (event: SseEvent) => void,
): Promise<void> {
  const response = await fetch(`${API_BASE}/assistant/analyze/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      context,
      messages: [{ role: "user", content: question }],
    }),
  });
  await consumeSseResponse(response, onEvent);
}
