import { getProducts } from "@/lib/api";
import { CompareView } from "./CompareView";

export const dynamic = "force-dynamic";

export default async function ComparePage() {
  const products = (await getProducts()) ?? [];
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Version Comparison</h1>
        <p className="muted">Deterministic comparison of stored documentation between two releases. No language model is involved; a change is marked verified only when the sources support it.</p>
      </header>
      <CompareView products={products} />
    </div>
  );
}
