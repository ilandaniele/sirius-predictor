import type { ReactNode } from "react";

import type { Provenance } from "@/lib/types";

import { SourceBadge } from "./SourceBadge";

export function MetricCard({ label, value, detail, source }: { label: string; value: ReactNode; detail?: string; source?: Provenance }) {
  return (
    <article className="metric-card">
      <span>{label}</span>
      <strong>{value}</strong>
      {detail ? <small>{detail}</small> : null}
      {source ? <SourceBadge source={source} /> : null}
    </article>
  );
}
