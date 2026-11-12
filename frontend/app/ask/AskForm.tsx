"use client";
import { useEffect, useState } from "react";
import { Badge } from "@/components/Badge";
import { PUBLIC_API, type Answer, type Evidence, type Product, type ProductDetail } from "@/lib/api";

export function AskForm({ products }: { products: Product[] }) {
  const [product, setProduct] = useState(products[0]?.slug ?? "");
  const [releases, setReleases] = useState<string[]>([]);
  const [version, setVersion] = useState("");
  const [mode, setMode] = useState("lexical");
    const [query, setQuery] = useState("");
  const [res, setRes] = useState<Answer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!product) return;
    fetch(`${PUBLIC_API}/api/products/${product}`).then(r => r.json()).then((p: ProductDetail) => {
      const labels = p.releases.map(r => r.label);
      setReleases(labels);
      setVersion(labels[labels.length - 1] ?? "");
    }).catch(() => setReleases([]));
  }, [product]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null); setRes(null);
    try {
      const r = await fetch(`${PUBLIC_API}/api/ask`, {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ question: query, product, target_version: version || null, mode, top_k: 5 }),
      });
      const body = await r.json();
      if (!r.ok) throw new Error(body.detail ?? r.statusText);
      setRes(body as Answer);
    } catch (err) { setError(String((err as Error).message)); } finally { setBusy(false); }
  }

  return (
    <div className="space-y-6">
      <form onSubmit={submit} className="card space-y-4">
        <div className="grid gap-3 md:grid-cols-4">
          <label className="text-sm"><div className="muted mb-1">Product</div>
            <select className="w-full rounded-md border border-zinc-300 bg-transparent p-2 dark:border-zinc-700" value={product} onChange={e => setProduct(e.target.value)}>
              {products.map(p => <option key={p.slug} value={p.slug}>{p.name}</option>)}
            </select></label>
          <label className="text-sm"><div className="muted mb-1">Target version</div>
            <select className="w-full rounded-md border border-zinc-300 bg-transparent p-2 dark:border-zinc-700" value={version} onChange={e => setVersion(e.target.value)}>
              <option value="">(none — unfiltered)</option>
              {releases.map(l => <option key={l} value={l}>{l}</option>)}
            </select></label>
          <label className="text-sm"><div className="muted mb-1">Retrieval mode</div>
            <select className="w-full rounded-md border border-zinc-300 bg-transparent p-2 dark:border-zinc-700" value={mode} onChange={e => setMode(e.target.value)}>
              <option value="lexical">lexical (PostgreSQL FTS)</option>
              <option value="semantic">semantic (pgvector cosine)</option>
              <option value="hybrid">hybrid (RRF)</option>
            </select></label>
          <div className="muted flex items-end pb-2 text-xs">Version is always enforced as a constraint here. Unconstrained retrieval is available in the Evaluation Lab as the traditional-RAG baseline.</div>
        </div>
        <textarea className="w-full rounded-md border border-zinc-300 bg-transparent p-2 font-mono text-sm dark:border-zinc-700" rows={3} placeholder="Is this workaround still required in release X?" value={query} onChange={e => setQuery(e.target.value)} />
        <button disabled={busy || query.length < 2 || !product} className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900">{busy ? "Answering…" : "Ask"}</button>
      </form>

      {error && <div className="card border-rose-300 text-sm">{error}</div>}

      {res && (
        <section className="space-y-3">
          <article className={`card ${res.abstained ? "border-amber-300 dark:border-amber-800" : ""}`}>
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <Badge value={res.abstained ? "abstained" : res.applicability_status} />
              {res.target_version && <Badge value={`target ${res.target_version}`} />}
              <Badge value={res.generation_mode === "llm" ? `llm ${res.model_identifier}` : res.generation_mode} />
              <span className="muted text-xs">{String(res.diagnostics.end_to_end_latency_ms)} ms · coverage {String(res.diagnostics.coverage_results)}</span>
            </div>
            <p className="whitespace-pre-wrap text-sm leading-relaxed">{res.answer}</p>
            {res.generation_mode !== "llm" && <p className="muted mt-2 text-xs">Extractive answer: text quoted from the best-covering source, no language model involved.</p>}
            {res.citations.length > 0 && <p className="muted mt-2 text-xs">Cited: {res.evidence.filter(e => res.citations.includes(e.chunk_id)).map(e => `#${e.rank} ${e.title}`).join(" · ")}</p>}
          </article>
          {res.warnings.map(n => <div key={n} className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">{n}</div>)}
          {res.conflicts.map(c => <div key={c.chunk_ids.join()} className="rounded-md border border-rose-300 bg-rose-50 p-3 text-sm text-rose-900 dark:border-rose-800 dark:bg-rose-950 dark:text-rose-200"><b>Conflict:</b> “{c.titles[0]}” states {c.differing_values[0].join(", ")} · “{c.titles[1]}” states {c.differing_values[1].join(", ")}</div>)}
          {res.unresolved_questions.length > 0 && <div className="card text-sm"><b>Unresolved:</b><ul className="list-disc pl-5">{res.unresolved_questions.map(q => <li key={q}>{q}</li>)}</ul></div>}
          <h3 className="pt-2 text-sm font-medium">Evidence ({res.evidence.length})</h3>
          {res.evidence.map(r => <EvidenceCard key={r.chunk_id} e={r} cited={res.citations.includes(r.chunk_id)} />)}
          {res.excluded.length > 0 && (
            <div className="space-y-2 border-t border-dashed border-rose-300 pt-4 dark:border-rose-800">
              <h3 className="text-sm font-medium">Relevant but not applicable to {res.target_version}</h3>
              <p className="muted text-xs">These sources match the question but are verified for other releases. They explain what exists elsewhere; they are never recommendations for the target version.</p>
              {res.excluded.map(r => <EvidenceCard key={r.chunk_id} e={r} cited={false} />)}
            </div>
          )}
        </section>
      )}
    </div>
  );
}

function EvidenceCard({ e, cited }: { e: Evidence; cited: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <article className="card">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="font-medium">#{e.rank} {e.title}</div>
          <div className="muted text-xs">{e.heading ? `§ ${e.heading} · ` : ""}score {e.score.toFixed(3)} · {e.strategy}</div>
        </div>
        <div className="flex flex-wrap gap-1">
          {cited && <Badge value="cited" />}
          <Badge value={e.applicability_status} />
          <Badge value={e.applicability_provenance} />
          <Badge value={e.trust_level} />
        </div>
      </div>
      <div className="muted mt-2 text-xs">
        Applies to: {e.effective_from ?? "unknown"} → {e.effective_to ?? (e.applicability_provenance === "unknown" ? "unknown" : "open")}
        {e.published_at && <> · published {e.published_at}</>}
        {e.source_url && <> · <a className="underline" href={e.source_url} target="_blank" rel="noreferrer">source</a></>}
      </div>
      <pre className={`mt-3 whitespace-pre-wrap rounded-md bg-zinc-50 p-3 font-mono text-xs dark:bg-zinc-950 ${open ? "" : "max-h-24 overflow-hidden"}`}>{e.excerpt}</pre>
      <button className="muted mt-1 text-xs underline" onClick={() => setOpen(!open)}>{open ? "collapse" : "expand excerpt"}</button>
    </article>
  );
}
