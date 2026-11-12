import { Badge } from "@/components/Badge";
import type { Doc, Revision } from "@/lib/api";

export const dynamic = "force-dynamic";
const API = process.env.API_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Chunk = { id: string; ordinal: number; heading: string | null; content: string; char_count: number; technical_tokens: string[]; has_embedding: boolean };

export default async function DocumentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const doc = (await (await fetch(`${API}/api/documents/${id}`, { cache: "no-store" })).json()) as Doc & { revisions: Revision[] };
  const cur = doc.current_revision;
  const chunks: Chunk[] = cur ? await (await fetch(`${API}/api/revisions/${cur.id}/chunks`, { cache: "no-store" })).json() : [];
  return (
    <div className="space-y-6">
      <header>
        <a className="muted text-sm underline" href="/knowledge-base">← Knowledge Base</a>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">{doc.title}</h1>
        <div className="muted font-mono text-xs">{doc.external_id} · {doc.source_name} · <Badge value={doc.trust_level} /></div>
      </header>
      {cur && (
        <section className="card grid gap-3 text-sm md:grid-cols-3">
          <div><div className="muted">Applies to</div>{cur.effective_from ?? "unknown"} → {cur.effective_to ?? (cur.applicability_provenance === "unknown" ? "unknown" : "open")} <Badge value={cur.applicability_provenance} /></div>
          <div><div className="muted">Published / updated</div>{cur.published_at ?? "—"} / {cur.last_updated_at ?? "—"}</div>
          <div><div className="muted">Field provenance</div>{Object.entries(cur.metadata_provenance).map(([k, v]) => <span key={k} className="mr-2">{k}: <Badge value={v} /></span>) || "—"}</div>
          <div className="md:col-span-3"><div className="muted">Technical tokens</div><div className="font-mono text-xs">{cur.technical_tokens.join("  ") || "—"}</div></div>
        </section>
      )}
      <section className="card">
        <h2 className="mb-2 font-medium">Revision history</h2>
        <ul className="text-sm">{doc.revisions.map(r => <li key={r.id} className="flex gap-3 border-t border-zinc-100 py-1 first:border-0 dark:border-zinc-800"><span>rev {r.revision_number}</span><span className="font-mono text-xs">{r.checksum.slice(0, 12)}</span><span className="muted">{new Date(r.ingested_at).toISOString()}</span>{cur?.id === r.id && <Badge value="current" />}</li>)}</ul>
      </section>
      <section className="space-y-2">
        <h2 className="font-medium">Chunks ({chunks.length})</h2>
        {chunks.map(c => (
          <article key={c.id} className="card">
            <div className="muted text-xs">#{c.ordinal} {c.heading ? `· ${c.heading}` : ""} · {c.char_count} chars · embedding {c.has_embedding ? "yes" : "none"}</div>
            <pre className="mt-2 whitespace-pre-wrap font-mono text-xs">{c.content}</pre>
          </article>
        ))}
      </section>
    </div>
  );
}
