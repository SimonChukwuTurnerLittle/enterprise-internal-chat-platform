// @vitest-environment node
import { describe, expect, it } from "vitest";
import { parseSseBlock, readSse, type SseEvent } from "./sse";

function streamOf(...chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
}

async function collect(stream: ReadableStream<Uint8Array>): Promise<SseEvent[]> {
  const events: SseEvent[] = [];
  for await (const event of readSse(stream)) events.push(event);
  return events;
}

describe("readSse", () => {
  it("parses events split across network chunks", async () => {
    const events = await collect(
      streamOf('event: token\ndata: {"text":"Hel', 'lo"}\n\nevent: message.end\r\n', "data: {}\r\n\r\n"),
    );
    expect(events).toEqual([
      { event: "token", data: '{"text":"Hello"}' },
      { event: "message.end", data: "{}" },
    ]);
  });

  it("handles a final event without a trailing blank line", async () => {
    expect(await collect(streamOf("data: last"))).toEqual([{ event: "message", data: "last" }]);
  });
});

describe("parseSseBlock", () => {
  it("ignores comments and joins multi-line data", () => {
    expect(parseSseBlock(": keep-alive\nevent: x\ndata: a\ndata: b")).toEqual({
      event: "x",
      data: "a\nb",
    });
    expect(parseSseBlock(": only a comment")).toBeNull();
  });
});
