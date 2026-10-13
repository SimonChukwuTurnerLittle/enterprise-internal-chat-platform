import { useState } from "react";
import type { Me } from "../api/types";
import { ChatView } from "../components/ChatView";
import { Sidebar } from "../components/Sidebar";
import { navigate } from "../lib/router";

export function ChatPage({ me, conversationId }: { me: Me; conversationId: string | null }) {
  const [refreshKey, setRefreshKey] = useState(0);
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <div className="flex h-full">
      <div className="hidden md:block">
        <Sidebar me={me} activeId={conversationId} refreshKey={refreshKey} />
      </div>
      {menuOpen && (
        <div className="fixed inset-0 z-20 flex md:hidden">
          <Sidebar
            me={me}
            activeId={conversationId}
            refreshKey={refreshKey}
            onNavigate={() => setMenuOpen(false)}
          />
          <button
            type="button"
            aria-label="Close menu"
            className="flex-1 bg-black/40"
            onClick={() => setMenuOpen(false)}
          />
        </div>
      )}
      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-2 border-b border-slate-200 px-4 py-2 dark:border-slate-800">
          <button
            type="button"
            className="rounded p-1 text-slate-600 md:hidden"
            aria-label="Open menu"
            onClick={() => setMenuOpen(true)}
          >
            ☰
          </button>
          <h1 className="text-sm font-semibold">Enterprise Assistant</h1>
        </header>
        <div className="min-h-0 flex-1">
          <ChatView
            conversationId={conversationId}
            onConversationCreated={(conversation) => {
              navigate(`/c/${conversation.id}`, { replace: conversationId === null });
              setRefreshKey((k) => k + 1);
            }}
          />
        </div>
      </main>
    </div>
  );
}
