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
    <span
      className={`source quality-${source.quality} static`}
      title={`Fuente interna del proyecto, sin URL pública · Consultado: ${source.consulted_at}`}
    >
      {label}
    </span>
  );
}
