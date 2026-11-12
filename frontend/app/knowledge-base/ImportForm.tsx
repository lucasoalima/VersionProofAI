"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { PUBLIC_API, type Job } from "@/lib/api";

export function ImportForm() {
  const [path, setPath] = useState("synthetic");
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const router = useRouter();
  async function run() {
    setBusy(true); setError(null); setJob(null);
    try {
      const r = await fetch(`${PUBLIC_API}/api/ingestion/local`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ path }) });
      const body = await r.json();
      if (!r.ok) throw new Error(body.detail ?? r.statusText);
      setJob(body as Job); router.refresh();
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  return (
    <section className="card space-y-3">
      <h2 className="font-medium">Import local documentation</h2>
      <p className="muted text-sm">Paths are relative to <code>INGESTION_ROOT</code>; traversal and absolute paths are rejected server-side. Unchanged documents are deduplicated; changed ones get a new revision.</p>
      <div className="flex gap-2">
        <input className="flex-1 rounded-md border border-zinc-300 bg-transparent p-2 font-mono text-sm dark:border-zinc-700" value={path} onChange={e => setPath(e.target.value)} />
        <button onClick={run} disabled={busy} className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900">{busy ? "Ingesting…" : "Ingest"}</button>
      </div>
      {error && <div className="text-sm text-rose-700">{error}</div>}
      {job && <pre className="rounded-md bg-zinc-50 p-3 font-mono text-xs dark:bg-zinc-950">{JSON.stringify({ status: job.status, ...job.stats }, null, 2)}</pre>}
    </section>
  );
}
