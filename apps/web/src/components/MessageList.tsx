import { useEffect, useRef } from "react";
import type { ChatMessageView } from "../hooks/useChat";
import { CitationList } from "./CitationList";
import { Markdown } from "./Markdown";

function TypingDots() {
  return (
    <span className="inline-flex gap-1 py-2" aria-label="Assistant is typing">
      {[0, 150, 300].map((delay) => (
        <span
          key={delay}
          className="h-2 w-2 animate-bounce rounded-full bg-slate-400"
          style={{ animationDelay: `${delay}ms` }}
        />
      ))}
    </span>
  );
}

export function MessageList({ messages }: { messages: ChatMessageView[] }) {
  const endRef = useRef<HTMLDivElement>(null);
  const last = messages[messages.length - 1];

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages.length, last?.content]);

  return (
    <div className="space-y-4" aria-live="polite">
      {messages.map((message) =>
        message.role === "user" ? (
          <div key={message.key} className="flex justify-end">
            <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-sm bg-blue-600 px-4 py-2 text-sm text-white">
              {message.content}
            </div>
          </div>
        ) : (
          <div key={message.key} className="flex justify-start">
            <div
              className={`max-w-[92%] rounded-2xl rounded-bl-sm px-4 py-2 text-sm ${
                message.status === "error"
                  ? "border border-red-200 bg-red-50 text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200"
                  : "bg-slate-100 dark:bg-slate-800"
              }`}
            >
              {message.content ? <Markdown text={message.content} /> : <TypingDots />}
              {message.status !== "streaming" && <CitationList citations={message.citations} />}
            </div>
          </div>
        ),
      )}
      <div ref={endRef} />
    </div>
  );
}
