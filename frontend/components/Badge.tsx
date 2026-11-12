import clsx from "clsx";
const styles: Record<string, string> = {
  applies: "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  not_applicable: "border-rose-300 bg-rose-50 text-rose-800 dark:border-rose-800 dark:bg-rose-950 dark:text-rose-300",
  unknown: "border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-300",
  inferred_applies: "border-sky-300 bg-sky-50 text-sky-800 dark:border-sky-800 dark:bg-sky-950 dark:text-sky-300",
  inferred_not_applicable: "border-sky-300 bg-sky-50 text-sky-800 dark:border-sky-800 dark:bg-sky-950 dark:text-sky-300",
  verified: "border-emerald-300 text-emerald-800 dark:border-emerald-800 dark:text-emerald-300",
  inferred: "border-sky-300 text-sky-800 dark:border-sky-800 dark:text-sky-300",
  abstained: "border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-300",
  cited: "border-zinc-900 bg-zinc-900 text-white dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-900",
  introduced: "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  modified: "border-sky-300 bg-sky-50 text-sky-800 dark:border-sky-800 dark:bg-sky-950 dark:text-sky-300",
  deprecated: "border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-300",
  removed: "border-rose-300 bg-rose-50 text-rose-800 dark:border-rose-800 dark:bg-rose-950 dark:text-rose-300",
  completed: "border-emerald-300 text-emerald-800 dark:border-emerald-800 dark:text-emerald-300",
  failed: "border-rose-300 text-rose-800 dark:border-rose-800 dark:text-rose-300",
};
export function Badge({ value, className }: { value: string; className?: string }) {
  return <span className={clsx("badge", styles[value] ?? "border-zinc-300 text-zinc-700 dark:border-zinc-700 dark:text-zinc-300", className)}>{value.replace(/_/g, " ")}</span>;
}
