import { useEffect, type ReactNode } from "react";
import { loginUrl } from "./api/client";
import { useMe } from "./auth/useMe";
import { conversationIdFromPath, usePathname } from "./lib/router";
import { AdminPage } from "./pages/AdminPage";
import { ChatPage } from "./pages/ChatPage";
import { EmbedPage } from "./pages/EmbedPage";
import { PopupDone } from "./pages/PopupDone";

export function App() {
  const pathname = usePathname();
  if (pathname === "/embed") return <EmbedPage />;
  if (pathname === "/auth/popup-done") return <PopupDone />;
  return <SignedInApp pathname={pathname} />;
}

function Notice({ children }: { children: ReactNode }) {
  return <div className="grid h-full place-items-center p-6 text-sm text-slate-600 dark:text-slate-400">{children}</div>;
}

function SignedInApp({ pathname }: { pathname: string }) {
  const auth = useMe();

  useEffect(() => {
    if (auth.status === "unauthenticated") {
      window.location.assign(loginUrl(pathname + window.location.search));
    }
  }, [auth.status, pathname]);

  if (auth.status === "loading" || auth.status === "unauthenticated") {
    return <Notice>Signing you in…</Notice>;
  }
  if (auth.status === "error") {
    return (
      <Notice>
        <div className="text-center">
          <p>The assistant is unavailable right now ({auth.message}).</p>
          <button type="button" onClick={auth.reload} className="mt-2 text-blue-700 underline">
            Try again
          </button>
        </div>
      </Notice>
    );
  }
  if (pathname === "/admin") {
    return auth.me.is_admin ? <AdminPage /> : <Notice>You need the administrator role to view this page.</Notice>;
  }
  return <ChatPage me={auth.me} conversationId={conversationIdFromPath(pathname)} />;
}
