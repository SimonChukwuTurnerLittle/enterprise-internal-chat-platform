# Embedding the chat widget

For teams adding the assistant to an existing internal application.

## 1. Register your application

Ask a platform admin to register your app with:

- **id**: short slug, e.g. `hr-portal`
- **name** shown in the widget header
- **allowed origins**: every origin that will embed the widget, e.g. `https://hr.example.com`

The platform also adds your origins to `FRAME_ANCESTORS` on the web container. Pages on other origins see "not authorised to embed".

## 2. Add the widget

Any page, any framework:

```html
<script src="https://chat.example.com/sdk/v1/chat-widget.js" async></script>
<enterprise-chat app-id="hr-portal"></enterprise-chat>
```

Optional attributes: `position="bottom-left"`, `open` (start opened), `base-url` (only needed when the script is served from a different origin than the chat).

Or from JavaScript:

```js
const chat = EnterpriseChat.mount({ appId: "hr-portal", context: { page: location.pathname } });
```

## 3. Tell the assistant where the user is

Call `setContext` whenever the page or record changes (for SPAs, on every route change):

```js
document.querySelector("enterprise-chat").setContext({
  page: "/leave/requests/LR-2041",
  module: "Leave",
  title: "Leave request LR-2041",
  record: { type: "leave-request", id: "LR-2041" },
});
```

Fields are trimmed to safe lengths, and unknown fields are dropped. In milestone 1, context is a **hint** used to prefer your app's knowledge. It never grants access. Milestone 2 adds signed context tokens for record-aware answers.

## Framework notes

**React 19:** custom elements work directly in JSX.

```tsx
export function Assistant({ invoiceId }: { invoiceId?: string }) {
  const ref = useRef<HTMLElement & { setContext(c: object): void }>(null);
  useEffect(() => {
    ref.current?.setContext({ module: "Invoices", record: invoiceId ? { type: "invoice", id: invoiceId } : undefined });
  }, [invoiceId]);
  return <enterprise-chat ref={ref} app-id="finance" />;
}
```

For TypeScript, declare the element once: `declare module "react" { namespace JSX { interface IntrinsicElements { "enterprise-chat": any } } }`.

**Angular:** add `CUSTOM_ELEMENTS_SCHEMA` to the component or module `schemas`, then use `<enterprise-chat app-id="…">` in templates and call `setContext` via `@ViewChild`.

**Vue 3:** tell the compiler it is a custom element (`compilerOptions.isCustomElement: tag => tag === "enterprise-chat"`), then use it in templates.

**ASP.NET (MVC / Razor / Web Forms) and legacy pages:** paste the two HTML lines into the shared layout (`_Layout.cshtml` or master page).

## Events

The element dispatches DOM events you can listen to: `ecp-ready`, `ecp-open`, `ecp-close`, `ecp-authenticated`, `ecp-unauthenticated`.

## Theming

Override CSS variables on the element: `enterprise-chat { --ecp-accent: #0f766e; }`, or style the shadow parts `::part(launcher)` and `::part(panel)`.

## Security model

- The chat runs in a sandboxed iframe on the platform's origin. Your page never sees the employee's chat session or tokens, and the chat cannot read your page.
- Messages are only accepted from the registered host origin (iframe side) and from the chat origin (host side).
- Employees sign in with company SSO. When the chat is on the same site as your app (e.g. `chat.example.com` and `hr.example.com`), an existing session is reused automatically. Otherwise they click **Sign in** once and a popup completes SSO.
