import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = { title: "VersionProof AI", description: "Version-aware technical documentation retrieval" };

const nav = [
  ["/", "Dashboard"],
  ["/ask", "Ask Documentation"],
  ["/knowledge-base", "Knowledge Base"],
  ["/compare", "Version Comparison"],
  ["/evaluation", "Evaluation Lab"],
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="flex min-h-screen">
          <aside className="w-56 shrink-0 border-r border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
            <div className="mb-6">
              <div className="text-base font-semibold tracking-tight">VersionProof AI</div>
              <div className="muted">relevant ≠ still valid</div>
            </div>
            <nav className="flex flex-col gap-1 text-sm">
              {nav.map(([href, label]) => (
                <Link key={href} href={href} className="rounded-md px-2 py-1.5 hover:bg-zinc-100 dark:hover:bg-zinc-800">{label}</Link>
              ))}
            </nav>
            <div className="muted mt-8 text-xs">Phase 4 · version intelligence</div>
          </aside>
          <main className="flex-1 p-8">{children}</main>
        </div>
      </body>
    </html>
  );
}
