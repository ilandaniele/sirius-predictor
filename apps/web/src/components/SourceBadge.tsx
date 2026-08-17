import type { Provenance } from "@/lib/types";

export function SourceBadge({ source }: { source: Provenance }) {
  const label = `${source.quality} · ${source.name}`;
  if (source.url?.startsWith("http")) {
    return (
      <a className={`source quality-${source.quality}`} href={source.url} target="_blank" rel="noreferrer">
        {label} ↗
      </a>
    );
  }
  return (
    <button className={`source quality-${source.quality}`} title={`Consultado: ${source.consulted_at}`}>
      {label}
    </button>
  );
}
