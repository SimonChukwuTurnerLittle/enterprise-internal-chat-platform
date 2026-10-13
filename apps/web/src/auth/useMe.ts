import { useCallback, useEffect, useState } from "react";
import { ApiError, api, setCsrfToken } from "../api/client";
import type { Me } from "../api/types";

export type AuthState =
  | { status: "loading" }
  | { status: "authenticated"; me: Me }
  | { status: "unauthenticated" }
  | { status: "error"; message: string };

export function useMe(): AuthState & { reload: () => void } {
  const [state, setState] = useState<AuthState>({ status: "loading" });

  const reload = useCallback(() => {
    api<Me>("/api/auth/me")
      .then((me) => {
        setCsrfToken(me.csrf_token);
        setState({ status: "authenticated", me });
      })
      .catch((error: unknown) => {
        setCsrfToken(null);
        if (error instanceof ApiError && error.status === 401) {
          setState({ status: "unauthenticated" });
        } else {
          setState({ status: "error", message: String((error as Error).message ?? error) });
        }
      });
  }, []);

  useEffect(reload, [reload]);
  return { ...state, reload };
}

export async function logout(): Promise<void> {
  const { logout_url } = await api<{ logout_url: string | null }>("/api/auth/logout", {
    method: "POST",
  });
  setCsrfToken(null);
  window.location.assign(logout_url ?? "/");
}
