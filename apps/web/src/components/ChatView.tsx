import type { Conversation, HostContext } from "../api/types";
import { useChat } from "../hooks/useChat";
import { Composer } from "./Composer";
import { MessageList } from "./MessageList";

const SUGGESTIONS = [
  "How many days of annual leave do I get?",
  "How do I fix VPN error 809?",
  "How do I reset my password?",
];

interface Props {
  conversationId: string | null;
  onConversationCreated?: (conversation: Conversation) => void;
  originAppId?: string | null;
  context?: HostContext | null;
  compact?: boolean;
}

export function ChatView({
  conversationId,
  onConversationCreated,
  originAppId,
  context,
  compact,
}: Props) {
  const chat = useChat(conversationId, onConversationCreated);

  const send = (text: string) =>
    chat.send(text, {
      originAppId,
      context: originAppId || context ? { ...context, app_id: originAppId ?? undefined } : null,
    });

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className={`flex-1 overflow-y-auto ${compact ? "px-3 py-3" : "px-4 py-6"}`}>
        <div className="mx-auto max-w-3xl">
          {chat.loading && <p className="text-sm text-slate-500">Loading conversation…</p>}
          {!chat.loading && chat.messages.length === 0 && (
            <div className={compact ? "pt-4" : "pt-16"}>
              <h2 className={`font-semibold ${compact ? "text-base" : "text-2xl"}`}>
                How can I help?
              </h2>
              <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                Answers come from approved company documents, with sources.
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                {SUGGESTIONS.map((suggestion) => (
                  <button
                    key={suggestion}
                    type="button"
                    onClick={() => send(suggestion)}
                    className="rounded-full border border-slate-300 px-3 py-1 text-xs text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          )}
          <MessageList messages={chat.messages} />
        </div>
      </div>
      <div className={compact ? "px-3 pb-3" : "px-4 pb-4"}>
        <div className="mx-auto max-w-3xl">
          {chat.error && (
            <p role="alert" className="mb-2 text-xs text-red-600 dark:text-red-400">
              {chat.error}
            </p>
          )}
          <Composer sending={chat.sending} onSend={send} onStop={chat.stop} autoFocus />
          {!compact && (
            <p className="mt-2 text-center text-[11px] text-slate-400">
              AI answers can be wrong. Check the cited sources for anything important.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
