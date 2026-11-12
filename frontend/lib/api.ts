// Server components call the backend through API_INTERNAL_URL (docker network);
// client components use NEXT_PUBLIC_API_URL (browser-reachable).
export const PUBLIC_API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const INTERNAL_API = process.env.API_INTERNAL_URL ?? PUBLIC_API;

export type Product = { id: string; slug: string; name: string; version_scheme: string; is_synthetic: boolean; release_count: number; document_count: number };
export type Release = { id: string; label: string; sequence: number; release_date: string | null; release_date_provenance: string };
export type ProductDetail = Product & { releases: Release[] };
export type Job = { id: string; source_path: string; status: string; started_at: string; finished_at: string | null; stats: Record<string, unknown>; error: string | null };
export type Dashboard = {
  products: Product[]; document_count: number; revision_count: number; chunk_count: number; embedded_chunk_count: number;
  recent_jobs: Job[]; evaluation_runs: { id: string; strategy: string; model_identifier: string | null; started_at: string; metrics: Record<string, number> }[];
  capabilities: Record<string, boolean | string>;
};
export type Revision = { id: string; revision_number: number; checksum: string; published_at: string | null; last_updated_at: string | null; effective_from: string | null; effective_to: string | null; applicability_provenance: string; metadata_provenance: Record<string, string>; technical_tokens: string[]; chunk_count: number; ingested_at: string };
export type Doc = { id: string; product_slug: string; source_name: string; trust_level: string; external_id: string; title: string; source_url: string | null; category: string | null; current_revision: Revision | null };
export type Evidence = { chunk_id: string; document_id: string; revision_id: string; title: string; source_url: string | null; heading: string | null; excerpt: string; score: number; rank: number; effective_from: string | null; effective_to: string | null; applicability_status: string; applicability_provenance: string; published_at: string | null; trust_level: string; strategy: string; diagnostics: Record<string, unknown> };
export type SearchResponse = { query: string; product: string; target_version: string | null; mode: string; enforce_version: boolean; results: Evidence[]; excluded: Evidence[]; retrieval_latency_ms: number; notices: string[] };

async function serverGet<T>(path: string): Promise<T | null> {
  try {
    const r = await fetch(`${INTERNAL_API}${path}`, { cache: "no-store" });
    if (!r.ok) return null;
    return (await r.json()) as T;
  } catch {
    return null;
  }
}
export const getDashboard = () => serverGet<Dashboard>("/api/dashboard");
export const getProducts = () => serverGet<Product[]>("/api/products");
export const getProduct = (slug: string) => serverGet<ProductDetail>(`/api/products/${slug}`);
export const getDocuments = (slug?: string) => serverGet<Doc[]>(`/api/documents${slug ? `?product=${slug}` : ""}`);

export type Dataset = { id: string; name: string; version: string; split: string; is_synthetic: boolean; records: number; description: string | null };
export type EvalRun = { id: string; dataset_id: string; strategy: string; config: Record<string, unknown>; model_identifier: string | null; started_at: string; finished_at: string | null; metrics: Record<string, number | null>; per_question: Record<string, unknown>[] };
export const getDatasets = () => serverGet<Dataset[]>("/api/evaluation/datasets");
export const getRuns = () => serverGet<EvalRun[]>("/api/evaluation/runs");
