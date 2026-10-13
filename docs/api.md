# API reference

Interactive OpenAPI docs: `http://localhost:8000/api/docs` (disabled when `ENVIRONMENT=prod`).

## Authentication

| Client | How |
|---|---|
| Browser (web app, widget) | Session cookie from `/api/auth/login`. State-changing requests (`POST`, `PATCH`, `DELETE`) must send `X-CSRF-Token` with the value from `GET /api/auth/me`. |
| Services, scripts | `Authorization: Bearer <access token>` issued by the IdP for audience `OIDC_AUDIENCE`. No CSRF header needed. |

## Endpoints

| Method & path | Who | Purpose |
|---|---|---|
| `GET /api/auth/login?return_to=/path` | anyone | Start sign-in (302 to the IdP) |
| `GET /api/auth/callback` | IdP redirect | Finish sign-in, set session cookie |
| `POST /api/auth/logout` | signed in | End session; returns `{logout_url}` for IdP sign-out |
| `GET /api/auth/me` | signed in | Identity, roles, `is_admin`, `csrf_token` |
| `GET /api/v1/applications` | signed in | Enabled applications |
| `GET /api/v1/widget/config?app_id=` | public | App name and allowed embedding origins |
| `POST /api/v1/conversations` | signed in | Create `{origin_app_id?, title?}` |
| `GET /api/v1/conversations` | signed in | Own conversations, newest first |
| `GET /api/v1/conversations/{id}` | owner | Conversation with messages and citations |
| `PATCH /api/v1/conversations/{id}` | owner | Rename `{title}` |
| `DELETE /api/v1/conversations/{id}` | owner | Archive |
| `POST /api/v1/conversations/{id}/messages` | owner | Ask a question; **streams SSE** (below) |
| `GET /api/v1/admin/knowledge/sources` | admin | Knowledge sources with document counts |
| `POST /api/v1/admin/knowledge/sources` | admin | Create `{slug, name, description?, application_id?, acl_roles[]}` |
| `GET /api/v1/admin/knowledge/sources/{id}/documents` | admin | Documents in a source |
| `POST /api/v1/admin/knowledge/sources/{id}/documents` | admin | Multipart upload `file` (.md, .txt, .pdf), optional `title`, `uri` |
| `DELETE /api/v1/admin/knowledge/documents/{id}` | admin | Delete a document and its chunks |
| `GET /api/v1/admin/audit?action=&actor_subject=&before_id=&limit=` | admin | Audit events, newest first |
| `GET /api/healthz`, `GET /api/readyz` | anyone | Liveness; readiness (DB + Redis) |

Other users' conversations return `404`, not `403`, so their existence is not revealed.

## Sending a message (SSE)

Request:

```json
POST /api/v1/conversations/3f2c…/messages
{
  "content": "How many days of annual leave do I get?",
  "context": {
    "app_id": "hr-portal",
    "page": "/leave",
    "module": "Leave",
    "title": "My leave",
    "record": { "type": "leave-request", "id": "LR-2041" }
  }
}
```

`context` is optional and treated as an **unverified hint**: it can steer retrieval toward the app's knowledge, never access.

Response: `Content-Type: text/event-stream`, events in this order:

| Event | Data | Notes |
|---|---|---|
| `message.start` | `{message_id, user_message_id}` | Always first |
| `citations` | `{citations: [{n, document_id, document_title, source_name, heading, uri, snippet, score}]}` | Empty list → fallback answer follows |
| `token` | `{text}` | Repeated; concatenate in order |
| `error` | `{code, message}` | Terminal; replaces `message.end` |
| `message.end` | `{message_id}` | Answer complete and saved |

```
event: message.start
data: {"message_id":"…","user_message_id":"…"}

event: citations
data: {"citations":[{"n":1,"document_title":"Annual Leave Policy",…}]}

event: token
data: {"text":"Full-time "}
…
event: message.end
data: {"message_id":"…"}
```

If the client disconnects mid-answer, the partial answer is still saved and audited.

## Errors

Errors use RFC 7807 `application/problem+json`:

```json
{ "type": "about:blank", "title": "Too Many Requests", "status": 429,
  "detail": "Too many messages. Please wait a moment and try again.", "request_id": "9f1c…" }
```

Every response carries `X-Request-ID`; quote it when reporting problems, it links to the API logs and audit events.
