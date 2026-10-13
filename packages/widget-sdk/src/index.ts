/**
 * <enterprise-chat> — drop-in chat launcher for any web page.
 *
 *   <script src="https://chat.example.com/sdk/v1/chat-widget.js" async></script>
 *   <enterprise-chat app-id="hr-portal"></enterprise-chat>
 *
 * The chat itself runs in an iframe served by the chat platform, so it keeps its own
 * session, styles and release cycle. The host page only passes context via setContext().
 */
import {
  envelope,
  isEnvelope,
  sanitizeContext,
  type HostContext,
  type HostToWidgetMessage,
} from "./protocol";

export type { HostContext, RecordRef } from "./protocol";

// Default chat origin: wherever this script was loaded from.
const scriptOrigin = (() => {
  const script = document.currentScript as HTMLScriptElement | null;
  try {
    return script?.src ? new URL(script.src).origin : window.location.origin;
  } catch {
    return window.location.origin;
  }
})();

const CHAT_ICON = `<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>`;
const CLOSE_ICON = `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>`;

const STYLE = `
  :host { position: fixed; z-index: 2147483000; bottom: 20px; right: 20px;
          --ecp-accent: #2563eb; --ecp-accent-text: #fff; font-family: system-ui, sans-serif; }
  :host([position="bottom-left"]) { right: auto; left: 20px; }
  .launcher { width: 56px; height: 56px; border-radius: 50%; border: 0; cursor: pointer;
              background: var(--ecp-accent); color: var(--ecp-accent-text);
              display: grid; place-items: center; box-shadow: 0 6px 20px rgb(0 0 0 / .25); }
  .launcher:focus-visible { outline: 3px solid #93c5fd; outline-offset: 2px; }
  .panel { position: absolute; bottom: 72px; right: 0; display: none; overflow: hidden;
           width: min(400px, calc(100vw - 32px)); height: min(640px, calc(100vh - 112px));
           border-radius: 14px; background: #fff; box-shadow: 0 12px 40px rgb(0 0 0 / .3); }
  :host([position="bottom-left"]) .panel { right: auto; left: 0; }
  .panel.open { display: block; }
  iframe { width: 100%; height: 100%; border: 0; display: block; }
  @media (max-width: 480px) {
    .panel { position: fixed; inset: 0; width: 100vw; height: 100dvh; border-radius: 0; }
  }
`;

export class EnterpriseChatElement extends HTMLElement {
  static observedAttributes = ["app-id", "base-url"];

  #button: HTMLButtonElement;
  #panel: HTMLDivElement;
  #iframe: HTMLIFrameElement | null = null;
  #context: HostContext = {};
  #ready = false;

  constructor() {
    super();
    const root = this.attachShadow({ mode: "open" });
    root.innerHTML = `<style>${STYLE}</style>
      <div class="panel" part="panel" role="dialog" aria-label="Chat assistant"></div>
      <button class="launcher" part="launcher" type="button" aria-expanded="false"
              aria-label="Open chat assistant">${CHAT_ICON}</button>`;
    this.#panel = root.querySelector<HTMLDivElement>(".panel")!;
    this.#button = root.querySelector<HTMLButtonElement>(".launcher")!;
    this.#button.addEventListener("click", () => this.toggle());
  }

  connectedCallback(): void {
    window.addEventListener("message", this.#onMessage);
    if (this.hasAttribute("open")) this.open();
  }

  disconnectedCallback(): void {
    window.removeEventListener("message", this.#onMessage);
  }

  attributeChangedCallback(): void {
    // App or chat origin changed: drop the old iframe; it is recreated on next open.
    this.#iframe?.remove();
    this.#iframe = null;
    this.#ready = false;
    if (this.isOpen) this.#ensureIframe();
  }

  get appId(): string {
    return this.getAttribute("app-id") ?? "";
  }

  get baseUrl(): string {
    return (this.getAttribute("base-url") || scriptOrigin).replace(/\/+$/, "");
  }

  get isOpen(): boolean {
    return this.#panel.classList.contains("open");
  }

  open(): void {
    this.#ensureIframe();
    this.#panel.classList.add("open");
    this.#button.setAttribute("aria-expanded", "true");
    this.#button.setAttribute("aria-label", "Close chat assistant");
    this.#button.innerHTML = CLOSE_ICON;
    this.#post({ type: "focus" });
    this.dispatchEvent(new CustomEvent("ecp-open"));
  }

  close(): void {
    this.#panel.classList.remove("open");
    this.#button.setAttribute("aria-expanded", "false");
    this.#button.setAttribute("aria-label", "Open chat assistant");
    this.#button.innerHTML = CHAT_ICON;
    this.#button.focus();
    this.dispatchEvent(new CustomEvent("ecp-close"));
  }

  toggle(): void {
    if (this.isOpen) this.close();
    else this.open();
  }

  /** Tell the chat where the user is; call again on SPA route changes. */
  setContext(context: HostContext): void {
    this.#context = sanitizeContext(context);
    this.#post({ type: "context", context: this.#context });
  }

  #widgetOrigin(): string {
    return new URL(this.baseUrl).origin;
  }

  #ensureIframe(): void {
    if (this.#iframe) return;
    const url = new URL("/embed", this.baseUrl);
    url.searchParams.set("app", this.appId);
    const iframe = document.createElement("iframe");
    iframe.title = "Chat assistant";
    iframe.src = url.toString();
    iframe.allow = "clipboard-write";
    iframe.setAttribute(
      "sandbox",
      "allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox",
    );
    this.#panel.append(iframe);
    this.#iframe = iframe;
  }

  #post(message: HostToWidgetMessage): void {
    if (!this.#ready || !this.#iframe?.contentWindow) return;
    this.#iframe.contentWindow.postMessage(envelope(message), this.#widgetOrigin());
  }

  #onMessage = (event: MessageEvent): void => {
    if (!this.#iframe || event.source !== this.#iframe.contentWindow) return;
    if (event.origin !== this.#widgetOrigin() || !isEnvelope(event.data)) return;
    switch (event.data.type) {
      case "ready":
        this.#ready = true;
        this.#post({ type: "context", context: this.#context });
        this.dispatchEvent(new CustomEvent("ecp-ready"));
        break;
      case "close":
        this.close();
        break;
      case "authenticated":
      case "unauthenticated":
        this.dispatchEvent(new CustomEvent(`ecp-${event.data.type}`));
        break;
    }
  };
}

if (!customElements.get("enterprise-chat")) {
  customElements.define("enterprise-chat", EnterpriseChatElement);
}

export interface MountOptions {
  appId: string;
  baseUrl?: string;
  context?: HostContext;
  position?: "bottom-right" | "bottom-left";
  open?: boolean;
}

/** Programmatic alternative to writing the tag: `EnterpriseChat.mount({ appId: "hr-portal" })`. */
export function mount(options: MountOptions): EnterpriseChatElement {
  const element = document.createElement("enterprise-chat") as EnterpriseChatElement;
  element.setAttribute("app-id", options.appId);
  if (options.baseUrl) element.setAttribute("base-url", options.baseUrl);
  if (options.position) element.setAttribute("position", options.position);
  if (options.open) element.setAttribute("open", "");
  document.body.append(element);
  if (options.context) element.setContext(options.context);
  return element;
}
