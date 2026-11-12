import { getDatasets, getRuns } from "@/lib/api";
import { RunForm } from "./RunForm";

export const dynamic = "force-dynamic";
const cols: [string, string][] = [["recall_at_k", "Recall@k"], ["mrr", "MRR"], ["ndcg_at_k", "nDCG@k"], ["outdated_surfaced_rate", "Outdated surfaced"], ["applicability_accuracy", "Applicability acc."], ["retrieval_latency_ms_p50", "p50 ms"], ["correct_abstention_rate", "Abstention ok"], ["outdated_recommendation_rate", "Outdated cited"], ["citation_validity_rate", "Citation valid"]];

export default async function EvaluationPage() {
  const [datasets, runs] = await Promise.all([getDatasets(), getRuns()]);
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Evaluation Lab</h1>
        <p className="muted">Retrieval and answer benchmarks. Every row is a stored run with its configuration; nothing here is illustrative.</p>
      </header>
      <RunForm datasets={datasets ?? []} />
      <section className="card overflow-x-auto">
        <h2 className="mb-3 font-medium">Recorded runs ({runs?.length ?? 0})</h2>
        {!runs || runs.length === 0 ? <p className="muted">No runs yet. Register a dataset (<code>python scripts/seed.py</code>) and execute a benchmark above.</p> : (
          <table className="w-full text-sm">
            <thead className="muted text-left"><tr><th className="py-1">Strategy</th><th>Model</th>{cols.map(([k, l]) => <th key={k} className="text-right">{l}</th>)}<th>When</th><th></th></tr></thead>
            <tbody>{runs.map(r => (
              <tr key={r.id} className="border-t border-zinc-100 dark:border-zinc-800">
                <td className="py-1.5 font-mono text-xs">{r.strategy}<div className="muted">{String(r.config.dataset)} · k={String(r.config.top_k)}</div></td>
                <td className="font-mono text-xs">{r.model_identifier ?? "—"}</td>
                {cols.map(([k]) => <td key={k} className="text-right tabular-nums">{r.metrics[k] ?? "—"}</td>)}
                <td className="muted whitespace-nowrap text-xs">{new Date(r.started_at).toISOString().slice(0, 16).replace("T", " ")}</td>
                <td className="whitespace-nowrap text-xs"><a className="underline" href={`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/evaluation/runs/${r.id}`} target="_blank" rel="noreferrer">JSON</a> · <a className="underline" href={`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/evaluation/runs/${r.id}/export.csv`}>CSV</a></td>
              </tr>))}</tbody>
          </table>
        )}
      </section>
      <section className="card text-sm">
        <h2 className="mb-2 font-medium">Reading the metrics</h2>
        <ul className="muted list-disc space-y-1 pl-5">
          <li><b>Outdated surfaced</b> — share of questions (with a known outdated source) where that source reached the top-k. Lower is better; the version constraint should drive it to 0.</li>
          <li><b>Applicability accuracy</b> — top result's status matches the dataset's expectation; for "not applicable" cases, finding the source in the excluded list counts.</li>
          <li><b>Recall/MRR/nDCG</b> are computed only over questions with supporting documents; abstention cases are excluded from them and scored separately in Phase 3.</li>
          <li>Runs with model <code>hashed-bow-v1</code> use a deterministic bag-of-words embedding for offline tests — not a semantic model.</li>
        </ul>
      </section>
    </div>
  );
}
