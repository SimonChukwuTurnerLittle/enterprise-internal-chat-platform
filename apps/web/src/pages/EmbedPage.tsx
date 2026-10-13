import { useEffect, useState } from "react";
import {
  envelope,
  isEnvelope,
  sanitizeContext,
  type WidgetToHostMessage,
} from "@ecp/widget-sdk/protocol";
import { api, loginUrl } from "../api/client";
import type { HostContext, WidgetConfig } from "../api/types";
import { useMe } from "../auth/useMe";
import { ChatView } from "../components/ChatView";
import { LOGIN_COMPLETE_MESSAGE } from "./PopupDone";

type EmbedState =
  | { kind: "checking" }
  | { kind: "blocked"; reason: string }
  | { kind: "ready"; config: WidgetConfig; hostOrigin: string | null };

/** Origin of the page embedding us, or null when /embed is opened directly. */
function embeddingOrigin(): string | null {
  if (window.parent === window) return null;
  const ancestor = window.location.ancestorOrigins?.[0];
  if (ancestor) return ancestor;
  try {
    return document.referrer ? new URL(document.referrer).origin : null;
  } catch {
    return null;
  }
}

// Per-tab convenience only: remembers the open conversation while the user browses the host app.
const storageKey = (appId: string) => `ecp:embed:${appId}:conversation`;
function readStoredConversation(appId: string): string | null {
  try {
    return sessionStorage.getItem(storageKey(appId));
  } catch {
    return null;
  }
}
function storeConversation(appId: string, id: string | null): void {
  try {
    if (id) sessionStorage.setItem(storageKey(appId), id);
    else sessionStorage.removeItem(storageKey(appId));
  } catch {
    // storage unavailable: nothing to remember
  }
}

export function EmbedPage() {
  const appId = new URLSearchParams(window.location.search).get("app") ?? "";
  const auth = useMe();
  const { reload } = auth;
  const [state, setState] = useState<EmbedState>({ kind: "checking" });
  const [context, setContext] = useState<HostContext | null>(null);
  const [conversationId, setConversationId] = useState(() => readStoredConversation(appId));
  const [chatKey, setChatKey] = useState(0);
  const hostOrigin = state.kind === "ready" ? state.hostOrigin : null;

  const toHost = (message: WidgetToHostMessage) => {
    if (hostOrigin) window.parent.postMessage(envelope(message), hostOrigin);
  };

  // 1. Only registered host origins may embed this app's chat (fail closed).
  useEffect(() => {
    if (!appId) {
      setState({ kind: "blocked", reason: "No application was specified." });
      return;
    }
    api<WidgetConfig>(`/api/v1/widget/config?app_id=${encodeURIComponent(appId)}`)
      .then((config) => {
        const origin = embeddingOrigin();
        const embedded = window.parent !== window;
        const allowed =
          !embedded ||
          (origin !== null &&
            (origin === window.location.origin || config.allowed_origins.includes(origin)));
        setState(
          allowed
            ? { kind: "ready", config, hostOrigin: embedded ? origin : null }
            : { kind: "blocked", reason: "This page is not authorised to embed the assistant." },
        );
      })
      .catch(() => setState({ kind: "blocked", reason: "Unknown application." }));
  }, [appId]);

  // 2. Handshake with the host page and accept context updates from it only.
  useEffect(() => {
    if (!hostOrigin) return;
    const onMessage = (event: MessageEvent) => {
      if (event.source !== window.parent || event.origin !== hostOrigin) return;
      if (!isEnvelope(event.data)) return;
      if (event.data.type === "context") {
        setContext(sanitizeContext((event.data as { context?: unknown }).context));
      } else if (event.data.type === "focus") {
        document.getElementById("composer")?.focus();
      }
    };
    window.addEventListener("message", onMessage);
    window.parent.postMessage(envelope({ type: "ready" }), hostOrigin);
    return () => window.removeEventListener("message", onMessage);
  }, [hostOrigin]);

  useEffect(() => {
    if (auth.status === "authenticated" || auth.status === "unauthenticated") {
      toHost({ type: auth.status });
    }
  }, [auth.status, hostOrigin]); // toHost only depends on hostOrigin

  // 3. Sign-in happens in a popup; it tells us when it is done.
  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      if (event.origin === window.location.origin && event.data?.type === LOGIN_COMPLETE_MESSAGE) {
        reload();
      }
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [reload]);

  const signIn = () =>
    window.open(loginUrl("/auth/popup-done"), "ecp-login", "popup,width=480,height=640");

  const newChat = () => {
    storeConversation(appId, null);
    setConversationId(null);
    setChatKey((k) => k + 1);
  };

  const title = state.kind === "ready" ? `${state.config.name} assistant` : "Assistant";

  return (
    <div className="flex h-full flex-col bg-white dark:bg-slate-950">
      <header className="flex items-center gap-2 bg-blue-600 px-3 py-2 text-white">
        <h1 className="flex-1 truncate text-sm font-semibold">{title}</h1>
        {auth.status === "authenticated" && state.kind === "ready" && (
          <button type="button" onClick={newChat} className="rounded px-2 py-1 text-xs hover:bg-blue-700">
            New chat
          </button>
        )}
        {hostOrigin && (
          <button
            type="button"
            onClick={() => toHost({ type: "close" })}
            aria-label="Close assistant"
            className="rounded px-2 py-1 text-lg leading-none hover:bg-blue-700"
          >
            ×
          </button>
        )}
      </header>
      <div className="min-h-0 flex-1">
        {state.kind === "blocked" ? (
          <p className="p-4 text-sm text-red-700 dark:text-red-300">{state.reason}</p>
        ) : state.kind === "checking" || auth.status === "loading" ? (
          <p className="p-4 text-sm text-slate-500">Loading…</p>
        ) : auth.status === "unauthenticated" ? (
          <div className="p-4 text-sm">
            <p>Sign in with your company account to use the assistant.</p>
            <button
              type="button"
              onClick={signIn}
              className="mt-3 rounded-lg bg-blue-600 px-3 py-1.5 font-medium text-white hover:bg-blue-700"
            >
              Sign in
            </button>
          </div>
        ) : auth.status === "error" ? (
          <p className="p-4 text-sm text-red-700">Could not reach the assistant: {auth.message}</p>
        ) : (
          <ChatView
            key={chatKey}
            compact
            conversationId={conversationId}
            originAppId={appId}
            context={context}
            onConversationCreated={(conversation) => {
              setConversationId(conversation.id);
              storeConversation(appId, conversation.id);
            }}
          />
        )}
      </div>
    </div>
  );
}
