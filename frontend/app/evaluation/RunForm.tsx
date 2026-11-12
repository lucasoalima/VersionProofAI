"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { PUBLIC_API, type Dataset } from "@/lib/api";

export function RunForm({ datasets }: { datasets: Dataset[] }) {
  const [dataset, setDataset] = useState(datasets[0]?.id ?? "");
  const [mode, setMode] = useState("lexical");
  const [enforce, setEnforce] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  async function run() {
    setBusy(true); setError(null);
    try {
      const r = await fetch(`${PUBLIC_API}/api/evaluation/retrieval-runs`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ dataset_id: dataset, mode, enforce_version: enforce, top_k: 5 }) });
      if (!r.ok) throw new Error((await r.json()).detail ?? r.statusText);
      router.refresh();
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  return (
    <section className="card flex flex-wrap items-end gap-3 text-sm">
      <label><div className="muted mb-1">Dataset</div>
        <select className="rounded-md border border-zinc-300 bg-transparent p-2 dark:border-zinc-700" value={dataset} onChange={e => setDataset(e.target.value)}>
          {datasets.map(d => <option key={d.id} value={d.id}>{d.name} v{d.version} ({d.records} q{d.is_synthetic ? ", synthetic" : ""})</option>)}
        </select></label>
      <label><div className="muted mb-1">Retrieval</div>
        <select className="rounded-md border border-zinc-300 bg-transparent p-2 dark:border-zinc-700" value={mode} onChange={e => setMode(e.target.value)}>
          <option value="lexical">lexical</option><option value="semantic">semantic</option><option value="hybrid">hybrid</option>
        </select></label>
      <label className="flex items-center gap-2 pb-2"><input type="checkbox" checked={enforce} onChange={e => setEnforce(e.target.checked)} /> version constraint</label>
      <button onClick={run} disabled={busy || !dataset} className="rounded-md bg-zinc-900 px-4 py-2 font-medium text-white disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900">{busy ? "Running…" : "Run benchmark"}</button>
      {error && <span className="text-rose-700">{error}</span>}
    </section>
  );
}
