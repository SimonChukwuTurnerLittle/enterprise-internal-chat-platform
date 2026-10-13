export type { HostContext, RecordRef } from "@ecp/widget-sdk/protocol";

export interface Me {
  user_id: string;
  subject: string;
  email: string | null;
  name: string | null;
  roles: string[];
  is_admin: boolean;
  csrf_token: string | null;
}

export interface Conversation {
  id: string;
  title: string | null;
  origin_app_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface Citation {
  n: number;
  document_id: string;
  document_title: string;
  source_name: string;
  heading: string | null;
  uri: string | null;
  snippet: string;
  score: number;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  created_at: string;
}

export interface ConversationDetail extends Conversation {
  messages: Message[];
}

export interface WidgetConfig {
  app_id: string;
  name: string;
  allowed_origins: string[];
}

export interface KnowledgeSource {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  application_id: string | null;
  acl_roles: string[];
  document_count: number;
}

export interface KnowledgeDocument {
  id: string;
  title: string;
  uri: string | null;
  content_type: string;
  chunk_count: number;
  uploaded_by: string | null;
  updated_at: string;
}

export interface AuditEvent {
  id: number;
  occurred_at: string;
  action: string;
  outcome: string;
  actor_subject: string | null;
  resource_type: string | null;
  resource_id: string | null;
  application_id: string | null;
  details: Record<string, unknown>;
}
