"use client";

import { useEffect, useMemo, useState } from "react";

import { MetricCard } from "@/components/MetricCard";
import { SourceBadge } from "@/components/SourceBadge";
import { HistoryChart } from "@/components/HistoryChart";
import { api } from "@/lib/api";
import type {
  BacktestResult,
  Draw,
  HistoryPoint,
  Prediction,
  Provenance,
  Scenario,
  SourceRecord,
  Team,
  UpdateEvent
} from "@/lib/types";

const tabs = [
  "Dashboard",
  "Argentina",
  "64 selecciones",
  "Sorteo",
  "Simulaciones",
  "Sirius",
  "Fuentes",
  "Backtesting",
  "Historial",
  "Configuración"
] as const;

export default function Home() {
  const [active, setActive] = useState<(typeof tabs)[number]>("Dashboard");
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [teams, setTeams] = useState<Team[]>([]);
  const [prediction, setPrediction] = useState<Prediction | null>(null);
  const [sources, setSources] = useState<Provenance[]>([]);
  const [sourceCatalog, setSourceCatalog] = useState<SourceRecord[]>([]);
  const [draw, setDraw] = useState<Draw>({});
  const [backtest, setBacktest] = useState<BacktestResult | null>(null);
  const [lastUpdate, setLastUpdate] = useState<UpdateEvent | null>(null);
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [status, setStatus] = useState("Cargando contratos…");

  useEffect(() => {
    Promise.all([
      api.scenario(),
      api.teams(),
      api.latest(),
      api.history(),
      api.draw(),
      api.sources(),
      api.backtest(),
      api.latestUpdate()
    ])
      .then(
        ([scenarioResult, teamResult, latest, historical, drawResult, catalog, tested, update]) => {
        setScenario(scenarioResult.data);
        setTeams(teamResult.data);
        setPrediction(latest.data);
        const provenanceRows = [
          ...scenarioResult.provenance,
          ...teamResult.provenance,
          ...latest.provenance,
          ...tested.provenance,
          ...update.provenance
        ];
        setSources(
          provenanceRows.filter(
            (source, index) =>
              provenanceRows.findIndex(
                (candidate) =>
                  candidate.source_id === source.source_id && candidate.url === source.url
              ) === index
          )
        );
        setHistory(historical.data);
        setDraw(drawResult.data);
        setSourceCatalog(catalog.data);
        setBacktest(tested.data);
        setLastUpdate(update.data);
        const successful = update.data?.sources.filter(
          (source) => source.fetch_status === "success"
        ).length;
        setStatus(
          latest.data
            ? `Snapshot ${latest.data.run_id} · fuentes ${successful ?? "—"}/${update.data?.sources.length ?? "—"}`
            : "Sin predicción ejecutada"
        );
        }
      )
      .catch((error: Error) => setStatus(`API no disponible · ${error.message}`));
  }, []);

  const candidates = useMemo(
    () => [...teams].sort((a, b) => b.projected_elo - a.projected_elo).slice(0, 12),
    [teams]
  );
  const argentinaTeam = teams.find((team) => team.team_id === "ARG");
  const scenarioSource = sources.find((source) => source.source_id === "scenario");
  const modelSource = sources.find((source) => source.source_id !== "scenario") ?? scenarioSource;
  const argentinaGroup = Object.entries(draw).find(([, members]) =>
    members.some((team) => team.team_id === "ARG")
  );

  async function updateWorldCup() {
    setStatus("Encolando actualización…");
    try {
      const job = await api.update();
      setStatus(`${job.detail} · ${job.job_id}`);
    } catch (error) {
      setStatus(`No se pudo actualizar · ${(error as Error).message}`);
    }
  }

  return (
    <main>
      <header className="topbar">
        <div className="brand"><i>✦</i><span>SIRIUS<br /><b>ENGINE</b></span></div>
        <div className="scenario-label">ESCENARIO 2030 · HIPOTÉTICO</div>
        <button className="update" onClick={updateWorldCup}>ACTUALIZAR MUNDIAL 2030</button>
      </header>

      <section className="hero">
        <div>
          <p className="eyebrow">INTELIGENCIA DE TORNEO · v0.1.0</p>
          <h1>Mundial 2030<br /><em>Sirius Engine</em></h1>
          <p className="lede">Baseline futbolístico y modelo Sirius experimental, separados, comparables y trazables.</p>
        </div>
        <div className="status"><span className="pulse" />{status}</div>
      </section>

      <aside className="disclaimer">
        La astrología no tiene validez científica demostrada para predecir fútbol. Sirius se publica como experimento y siempre junto a FOOTBALL_ONLY.
      </aside>

      <nav className="tabs" aria-label="Secciones">
        {tabs.map((tab) => (
          <button key={tab} className={active === tab ? "active" : ""} onClick={() => setActive(tab)}>{tab}</button>
        ))}
      </nav>

      <section className="content">
        <div className="section-heading"><div><p>VISTA ACTUAL</p><h2>{active}</h2></div>{sources[0] ? <SourceBadge source={sources[0]} /> : null}</div>
        <div className="metrics">
          <MetricCard label="Selecciones" value={scenario?.format.teams ?? "—"} detail="4 bombos de 16" source={scenarioSource} />
          <MetricCard label="Grupos" value={scenario?.format.groups ?? "—"} detail="Clasifican 2" source={scenarioSource} />
          <MetricCard label="Final" value={scenario ? `${scenario.final.city}` : "—"} detail={scenario?.final.local_date} source={scenarioSource} />
          <MetricCard label="Simulaciones" value={prediction?.iterations.toLocaleString("es-UY") ?? "Pendiente"} detail={prediction?.mode ?? "3 modelos separados"} source={modelSource} />
        </div>

        {active === "Historial" ? <article className="panel history"><div className="panel-title"><div><p>EVOLUCIÓN APPEND-ONLY</p><h3>Argentina · España · Francia · Brasil</h3></div></div><HistoryChart points={history} /></article> : null}

        {active === "64 selecciones" ? <article className="panel wide"><div className="panel-title"><div><p>CAMPO PROYECTADO</p><h3>64 selecciones · no es clasificación oficial</h3></div>{scenarioSource ? <SourceBadge source={scenarioSource} /> : null}</div><div className="team-grid">{teams.map((team) => <div key={team.team_id}><b>{team.team_id}</b><strong>{team.team}</strong><span>{team.confed} · Bombo {team.pot}</span><small>Elo {team.projected_elo} · calidad Sirius {(team.sirius_confidence * 100).toFixed(0)}%</small></div>)}</div></article> : null}

        {active === "Sorteo" ? <div className="two-columns"><article className="panel"><div className="panel-title"><div><p>SEED 2030</p><h3>Un sorteo legal reproducible</h3></div>{scenarioSource ? <SourceBadge source={scenarioSource} /> : null}</div><div className="groups-grid">{Object.entries(draw).map(([group, members]) => <div key={group}><b>Grupo {group}</b>{members.map((team) => <span key={team.team_id}>{team.team_id} · {team.team}</span>)}</div>)}</div></article><article className="panel"><div className="panel-title"><div><p>ARGENTINA</p><h3>Grupo actual y familias frecuentes</h3></div></div>{argentinaGroup ? <div className="focus-group"><b>Grupo {argentinaGroup[0]}</b>{argentinaGroup[1].map((team) => <span key={team.team_id}>{team.team}</span>)}</div> : null}<DataTable rows={prediction?.argentina_groups ?? []} empty="Ejecutá una actualización para estimar familias." /></article></div> : null}

        {active === "Simulaciones" ? <div className="two-columns"><article className="panel"><div className="panel-title"><div><p>MONTE CARLO</p><h3>Ranking de campeón</h3></div>{modelSource ? <SourceBadge source={modelSource} /> : null}</div><DataTable rows={prediction?.ranking?.slice(0, 20) ?? []} empty="Todavía no hay simulación persistida." /></article><article className="panel"><div className="panel-title"><div><p>DENSIDAD</p><h3>Finales y cinco llaves</h3></div></div><DataTable rows={prediction?.final_pairs?.slice(0, 10) ?? []} empty="Sin finales simuladas." /><div className="bracket-list">{prediction?.top_brackets?.map((bracket, index) => <div key={String(bracket.signature ?? index)}><b>#{index + 1} · {String(bracket.champion ?? "campeón modal")}</b><span>{String(bracket.density_percent ?? "—")}% de densidad</span></div>)}</div></article></div> : null}

        {active === "Argentina" ? <div className="two-columns tab-detail"><article className="panel"><div className="panel-title"><div><p>ETAPAS</p><h3>Probabilidad de avance</h3></div></div><DataTable rows={prediction?.argentina_stages ?? []} empty="Sin snapshot ejecutado." /></article><article className="panel"><div className="panel-title"><div><p>RIVALES</p><h3>Frecuencia condicional por ronda</h3></div></div>{Object.entries(prediction?.argentina_rivals ?? {}).map(([round, rows]) => <div className="round-block" key={round}><b>{round}</b><DataTable rows={rows.slice(0, 5)} empty="Sin encuentros" /></div>)}</article></div> : null}

        {active === "Sirius" ? <div className="two-columns"><article className="panel"><div className="panel-title"><div><p>MODELO EXPERIMENTAL</p><h3>Índices y límites</h3></div></div><div className="sirius-cards"><span><small>Prior Sirius ARG</small><b>{argentinaTeam?.sirius_index.toFixed(2) ?? "—"}</b><em>Hipótesis X, no predicción científica</em></span><span><small>Confianza de datos</small><b>{argentinaTeam ? `${(argentinaTeam.sirius_confidence * 100).toFixed(0)}%` : "—"}</b><em>Separada de la fuerza</em></span><span><small>Índice Recorrido</small><b>Pendiente</b><em>Faltan testimonios verificables</em></span><span><small>Índice Coronación</small><b>Pendiente</b><em>No se imputa</em></span></div></article><article className="panel"><div className="panel-title"><div><p>SENSIBILIDAD</p><h3>Hora de la final y datos desconocidos</h3></div></div><DataTable rows={prediction?.sensitivity ?? []} empty="Se genera con una simulación; 4 horas × 3 offsets." /></article></div> : null}

        {active === "Fuentes" ? <article className="panel wide"><div className="panel-title"><div><p>CATÁLOGO Y GOBERNANZA</p><h3>Fuente · URL · calidad · uso</h3></div></div><div className="source-grid">{sourceCatalog.map((source) => <div key={source.id}><span className={`grade quality-${source.grade}`}>{source.grade}</span><strong>{source.name}</strong><p>{source.use}</p>{source.url?.startsWith("http") ? <a href={source.url} target="_blank" rel="noreferrer">Abrir fuente ↗</a> : <code>{source.url ?? "Adaptador pendiente"}</code>}<small>{source.enabled ? "Habilitada" : "Deshabilitada"} · robots: {source.robots_policy ?? "sin registrar"}</small></div>)}</div></article> : null}

        {active === "Backtesting" ? <article className="panel wide"><div className="panel-title"><div><p>VALIDACIÓN TEMPORAL</p><h3>2010 · 2014 · 2018 · 2022 · 2026</h3></div>{modelSource ? <SourceBadge source={modelSource} /> : null}</div>{backtest ? <><p className="micro">{backtest.matches} partidos · disponibles {backtest.available_editions.join(", ")}{backtest.missing_editions.length ? ` · sin datos: ${backtest.missing_editions.join(", ")}` : ""}</p><DataTable rows={backtest.metrics} empty="Sin métricas." /><h3 className="subheading">Ablaciones</h3><DataTable rows={backtest.ablations} empty="Sin ablaciones." /></> : <p className="empty">Ejecutá scripts/release_acceptance.py; el dashboard no inventa resultados ausentes.</p>}</article> : null}

        {active === "Configuración" ? <div className="two-columns"><article className="panel"><div className="panel-title"><div><p>ESCENARIO</p><h3>Supuestos configurables</h3></div>{scenarioSource ? <SourceBadge source={scenarioSource} /> : null}</div><ul className="config-list"><li>64 equipos · 16 grupos · clasifican 2</li><li>Máximo 2 UEFA y 1 de otras confederaciones</li><li>Argentina y España en sectores opuestos</li><li>Final Madrid · 21/07/2030 · 18:00 base</li><li>Sensibilidad 17/18/20/21 y ±15 minutos</li></ul></article><article className="panel"><div className="panel-title"><div><p>MODELOS</p><h3>Separación obligatoria</h3></div></div>{["FOOTBALL_ONLY", "SIRIUS_ONLY", "HYBRID"].map((model) => <div className="model-row" key={model}><i /><b>{model}</b><span>versionado</span></div>)}</article></div> : null}

        {active === "Dashboard" || active === "Argentina" ? <div className="dashboard-grid">
          <article className="panel ranking">
            <div className="panel-title"><div><p>RANKING DE CANDIDATOS</p><h3>Fuerza futbolística proyectada</h3></div><span>Confianza ≠ fuerza</span></div>
            <div className="ranking-list">
              {candidates.map((team, index) => (
                <div className="rank-row" key={team.team_id}>
                  <b>{String(index + 1).padStart(2, "0")}</b><span className="flag">{team.team_id}</span><strong>{team.team}</strong>
                  <div className="bar"><i style={{ width: `${Math.max(8, (team.projected_elo - 1300) / 7)}%` }} /></div>
                  <code>{team.projected_elo}</code><small>Sirius {team.sirius_index.toFixed(2)} · datos {(team.sirius_confidence * 100).toFixed(0)}%</small>
                </div>
              ))}
              {!candidates.length ? <p className="empty">Esperando API de equipos.</p> : null}
            </div>
          </article>

          <article className="panel argentina">
            <div className="panel-title"><div><p>FOCO ARGENTINA</p><h3>Camino de la selección</h3></div><span className="arg-pill">ARG</span></div>
            <div className="probability"><span>Probabilidad de campeón</span><strong>{String(prediction?.ranking?.find((row) => row.ID === "ARG")?.["Campeón %"] ?? "—")}{prediction ? "%" : ""}</strong></div>
            <div className="sirius-indices">
              <span><small>Fuerza Sirius</small><b>{argentinaTeam?.sirius_index.toFixed(2) ?? "—"}</b></span>
              <span><small>Confianza de datos</small><b>{argentinaTeam ? `${(argentinaTeam.sirius_confidence * 100).toFixed(0)}%` : "—"}</b></span>
              <span><small>Índice recorrido</small><b>Pendiente</b></span>
              <span><small>Índice coronación</small><b>Pendiente</b></span>
            </div>
            <div className="timeline">{["Grupos", "16avos", "Octavos", "Cuartos", "Semi", "Final"].map((round) => <div key={round}><i /><span>{round}</span></div>)}</div>
            <div className="assumptions"><b>Supuesto activo</b><p>Lionel Scaloni continúa como DT. Capitán y datos futuros quedan pendientes; no se imputan.</p></div>
          </article>

          <article className="panel provenance-panel">
            <div className="panel-title"><div><p>TRAZABILIDAD</p><h3>Fuentes de esta vista</h3></div></div>
            {sources.length ? sources.map((source, index) => <SourceBadge source={source} key={`${source.source_id}-${index}`} />) : <p className="empty">Sin provenance cargada.</p>}
            {lastUpdate ? <p className="micro">Última consulta: {new Date(lastUpdate.created_at).toLocaleString("es-UY")} · {lastUpdate.pending_review} pendientes · {lastUpdate.conflicts} conflictos.</p> : null}
            <p className="micro">Cada predicción conserva versión, timestamp, commit, semilla, pesos, supuestos y snapshots de entrada.</p>
          </article>

          <article className="panel model-panel">
            <div className="panel-title"><div><p>COMPARADOR</p><h3>Modelos aislados</h3></div></div>
            {["FOOTBALL_ONLY", "SIRIUS_ONLY", "HYBRID"].map((model, index) => <div className="model-row" key={model}><i className={`model-${index}`} /><b>{model}</b><span>{prediction?.model_comparison?.[model] != null ? `${Number(prediction.model_comparison[model]).toFixed(2)}% ARG` : "sin ejecutar"}</span></div>)}
            {prediction?.changes?.length ? <div className="changes"><b>Cambios detectados</b>{prediction.changes.map((change) => <p key={change}>{change}</p>)}</div> : null}
          </article>
        </div> : null}
      </section>

      <footer><span>Mundial 2030 Sirius Engine</span><span>Madrid · 21/07/2030 · 18:00 base · ±15 min</span></footer>
    </main>
  );
}

function DataTable({ rows, empty }: { rows: Array<Record<string, unknown>>; empty: string }) {
  if (!rows.length) return <p className="empty">{empty}</p>;
  const columns = Object.keys(rows[0]).slice(0, 6);
  return <div className="data-table"><table><thead><tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={index}>{columns.map((column) => <td key={column}>{formatCell(row[column])}</td>)}</tr>)}</tbody></table></div>;
}

function formatCell(value: unknown): string {
  if (value == null) return "—";
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
