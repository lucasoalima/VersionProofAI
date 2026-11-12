"use client";
import { useEffect, useState } from "react";
import { Badge } from "@/components/Badge";
import { PUBLIC_API, type Evidence, type Product, type ProductDetail, type SearchResponse } from "@/lib/api";

export function AskForm({ products }: { products: Product[] }) {
  const [product, setProduct] = useState(products[0]?.slug ?? "");
  const [releases, setReleases] = useState<string[]>([]);
  const [version, setVersion] = useState("");
  const [mode, setMode] = useState("lexical");
  const [enforce, setEnforce] = useState(true);
  const [query, setQuery] = useState("");
  const [res, setRes] = useState<SearchResponse | null>(null);
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
      const r = await fetch(`${PUBLIC_API}/api/search`, {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ query, product, target_version: version || null, mode, enforce_version: enforce, top_k: 10 }),
      });
      const body = await r.json();
      if (!r.ok) throw new Error(body.detail ?? r.statusText);
      setRes(body as SearchResponse);
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
          <label className="flex items-end gap-2 pb-2 text-sm"><input type="checkbox" checked={enforce} onChange={e => setEnforce(e.target.checked)} /> Enforce version as constraint</label>
        </div>
        <textarea className="w-full rounded-md border border-zinc-300 bg-transparent p-2 font-mono text-sm dark:border-zinc-700" rows={3} placeholder="Is this workaround still required in release X?" value={query} onChange={e => setQuery(e.target.value)} />
        <button disabled={busy || query.length < 2 || !product} className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900">{busy ? "Retrieving…" : "Retrieve evidence"}</button>
      </form>

      {error && <div className="card border-rose-300 text-sm">{error}</div>}

      {res && (
        <section className="space-y-3">
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <span className="muted">{res.results.length} result(s) · {res.retrieval_latency_ms} ms · {res.mode}</span>
            {res.target_version && <Badge value={`target ${res.target_version}`} />}
            {!res.enforce_version && <Badge value="version not enforced" />}
          </div>
          {res.notices.map(n => <div key={n} className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">{n}</div>)}
          <div className="card border-zinc-300 text-sm">
            <strong>Answer generation is not configured.</strong> Phase 3 adds a grounded answer engine with abstention. Until then, inspect the evidence directly — the applicability badge tells you whether each source is verified for the target version.
          </div>
          {res.results.map(r => <EvidenceCard key={r.chunk_id} e={r} />)}
          {res.results.length === 0 && <p className="muted">No matching evidence. Nothing in the knowledge base satisfies the query under the current constraints.</p>}
          {res.excluded.length > 0 && (
            <div className="space-y-2 border-t border-dashed border-rose-300 pt-4 dark:border-rose-800">
              <h3 className="text-sm font-medium">Relevant but not applicable to {res.target_version}</h3>
              <p className="muted text-xs">These sources match the question but are verified for other releases. They explain what exists elsewhere; they are never recommendations for the target version.</p>
              {res.excluded.map(r => <EvidenceCard key={r.chunk_id} e={r} />)}
            </div>
          )}
        </section>
      )}
    </div>
  );
}

function EvidenceCard({ e }: { e: Evidence }) {
  const [open, setOpen] = useState(false);
  return (
    <article className="card">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="font-medium">#{e.rank} {e.title}</div>
          <div className="muted text-xs">{e.heading ? `§ ${e.heading} · ` : ""}score {e.score.toFixed(3)} · {e.strategy} · query {String(e.diagnostics.query_mode)}</div>
        </div>
        <div className="flex flex-wrap gap-1">
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
