import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";
import { api } from "../api/client";
import type { AuditEvent, KnowledgeDocument, KnowledgeSource } from "../api/types";
import { navigate } from "../lib/router";

const input =
  "w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900";
const button =
  "rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50";

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-xl border border-slate-200 p-4 dark:border-slate-800">
      <h2 className="mb-3 text-base font-semibold">{title}</h2>
      {children}
    </section>
  );
}

export function AdminPage() {
  const [sources, setSources] = useState<KnowledgeSource[]>([]);
  const [selected, setSelected] = useState<KnowledgeSource | null>(null);
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const loadSources = useCallback(async () => {
    const list = await api<KnowledgeSource[]>("/api/v1/admin/knowledge/sources");
    setSources(list);
    setSelected((current) => list.find((s) => s.id === current?.id) ?? list[0] ?? null);
  }, []);
  const loadAudit = useCallback(
    () => api<AuditEvent[]>("/api/v1/admin/audit?limit=50").then(setAudit),
    [],
  );

  useEffect(() => {
    loadSources().catch((e: Error) => setMessage(e.message));
    loadAudit().catch(() => undefined);
  }, [loadSources, loadAudit]);

  useEffect(() => {
    if (!selected) {
      setDocuments([]);
      return;
    }
    api<KnowledgeDocument[]>(`/api/v1/admin/knowledge/sources/${selected.id}/documents`)
      .then(setDocuments)
      .catch((e: Error) => setMessage(e.message));
  }, [selected]);

  const run = async (action: () => Promise<string>) => {
    setBusy(true);
    setMessage(null);
    try {
      setMessage(await action());
      await loadSources();
      await loadAudit();
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const createSource = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    void run(async () => {
      await api("/api/v1/admin/knowledge/sources", {
        method: "POST",
        json: {
          slug: data.get("slug"),
          name: data.get("name"),
          application_id: (data.get("application_id") as string) || null,
          acl_roles: String(data.get("acl_roles") ?? "")
            .split(",")
            .map((r) => r.trim())
            .filter(Boolean),
        },
      });
      form.reset();
      return "Knowledge source created.";
    });
  };

  const upload = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selected) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    if (!data.get("title")) data.delete("title");
    if (!data.get("uri")) data.delete("uri");
    void run(async () => {
      const result = await api<{ status: string; document: KnowledgeDocument }>(
        `/api/v1/admin/knowledge/sources/${selected.id}/documents`,
        { method: "POST", body: data },
      );
      form.reset();
      setSelected({ ...selected });
      return `“${result.document.title}”: ${result.status} (${result.document.chunk_count} chunks).`;
    });
  };

  const remove = (doc: KnowledgeDocument) => {
    if (!selected || !window.confirm(`Delete “${doc.title}”? It will no longer be used in answers.`)) return;
    void run(async () => {
      await api(`/api/v1/admin/knowledge/documents/${doc.id}`, { method: "DELETE" });
      setSelected({ ...selected });
      return `Deleted “${doc.title}”.`;
    });
  };

  return (
    <div className="mx-auto max-w-5xl space-y-4 p-4">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Administration</h1>
        <button type="button" onClick={() => navigate("/")} className="text-sm text-blue-700 hover:underline dark:text-blue-300">
          ← Back to chat
        </button>
      </header>
      {message && (
        <p role="status" className="rounded-md bg-slate-100 px-3 py-2 text-sm dark:bg-slate-800">
          {message}
        </p>
      )}

      <Section title="Knowledge sources">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase text-slate-500">
              <tr>
                <th className="py-1">Name</th>
                <th>Slug</th>
                <th>Application</th>
                <th>Visible to roles</th>
                <th className="text-right">Docs</th>
              </tr>
            </thead>
            <tbody>
              {sources.map((s) => (
                <tr
                  key={s.id}
                  onClick={() => setSelected(s)}
                  className={`cursor-pointer border-t border-slate-100 dark:border-slate-800 ${
                    selected?.id === s.id ? "bg-blue-50 dark:bg-blue-950" : ""
                  }`}
                >
                  <td className="py-1.5 font-medium">{s.name}</td>
                  <td className="font-mono text-xs">{s.slug}</td>
                  <td>{s.application_id ?? "—"}</td>
                  <td>{s.acl_roles.length ? s.acl_roles.join(", ") : "Everyone"}</td>
                  <td className="text-right">{s.document_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <form onSubmit={createSource} className="mt-4 grid gap-2 sm:grid-cols-5">
          <input name="slug" required pattern="[a-z0-9][a-z0-9\-]{1,63}" placeholder="slug" className={input} />
          <input name="name" required placeholder="Name" className={input} />
          <input name="application_id" placeholder="Application id (optional)" className={input} />
          <input name="acl_roles" placeholder="Roles, comma-separated (empty = all)" className={input} />
          <button type="submit" disabled={busy} className={button}>
            Add source
          </button>
        </form>
      </Section>

      {selected && (
        <Section title={`Documents in “${selected.name}”`}>
          <ul className="divide-y divide-slate-100 text-sm dark:divide-slate-800">
            {documents.map((doc) => (
              <li key={doc.id} className="flex items-center gap-3 py-1.5">
                <span className="flex-1 truncate font-medium">{doc.title}</span>
                <span className="text-xs text-slate-500">{doc.chunk_count} chunks</span>
                <span className="text-xs text-slate-500">{new Date(doc.updated_at).toLocaleString()}</span>
                <button type="button" onClick={() => remove(doc)} className="text-xs text-red-700 hover:underline dark:text-red-300">
                  Delete
                </button>
              </li>
            ))}
            {documents.length === 0 && <li className="py-1.5 text-slate-500">No documents yet.</li>}
          </ul>
          <form onSubmit={upload} className="mt-4 grid gap-2 sm:grid-cols-4">
            <input name="file" type="file" required accept=".md,.markdown,.txt,.pdf" className="text-sm sm:col-span-1" />
            <input name="title" placeholder="Title (optional)" className={input} />
            <input name="uri" type="url" placeholder="Link to original (optional)" className={input} />
            <button type="submit" disabled={busy} className={button}>
              {busy ? "Working…" : "Upload"}
            </button>
          </form>
        </Section>
      )}

      <Section title="Recent audit events">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="uppercase text-slate-500">
              <tr>
                <th className="py-1">Time</th>
                <th>Actor</th>
                <th>Action</th>
                <th>Outcome</th>
                <th>Resource</th>
              </tr>
            </thead>
            <tbody>
              {audit.map((e) => (
                <tr key={e.id} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="whitespace-nowrap py-1">{new Date(e.occurred_at).toLocaleString()}</td>
                  <td>{e.actor_subject ?? "—"}</td>
                  <td className="font-mono">{e.action}</td>
                  <td className={e.outcome === "success" ? "" : "text-red-700 dark:text-red-300"}>{e.outcome}</td>
                  <td className="truncate font-mono">
                    {e.resource_type ? `${e.resource_type}:${e.resource_id}` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>
    </div>
  );
}
