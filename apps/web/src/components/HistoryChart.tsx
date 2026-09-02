import type { HistoryPoint } from "@/lib/types";

const colors: Record<string, string> = { ARG: "#65c5e8", ESP: "#d7ad53", FRA: "#f2efe7", BRA: "#66d3a0" };

export function HistoryChart({ points }: { points: HistoryPoint[] }) {
  const primary = points.filter((point) => point.mode === "SIRIUS_ONLY");
  const snapshots = [...new Set(primary.map((point) => point.snapshot_id))];
  const teams = [...new Set(primary.map((point) => point.team_id))];
  if (snapshots.length < 2) return <p className="empty">Se necesitan dos snapshots para dibujar evolución.</p>;
  const width = 900;
  const height = 250;
  const maximum = Math.max(1, ...primary.map((point) => point.champion_probability));
  return (
    <div className="history-chart">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Evolución histórica de probabilidad de campeón">
        {[0, 0.5, 1].map((fraction) => <line key={fraction} x1="40" x2="880" y1={20 + 200 * fraction} y2={20 + 200 * fraction} stroke="#243849" />)}
        {teams.map((team) => {
          const teamPoints = snapshots.map((snapshot, index) => {
            const point = primary.find((item) => item.snapshot_id === snapshot && item.team_id === team);
            const x = 40 + (index * 840) / (snapshots.length - 1);
            const y = 220 - ((point?.champion_probability ?? 0) / maximum) * 200;
            return `${x},${y}`;
          });
          return <polyline key={team} points={teamPoints.join(" ")} fill="none" stroke={colors[team] ?? "#93a4af"} strokeWidth="4" />;
        })}
      </svg>
      <div className="legend">{teams.map((team) => <span key={team}><i style={{ background: colors[team] }} />{team}</span>)}</div>
    </div>
  );
}
