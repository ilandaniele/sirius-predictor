import { flagUrl } from "@/lib/flags";

export function Flag({ teamId, teamName }: { teamId: string; teamName?: string }) {
  const url = flagUrl(teamId);
  if (!url) return <span className="flag flag-fallback">{teamId}</span>;
  return <img className="flag flag-img" src={url} alt={teamName ?? teamId} loading="lazy" />;
}
