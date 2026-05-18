"use client";

import { Calendar } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { WEEK_KEYS, WEEK_LABELS, parseWeek, type WeekKey } from "@/lib/week";

export function WeekSelector() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const current = parseWeek(params.get("week"));

  function setWeek(next: WeekKey) {
    const sp = new URLSearchParams(params.toString());
    if (next === "current") {
      sp.delete("week");
    } else {
      sp.set("week", next);
    }
    const qs = sp.toString();
    router.push(qs ? `${pathname}?${qs}` : pathname);
  }

  return (
    <div className="inline-flex w-full items-center gap-1 rounded-md border border-border bg-surface p-0.5 sm:w-auto">
      <Calendar className="ml-1.5 hidden h-3.5 w-3.5 text-fg-subtle sm:block" />
      {WEEK_KEYS.map((k) => {
        const active = current === k;
        return (
          <button
            key={k}
            type="button"
            onClick={() => setWeek(k)}
            className={`flex-1 rounded px-2 py-1 text-xs font-medium transition sm:flex-none ${
              active
                ? "bg-fg text-bg"
                : "text-fg-muted hover:bg-surface-hover hover:text-fg"
            }`}
          >
            {WEEK_LABELS[k]}
          </button>
        );
      })}
    </div>
  );
}
