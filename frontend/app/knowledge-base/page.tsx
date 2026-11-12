import { getDocuments, getProducts } from "@/lib/api";
import { Badge } from "@/components/Badge";
import { ImportForm } from "./ImportForm";

export const dynamic = "force-dynamic";

export default async function KnowledgeBasePage() {
  const [products, docs] = await Promise.all([getProducts(), getDocuments()]);
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Knowledge Base</h1>
        <p className="muted">Import local documentation and inspect version metadata, provenance and chunks.</p>
      </header>
      <ImportForm />
      <section className="card">
        <h2 className="mb-3 font-medium">Indexed documents ({docs?.length ?? 0})</h2>
        {!docs || docs.length === 0 ? <p className="muted">Nothing indexed. Import <code>synthetic</code> to load the fictional Nimbus CRM corpus.</p> : (
          <table className="w-full text-sm">
            <thead className="muted text-left"><tr><th className="py-1">Title</th><th>Product</th><th>Applies</th><th>Provenance</th><th>Rev</th><th>Chunks</th></tr></thead>
            <tbody>{docs.map(d => {
              const r = d.current_revision;
              return (
                <tr key={d.id} className="border-t border-zinc-100 align-top dark:border-zinc-800">
                  <td className="py-1.5"><a className="underline" href={`/knowledge-base/${d.id}`}>{d.title}</a><div className="muted font-mono text-xs">{d.external_id}</div></td>
                  <td>{products?.find(p => p.slug === d.product_slug)?.name ?? d.product_slug}</td>
                  <td className="whitespace-nowrap">{r ? `${r.effective_from ?? "?"} → ${r.effective_to ?? (r.applicability_provenance === "unknown" ? "?" : "open")}` : "—"}</td>
                  <td>{r && <Badge value={r.applicability_provenance} />}</td>
                  <td>{r?.revision_number ?? "—"}</td><td>{r?.chunk_count ?? "—"}</td>
                </tr>);
            })}</tbody>
          </table>
        )}
      </section>
    </div>
  );
}
