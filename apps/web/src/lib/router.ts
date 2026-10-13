import { useSyncExternalStore } from "react";

// A handful of routes do not justify a router dependency: /, /c/:id, /admin, /embed.

function subscribe(onChange: () => void): () => void {
  window.addEventListener("popstate", onChange);
  return () => window.removeEventListener("popstate", onChange);
}

export function usePathname(): string {
  return useSyncExternalStore(subscribe, () => window.location.pathname);
}

export function navigate(to: string, options: { replace?: boolean } = {}): void {
  if (options.replace) window.history.replaceState(null, "", to);
  else window.history.pushState(null, "", to);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

export function conversationIdFromPath(pathname: string): string | null {
  const match = /^\/c\/([0-9a-f-]{36})$/i.exec(pathname);
  return match ? match[1] : null;
}
