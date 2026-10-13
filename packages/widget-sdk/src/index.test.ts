import { beforeEach, describe, expect, it, vi } from "vitest";
import { EnterpriseChatElement, mount } from "./index";
import { envelope, sanitizeContext } from "./protocol";

const CHAT = "https://chat.example.com";

function create(): EnterpriseChatElement {
  return mount({ appId: "hr-portal", baseUrl: CHAT, context: { page: "/leave" } });
}

function iframeOf(el: EnterpriseChatElement): HTMLIFrameElement | null {
  return el.shadowRoot!.querySelector("iframe");
}

function fromIframe(el: EnterpriseChatElement, data: unknown, origin = CHAT): void {
  window.dispatchEvent(
    new MessageEvent("message", { data, origin, source: iframeOf(el)!.contentWindow }),
  );
}

describe("<enterprise-chat>", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("creates the iframe lazily, pointing at /embed for the app", () => {
    const el = create();
    expect(iframeOf(el)).toBeNull();
    el.open();
    expect(iframeOf(el)!.src).toBe(`${CHAT}/embed?app=hr-portal`);
    expect(el.isOpen).toBe(true);
  });

  it("sends context only after the iframe reports ready, to the chat origin only", () => {
    const el = create();
    el.open();
    const post = vi.spyOn(iframeOf(el)!.contentWindow!, "postMessage");

    fromIframe(el, envelope({ type: "ready" }), "https://evil.example");
    expect(post).not.toHaveBeenCalled();

    fromIframe(el, envelope({ type: "ready" }));
    expect(post).toHaveBeenCalledWith(
      envelope({ type: "context", context: { page: "/leave" } }),
      CHAT,
    );
  });

  it("closes when the iframe asks to", () => {
    const el = create();
    el.open();
    fromIframe(el, envelope({ type: "close" }));
    expect(el.isOpen).toBe(false);
  });

  it("ignores messages that are not protocol envelopes", () => {
    const el = create();
    el.open();
    fromIframe(el, { type: "close" });
    expect(el.isOpen).toBe(true);
  });
});

describe("sanitizeContext", () => {
  it("keeps known fields as bounded strings", () => {
    expect(
      sanitizeContext({
        page: "x".repeat(600),
        module: 42,
        record: { type: "invoice", id: "INV-1" },
        evil: "<script>",
      }),
    ).toEqual({ page: "x".repeat(500), module: "42", record: { type: "invoice", id: "INV-1" } });
    expect(sanitizeContext(null)).toEqual({});
    expect(sanitizeContext({ record: { type: "invoice" } })).toEqual({});
  });
});
