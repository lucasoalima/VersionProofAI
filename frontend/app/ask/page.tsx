import { getProducts } from "@/lib/api";
import { AskForm } from "./AskForm";

export const dynamic = "force-dynamic";

export default async function AskPage() {
  const products = (await getProducts()) ?? [];
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Ask Documentation</h1>
        <p className="muted">Retrieve evidence for a target version. Version restrictions are applied as applicability constraints, not ranking bonuses.</p>
      </header>
      <AskForm products={products} />
    </div>
  );
}
