"use client";
import { useEffect, useState } from "react";
import { Badge } from "@/components/Badge";
import { PUBLIC_API, type Product, type ProductDetail } from "@/lib/api";

type Change = { document_id: string; external_id: string; title: string; source_url: string | null; classification: string; verified: boolean; provenance: string; basis: string; release: string | null; applies_from: string | null; applies_to: string | null; evidence_excerpt: string | null; note: string | null; paired_with: { title: string; external_id: string } | null; differing_values: string[][] | null; diff: string[] };
type Result = { summary: Record<string, number>; verified_changes: number; changes: Change[]; earlier: string; later: string };
type TimelineEvent = { document_id: string; title: string; source_url: string | null; event: string; verified: boolean; basis: string; excerpt: string | null };
type Timeline = { releases: { label: string; release_date: string | null; events: TimelineEvent[] }[]; unplaced: TimelineEvent[] };

const sel = "w-full rounded-md border border-zinc-300 bg-transparent p-2 dark:border-zinc-700";

export function CompareView({ products }: { products: Product[] }) {
  const [product, setProduct] = useState(products[0]?.slug ?? "");
  const [releases, setReleases] = useState<string[]>([]);
  const [earlier, setEarlier] = useState("");
  const [later, setLater] = useState("");
  const [topic, setTopic] = useState("");
  const [res, setRes] = useState<Result | null>(null);
  const [timeline, setTimeline] = useState<Timeline | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showUnchanged, setShowUnchanged] = useState(false);

  useEffect(() => {
    if (!product) return;
    fetch(`${PUBLIC_API}/api/products/${product}`).then(r => r.json()).then((p: ProductDetail) => {
      const l = p.releases.map(r => r.label);
      setReleases(l); setEarlier(l[0] ?? ""); setLater(l[l.length - 1] ?? "");
    }).catch(() => setReleases([]));
    fetch(`${PUBLIC_API}/api/products/${product}/timeline`).then(r => r.json()).then(setTimeline).catch(() => setTimeline(null));
  }, [product]);

  async function run() {
    setError(null); setRes(null);
    const q = new URLSearchParams({ product, earlier, later, ...(topic ? { topic } : {}) });
    const r = await fetch(`${PUBLIC_API}/api/compare?${q}`);
    const body = await r.json();
    if (!r.ok) { setError(body.detail ?? r.statusText); return; }
    setRes(body);
  }

  const shown = res?.changes.filter(c => showUnchanged || c.classification !== "unchanged") ?? [];
  return (
    <div className="space-y-6">
      <section className="card grid items-end gap-3 text-sm md:grid-cols-5">
        <label><div className="muted mb-1">Product</div><select className={sel} value={product} onChange={e => setProduct(e.target.value)}>{products.map(p => <option key={p.slug} value={p.slug}>{p.name}</option>)}</select></label>
        <label><div className="muted mb-1">Earlier release</div><select className={sel} value={earlier} onChange={e => setEarlier(e.target.value)}>{releases.map(l => <option key={l}>{l}</option>)}</select></label>
        <label><div className="muted mb-1">Later release</div><select className={sel} value={later} onChange={e => setLater(e.target.value)}>{releases.map(l => <option key={l}>{l}</option>)}</select></label>
        <label><div className="muted mb-1">Topic (optional)</div><input className={sel} value={topic} onChange={e => setTopic(e.target.value)} placeholder="e.g. scheduled jobs" /></label>
        <button onClick={run} disabled={!earlier || !later} className="rounded-md bg-zinc-900 px-4 py-2 font-medium text-white disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900">Compare</button>
      </section>
      {error && <div className="card border-rose-300 text-sm">{error}</div>}
      {res && (
        <section className="space-y-3">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="font-medium">{res.earlier} → {res.later}</span>
            {Object.entries(res.summary).map(([k, v]) => <Badge key={k} value={`${v} ${k}`} />)}
            <span className="muted">{res.verified_changes} verified change(s)</span>
            <label className="muted ml-auto flex items-center gap-1 text-xs"><input type="checkbox" checked={showUnchanged} onChange={e => setShowUnchanged(e.target.checked)} /> show unchanged</label>
          </div>
          {shown.map(c => (
            <article key={c.document_id} className="card">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div><div className="font-medium">{c.title}</div><div className="muted text-xs">{c.applies_from ?? "?"} → {c.applies_to ?? (c.provenance === "unknown" ? "?" : "open")} · basis: {c.basis.replace(/_/g, " ")}{c.release ? ` · at ${c.release}` : ""}{c.source_url && <> · <a className="underline" href={c.source_url} target="_blank" rel="noreferrer">source</a></>}</div></div>
                <div className="flex gap-1"><Badge value={c.classification} /><Badge value={c.verified ? "verified" : "not verified"} /></div>
              </div>
              {c.evidence_excerpt && <blockquote className="mt-2 border-l-2 border-zinc-300 pl-3 text-sm dark:border-zinc-700">{c.evidence_excerpt}</blockquote>}
              {c.paired_with && (
                <div className="mt-3 grid gap-3 md:grid-cols-2">
                  <div><div className="muted mb-1 text-xs">{res.earlier}: {c.title} — states {c.differing_values?.[0].join(", ") || "—"}</div><pre className="whitespace-pre-wrap rounded-md bg-rose-50 p-2 font-mono text-xs dark:bg-rose-950">{c.diff.filter(l => l.startsWith("-")).join("\n")}</pre></div>
                  <div><div className="muted mb-1 text-xs">{res.later}: {c.paired_with.title} — states {c.differing_values?.[1].join(", ") || "—"}</div><pre className="whitespace-pre-wrap rounded-md bg-emerald-50 p-2 font-mono text-xs dark:bg-emerald-950">{c.diff.filter(l => l.startsWith("+")).join("\n")}</pre></div>
                </div>
              )}
              {c.note && <p className="muted mt-2 text-xs">{c.note}</p>}
            </article>
          ))}
        </section>
      )}
      {timeline && (
        <section className="card">
          <h2 className="mb-4 font-medium">Release timeline</h2>
          <ol className="relative ml-2 space-y-5 border-l border-zinc-300 pl-6 dark:border-zinc-700">
            {timeline.releases.map(r => (
              <li key={r.label} className="relative">
                <span className="absolute -left-[31px] top-1 h-2.5 w-2.5 rounded-full bg-zinc-900 dark:bg-zinc-100" />
                <div className="font-medium">{r.label} <span className="muted text-xs font-normal">{r.release_date ?? "date unknown"}</span></div>
                {r.events.length === 0 ? <div className="muted text-xs">No documented changes.</div> : (
                  <ul className="mt-1 space-y-1 text-sm">{r.events.map((e, i) => (
                    <li key={i} className="flex flex-wrap items-center gap-2"><Badge value={e.event} />{!e.verified && <Badge value="not verified" />}<span>{e.title}</span></li>
                  ))}</ul>
                )}
              </li>
            ))}
          </ol>
          {timeline.unplaced.length > 0 && <p className="muted mt-4 text-xs">Not placed on the timeline (applicability unknown): {timeline.unplaced.map(u => u.title).join(" · ")}</p>}
        </section>
      )}
    </div>
  );
}
