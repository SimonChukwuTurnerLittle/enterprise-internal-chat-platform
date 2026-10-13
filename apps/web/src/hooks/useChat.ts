import { useCallback, useEffect, useRef, useState } from "react";
import { api, csrfHeaders, toApiError } from "../api/client";
import { readSse } from "../api/sse";
import type { Citation, Conversation, ConversationDetail, HostContext } from "../api/types";

export interface ChatMessageView {
  key: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  status: "done" | "streaming" | "error";
}

export interface SendOptions {
  originAppId?: string | null;
  context?: (HostContext & { app_id?: string }) | null;
}

let keyCounter = 0;
const newKey = () => `local-${++keyCounter}`;

/**
 * Messages of one conversation plus sending with a streamed reply.
 * A conversation is created lazily on the first message.
 */
export function useChat(
  routeConversationId: string | null,
  onConversationCreated?: (conversation: Conversation) => void,
) {
  const [conversationId, setConversationId] = useState(routeConversationId);
  const [messages, setMessages] = useState<ChatMessageView[]>([]);
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const createdRef = useRef<string | null>(null);
  const onCreatedRef = useRef(onConversationCreated);
  onCreatedRef.current = onConversationCreated;

  useEffect(() => {
    // We just created this conversation ourselves and already hold its messages.
    if (routeConversationId !== null && routeConversationId === createdRef.current) return;
    createdRef.current = null;
    abortRef.current?.abort();
    setConversationId(routeConversationId);
    setMessages([]);
    setError(null);
    if (!routeConversationId) return;

    let cancelled = false;
    setLoading(true);
    api<ConversationDetail>(`/api/v1/conversations/${routeConversationId}`)
      .then((detail) => {
        if (cancelled) return;
        setMessages(
          detail.messages.map((m) => ({
            key: m.id,
            role: m.role,
            content: m.content,
            citations: m.citations,
            status: "done",
          })),
        );
      })
      .catch((e: Error) => !cancelled && setError(e.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [routeConversationId]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const updateMessage = (key: string, update: (m: ChatMessageView) => ChatMessageView) =>
    setMessages((all) => all.map((m) => (m.key === key ? update(m) : m)));

  const send = useCallback(
    async (content: string, options: SendOptions = {}) => {
      const text = content.trim();
      if (!text || sending) return;
      setError(null);
      setSending(true);
      const assistantKey = newKey();
      try {
        let id = conversationId;
        if (!id) {
          const created = await api<Conversation>("/api/v1/conversations", {
            method: "POST",
            json: { origin_app_id: options.originAppId ?? null },
          });
          id = created.id;
          createdRef.current = id;
          setConversationId(id);
          onCreatedRef.current?.(created);
        }

        setMessages((all) => [
          ...all,
          { key: newKey(), role: "user", content: text, citations: [], status: "done" },
          { key: assistantKey, role: "assistant", content: "", citations: [], status: "streaming" },
        ]);

        const controller = new AbortController();
        abortRef.current = controller;
        const response = await fetch(`/api/v1/conversations/${id}/messages`, {
          method: "POST",
          credentials: "same-origin",
          headers: {
            "Content-Type": "application/json",
            Accept: "text/event-stream",
            ...csrfHeaders(),
          },
          body: JSON.stringify({ content: text, context: options.context ?? null }),
          signal: controller.signal,
        });
        if (!response.ok || !response.body) throw await toApiError(response);

        for await (const event of readSse(response.body)) {
          const data = JSON.parse(event.data);
          switch (event.event) {
            case "citations":
              updateMessage(assistantKey, (m) => ({ ...m, citations: data.citations }));
              break;
            case "token":
              updateMessage(assistantKey, (m) => ({ ...m, content: m.content + data.text }));
              break;
            case "error":
              updateMessage(assistantKey, (m) => ({
                ...m,
                status: "error",
                content: m.content || data.message,
              }));
              break;
            case "message.end":
              updateMessage(assistantKey, (m) => ({ ...m, status: "done" }));
              break;
          }
        }
      } catch (e) {
        if ((e as Error).name === "AbortError") return;
        const message = (e as Error).message || "Something went wrong";
        setError(message);
        updateMessage(assistantKey, (m) => ({ ...m, status: "error", content: m.content || message }));
      } finally {
        updateMessage(assistantKey, (m) => (m.status === "streaming" ? { ...m, status: "done" } : m));
        setSending(false);
      }
    },
    [conversationId, sending],
  );

  const stop = useCallback(() => abortRef.current?.abort(), []);

  return { conversationId, messages, loading, sending, error, send, stop };
}
