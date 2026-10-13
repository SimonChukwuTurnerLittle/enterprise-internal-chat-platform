import type { Citation } from "../api/types";

export function CitationList({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) return null;
  return (
    <div className="mt-3 border-t border-slate-200 pt-2 dark:border-slate-700">
      <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
        Sources
      </p>
      <ol className="space-y-1">
        {citations.map((citation) => (
          <li key={citation.n} className="text-xs">
            <details className="group">
              <summary className="cursor-pointer list-none text-slate-700 hover:text-blue-700 dark:text-slate-300 dark:hover:text-blue-300">
                <span className="mr-1 inline-flex h-4 min-w-4 items-center justify-center rounded bg-slate-200 px-1 font-mono text-[10px] text-slate-700 dark:bg-slate-700 dark:text-slate-200">
                  {citation.n}
                </span>
                <span className="font-medium">{citation.document_title}</span>
                {citation.heading && citation.heading !== citation.document_title && (
                  <span className="text-slate-500 dark:text-slate-400">
                    {" "}
                    › {citation.heading.split(" > ").slice(1).join(" › ") || citation.heading}
                  </span>
                )}
                <span className="text-slate-400"> · {citation.source_name}</span>
              </summary>
              <blockquote className="mt-1 border-l-2 border-slate-300 pl-2 text-slate-600 dark:border-slate-600 dark:text-slate-400">
                {citation.snippet}
                {citation.snippet.length >= 300 && "…"}
              </blockquote>
              {citation.uri && (
                <a
                  href={citation.uri}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-1 inline-block text-blue-700 underline dark:text-blue-300"
                >
                  Open document
                </a>
              )}
            </details>
          </li>
        ))}
      </ol>
    </div>
  );
}
