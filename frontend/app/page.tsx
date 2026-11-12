import { getDashboard } from "@/lib/api";
import { Badge } from "@/components/Badge";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const d = await getDashboard();
  if (!d) {
    return (
      <div className="card border-rose-300">
        <h1 className="text-lg font-semibold">Backend unreachable</h1>
        <p className="muted mt-1">The dashboard shows only measured values from the API. Start the backend (see README) and reload.</p>
      </div>
    );
  }
  const caps = d.capabilities;
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        <p className="muted">Every number below is read live from the backend.</p>
      </header>
      <section className="grid grid-cols-2 gap-4 md:grid-cols-5">
        {[["Products", d.products.length], ["Documents", d.document_count], ["Revisions", d.revision_count], ["Chunks", d.chunk_count], ["Embedded chunks", d.embedded_chunk_count]].map(([k, v]) => (
          <div className="card" key={String(k)}><div className="muted">{k}</div><div className="kpi">{v}</div></div>
        ))}
      </section>
      <section className="grid gap-4 md:grid-cols-2">
        <div className="card">
          <h2 className="mb-3 font-medium">Indexed products</h2>
          {d.products.length === 0 ? <p className="muted">Nothing indexed yet. Import documentation from the Knowledge Base page.</p> : (
            <table className="w-full text-sm">
              <thead className="muted text-left"><tr><th className="py-1">Product</th><th>Scheme</th><th>Releases</th><th>Docs</th></tr></thead>
              <tbody>{d.products.map(p => (
                <tr key={p.id} className="border-t border-zinc-100 dark:border-zinc-800">
                  <td className="py-1.5">{p.name} {p.is_synthetic && <Badge value="synthetic" className="ml-1" />}</td>
                  <td className="font-mono text-xs">{p.version_scheme}</td><td>{p.release_count}</td><td>{p.document_count}</td>
                </tr>))}</tbody>
            </table>
          )}
        </div>
        <div className="card">
          <h2 className="mb-3 font-medium">Capabilities</h2>
          <ul className="space-y-1 text-sm">
            {Object.entries(caps).filter(([, v]) => typeof v === "boolean").map(([k, v]) => (
              <li key={k} className="flex justify-between"><span>{k.replace(/_/g, " ")}</span><Badge value={v ? "enabled" : "not configured"} /></li>
            ))}
          </ul>
          <p className="muted mt-3 text-xs">Semantic/hybrid retrieval and answer generation require EMBEDDING_PROVIDER / LLM_PROVIDER. Phase 1 runs entirely without them.</p>
        </div>
        <div className="card">
          <h2 className="mb-3 font-medium">Recent ingestion jobs</h2>
          {d.recent_jobs.length === 0 ? <p className="muted">No jobs yet.</p> : (
            <ul className="space-y-2 text-sm">{d.recent_jobs.map(j => (
              <li key={j.id} className="flex items-start justify-between gap-3 border-t border-zinc-100 pt-2 first:border-0 first:pt-0 dark:border-zinc-800">
                <div><div className="font-mono text-xs">{j.source_path.split("/").slice(-2).join("/")}</div>
                  <div className="muted text-xs">{JSON.stringify({ seen: j.stats.documents_seen, revisions: j.stats.revisions_created, unchanged: j.stats.unchanged, failures: (j.stats.failures as unknown[] | undefined)?.length ?? 0 })}</div></div>
                <Badge value={j.status} />
              </li>))}</ul>
          )}
        </div>
        <div className="card">
          <h2 className="mb-3 font-medium">Evaluation runs</h2>
          {d.evaluation_runs.length === 0 ? <p className="muted">No benchmark has been executed. The Evaluation Lab arrives in Phase 5; no numbers are shown until a run is recorded.</p> : (
            <ul className="text-sm">{d.evaluation_runs.map(r => <li key={r.id}>{r.strategy} · {r.model_identifier ?? "no LLM"} · {JSON.stringify(r.metrics)}</li>)}</ul>
          )}
        </div>
      </section>
    </div>
  );
}
