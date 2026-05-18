import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";

/* ──────────────────────────────────────────────────────────────────────────
 * Shared design-system primitives. One canonical look across every page.
 * ──────────────────────────────────────────────────────────────────────── */

export function Card({
  children,
  className = "",
  as: As = "div",
  ...rest
}: { children: ReactNode; className?: string; as?: "div" | "section" } & ComponentProps<"div">) {
  return (
    <As
      className={`rounded-xl border border-border bg-surface ${className}`}
      {...rest}
    >
      {children}
    </As>
  );
}

export function PageHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <header className="space-y-1">
      <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{title}</h1>
      {subtitle && <p className="text-sm text-fg-muted sm:text-base">{subtitle}</p>}
    </header>
  );
}

export function Stat({
  label,
  value,
  hint,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
}) {
  return (
    <Card className="p-4">
      <div className="text-xs font-medium uppercase tracking-wide text-fg-subtle">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
      {hint && <div className="mt-0.5 text-xs text-fg-subtle">{hint}</div>}
    </Card>
  );
}

type BadgeTone = "neutral" | "positive" | "negative" | "warning" | "accent";

const badgeTones: Record<BadgeTone, string> = {
  neutral:
    "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
  positive:
    "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300",
  negative:
    "bg-rose-50 text-rose-700 dark:bg-rose-950/60 dark:text-rose-300",
  warning:
    "bg-amber-50 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300",
  accent:
    "bg-sky-50 text-sky-700 dark:bg-sky-950/60 dark:text-sky-300",
};

export function Badge({
  children,
  tone = "neutral",
  className = "",
  title,
}: {
  children: ReactNode;
  tone?: BadgeTone;
  className?: string;
  /** Native tooltip text shown on hover. */
  title?: string;
}) {
  return (
    <span
      title={title}
      className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-xs font-medium tabular-nums ${badgeTones[tone]} ${className}`}
    >
      {children}
    </span>
  );
}

import { AlertTriangle } from "lucide-react";
import { discountTrust, offerLink } from "@/lib/offerSanity";

export function PriceTag({
  price,
  original,
  discount,
  title,
  size = "md",
}: {
  price: number | null | undefined;
  original?: number | null;
  discount?: number | null;
  /** Offer title — used to detect pack/multi-unit hints that invalidate the % */
  title?: string | null;
  size?: "sm" | "md";
}) {
  const main = size === "sm" ? "text-sm font-semibold" : "text-base font-semibold";
  const trust = discountTrust(title, discount);

  return (
    <div className="flex items-baseline gap-2 tabular-nums">
      <span className={main}>{price != null ? `${price.toFixed(2)} €` : "—"}</span>
      {original != null && original !== price && trust !== "implausible" && (
        <span className="text-xs text-fg-subtle line-through">
          {original.toFixed(2)} €
        </span>
      )}
      {discount != null && discount > 0 && trust === "trusted" && (
        <Badge tone="negative">−{discount.toFixed(0)}%</Badge>
      )}
      {discount != null && discount > 0 && trust === "suspect" && (
        <Badge
          tone="warning"
          className="gap-1"
          title="Rabatt wahrscheinlich durch Mehrfachpackung verzerrt"
        >
          <AlertTriangle className="h-3 w-3" />
          −{discount.toFixed(0)}%
        </Badge>
      )}
      {/* "implausible" → discount badge hidden entirely; original price also hidden above. */}
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  body,
}: {
  icon?: ReactNode;
  title: string;
  body?: ReactNode;
}) {
  return (
    <Card className="flex flex-col items-center gap-3 p-10 text-center">
      {icon && <div className="text-fg-subtle">{icon}</div>}
      <div className="text-sm font-medium text-fg">{title}</div>
      {body && <div className="max-w-sm text-sm text-fg-muted">{body}</div>}
    </Card>
  );
}

export function Thumbnail({
  src,
  alt = "",
  size = 40,
}: {
  src?: string | null;
  alt?: string;
  size?: number;
}) {
  const cls = "flex-shrink-0 rounded-md object-cover";
  const px = `${size}px`;
  if (!src) {
    return (
      <div
        className={`${cls} bg-zinc-100 dark:bg-zinc-800`}
        style={{ width: px, height: px }}
      />
    );
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={src} alt={alt} className={cls} style={{ width: px, height: px }} />
  );
}

export function OfferRow({
  title,
  store,
  url,
  imageUrl,
  price,
  originalPrice,
  discountPercent,
  href,
  meta,
  trailing,
}: {
  title: string;
  store: string | null;
  url?: string;
  imageUrl?: string | null;
  price: number | null;
  originalPrice?: number | null;
  discountPercent?: number | null;
  href?: string;
  meta?: ReactNode;
  trailing?: ReactNode;
}) {
  // Always link out somewhere: the brochure URL if we have one, otherwise a
  // kaufDA search URL built from the title. Avoids 404s when links rot.
  const outboundUrl = offerLink(url, title);
  const titleEl = (
    <a
      href={outboundUrl}
      target="_blank"
      rel="noopener"
      className="block truncate text-sm font-medium hover:underline"
    >
      {title}
    </a>
  );

  // On mobile the price wraps under the title; on sm+ it sits to the right.
  const body = (
    <>
      <Thumbnail src={imageUrl} />
      <div className="min-w-0 flex-1">
        {titleEl}
        <div className="mt-0.5 truncate text-xs text-fg-muted">
          {store ?? "—"}
          {meta ? <> · {meta}</> : null}
        </div>
        <div className="mt-1 sm:hidden">
          <PriceTag price={price} original={originalPrice} discount={discountPercent} title={title} size="sm" />
        </div>
      </div>
      <div className="hidden sm:block">
        <PriceTag price={price} original={originalPrice} discount={discountPercent} title={title} size="sm" />
      </div>
      {trailing}
    </>
  );

  const cls = "flex items-center gap-3 px-3 py-3 transition-colors hover:bg-surface-hover sm:px-4";

  if (href) {
    return (
      <Link href={href} className={cls}>
        {body}
      </Link>
    );
  }
  return <div className={cls}>{body}</div>;
}
