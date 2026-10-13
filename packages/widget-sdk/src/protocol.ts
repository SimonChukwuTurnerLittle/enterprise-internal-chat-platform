/**
 * postMessage protocol between a host application page and the chat iframe (/embed).
 * Both sides check `event.origin` and `event.source` before trusting a message.
 */

export const PROTOCOL = "ecp-chat";
export const PROTOCOL_VERSION = 1;

export interface RecordRef {
  type: string;
  id: string;
}

/** Where the employee is in the host app. An unverified hint: never used for authorisation. */
export interface HostContext {
  page?: string;
  module?: string;
  title?: string;
  record?: RecordRef;
}

export type HostToWidgetMessage =
  | { type: "context"; context: HostContext }
  | { type: "focus" };

export type WidgetToHostMessage =
  | { type: "ready" }
  | { type: "close" }
  | { type: "authenticated" }
  | { type: "unauthenticated" };

export type Envelope<T> = T & { protocol: typeof PROTOCOL; version: typeof PROTOCOL_VERSION };

export function envelope<T extends { type: string }>(message: T): Envelope<T> {
  return { ...message, protocol: PROTOCOL, version: PROTOCOL_VERSION };
}

export function isEnvelope(data: unknown): data is Envelope<{ type: string }> {
  return (
    typeof data === "object" &&
    data !== null &&
    (data as Record<string, unknown>).protocol === PROTOCOL &&
    (data as Record<string, unknown>).version === PROTOCOL_VERSION &&
    typeof (data as Record<string, unknown>).type === "string"
  );
}

// Same limits as the API's HostContext model.
const LIMITS = { page: 500, module: 100, title: 200, recordType: 50, recordId: 100 };

function clip(value: unknown, max: number): string | undefined {
  if (typeof value !== "string" && typeof value !== "number") return undefined;
  const text = String(value).trim();
  return text ? text.slice(0, max) : undefined;
}

/** Keep only known fields, as bounded strings. */
export function sanitizeContext(input: unknown): HostContext {
  if (typeof input !== "object" || input === null) return {};
  const raw = input as Record<string, unknown>;
  const context: HostContext = {};
  const page = clip(raw.page, LIMITS.page);
  const module = clip(raw.module, LIMITS.module);
  const title = clip(raw.title, LIMITS.title);
  if (page) context.page = page;
  if (module) context.module = module;
  if (title) context.title = title;
  if (typeof raw.record === "object" && raw.record !== null) {
    const record = raw.record as Record<string, unknown>;
    const type = clip(record.type, LIMITS.recordType);
    const id = clip(record.id, LIMITS.recordId);
    if (type && id) context.record = { type, id };
  }
  return context;
}
