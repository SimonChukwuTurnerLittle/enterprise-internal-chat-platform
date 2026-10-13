import { useEffect } from "react";

export const LOGIN_COMPLETE_MESSAGE = "ecp:login-complete";

/** Landing page of the sign-in popup opened by the embedded widget. */
export function PopupDone() {
  useEffect(() => {
    window.opener?.postMessage({ type: LOGIN_COMPLETE_MESSAGE }, window.location.origin);
    window.close();
  }, []);
  return <p className="p-6 text-sm">Signed in. You can close this window.</p>;
}
