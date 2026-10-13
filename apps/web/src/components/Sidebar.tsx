import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Conversation, Me } from "../api/types";
import { logout } from "../auth/useMe";
import { navigate } from "../lib/router";

interface Props {
  me: Me;
  activeId: string | null;
  refreshKey: number;
  onNavigate?: () => void;
}

export function Sidebar({ me, activeId, refreshKey, onNavigate }: Props) {
  const [conversations, setConversations] = useState<Conversation[] | null>(null);

  useEffect(() => {
    api<Conversation[]>("/api/v1/conversations")
      .then(setConversations)
      .catch(() => setConversations([]));
  }, [refreshKey]);

  const go = (to: string) => {
    navigate(to);
    onNavigate?.();
  };

  return (
    <nav className="flex h-full w-72 flex-col border-r border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-900">
      <div className="p-3">
        <button
          type="button"
          onClick={() => go("/")}
          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-left text-sm font-medium hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800 dark:hover:bg-slate-700"
        >
          + New chat
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-2">
        <p className="px-2 pb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
          Recent
        </p>
        {conversations === null && <p className="px-2 text-sm text-slate-500">Loading…</p>}
        {conversations?.length === 0 && (
          <p className="px-2 text-sm text-slate-500">No conversations yet.</p>
        )}
        <ul className="space-y-0.5">
          {conversations?.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                onClick={() => go(`/c/${c.id}`)}
                aria-current={c.id === activeId ? "page" : undefined}
                className={`w-full truncate rounded-md px-2 py-1.5 text-left text-sm ${
                  c.id === activeId
                    ? "bg-slate-200 font-medium dark:bg-slate-800"
                    : "hover:bg-slate-100 dark:hover:bg-slate-800/60"
                }`}
              >
                {c.title ?? "New conversation"}
              </button>
            </li>
          ))}
        </ul>
      </div>
      <div className="border-t border-slate-200 p-3 text-sm dark:border-slate-800">
        <p className="truncate font-medium">{me.name ?? me.email ?? me.subject}</p>
        <p className="truncate text-xs text-slate-500">{me.email}</p>
        <div className="mt-2 flex gap-3 text-xs">
          {me.is_admin && (
            <button type="button" onClick={() => go("/admin")} className="text-blue-700 hover:underline dark:text-blue-300">
              Admin
            </button>
          )}
          <button type="button" onClick={() => void logout()} className="text-slate-600 hover:underline dark:text-slate-400">
            Sign out
          </button>
        </div>
      </div>
    </nav>
  );
}
