"use client";

import { useEffect, useMemo, useState } from "react";

import { AstrologiaPanel } from "@/components/AstrologiaPanel";
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

const tabs = ["Predicción", "Astrología", "Sistema"] as const;

const PREDICCION_SECTIONS = [
  { id: "resumen", label: "Resumen" },
  { id: "argentina", label: "Argentina" },
  { id: "selecciones", label: "Selecciones y sorteo" },
  { id: "simulacion", label: "Simulación" },
  { id: "historial", label: "Historial" }
] as const;

function SectionHeading({
  id,
  title,
  description
}: {
  id: string;
  title: string;
  description: string;
}) {
  return (
    <div className="section-block" id={id}>
      <h2>{title}</h2>
      <p>{description}</p>
    </div>
  );
}

function SectionNav({ sections }: { sections: ReadonlyArray<{ id: string; label: string }> }) {
  return (
    <nav className="section-nav" aria-label="Ir a sección">
      {sections.map((section) => (
        <a key={section.id} href={`#${section.id}`}>
          {section.label}
        </a>
      ))}
    </nav>
  );
}

export default function Home() {
  const [formatSize, setFormatSize] = useState<48 | 64>(64);
  const [active, setActive] = useState<(typeof tabs)[number]>("Predicción");
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
  const [iterationsChoice, setIterationsChoice] = useState<"100000" | "200000" | "300000" | "custom">(
    "100000"
  );
  const [customIterations, setCustomIterations] = useState("150000");
  const [runCommand, setRunCommand] = useState<string | null>(null);
  const [commandCopied, setCommandCopied] = useState(false);

  useEffect(() => {
    Promise.all([
      api.scenario(formatSize),
      api.teams(formatSize),
      api.latest(formatSize),
      api.history(formatSize),
      api.draw(2030, formatSize),
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
  }, [formatSize]);

  const candidates = useMemo(
    () => [...teams].sort((a, b) => b.projected_elo - a.projected_elo).slice(0, 12),
    [teams]
  );
  const probableGroups = useMemo(
    () => (prediction?.argentina_groups ?? []).slice(0, 10),
    [prediction]
  );
  const maxGroupFrequency = Math.max(1e-9, ...probableGroups.map((row) => Number(row["Frecuencia %"])));
  const scenarioSource = sources.find((source) => source.source_id === "scenario");
  const modelSource = sources.find((source) => source.source_id !== "scenario") ?? scenarioSource;
  const argentinaGroup = Object.entries(draw).find(([, members]) =>
    members.some((team) => team.team_id === "ARG")
  );
  const argentinaAssessment = prediction?.sirius_assessments?.ARG;

  const resolvedIterations =
    iterationsChoice === "custom"
      ? Math.min(1_000_000, Math.max(100, Number(customIterations) || 100_000))
      : Number(iterationsChoice);

  function updateWorldCup() {
    const script = formatSize === 48 ? "SIMULAR_Y_PUBLICAR_48.cmd" : "SIMULAR_Y_PUBLICAR.cmd";
    const command = `${script} -Iterations ${resolvedIterations}`;
    setRunCommand(command);
    setCommandCopied(false);
    setStatus(
      `Cómputo pesado local (${formatSize} · ${resolvedIterations.toLocaleString("es-AR")} simulaciones): copiá el comando y corrélo en tu PC.`
    );
  }

  async function copyRunCommand() {
    if (!runCommand) return;
    try {
      await navigator.clipboard.writeText(runCommand);
      setCommandCopied(true);
    } catch {
      setCommandCopied(false);
    }
  }

  return (
    <main>
      <header className="topbar">
        <div className="brand"><i>✦</i><span>SIRIUS<br /><b>ENGINE</b></span></div>
        <div className="format-control" aria-label="Formato del torneo">
          {([64, 48] as const).map((size) => (
            <button
              key={size}
              className={formatSize === size ? "active" : ""}
              onClick={() => setFormatSize(size)}
            >
              {size} CUPOS
            </button>
          ))}
        </div>
        <div className="sim-control" aria-label="Cantidad de simulaciones">
          <select
            value={iterationsChoice}
            onChange={(event) => setIterationsChoice(event.target.value as typeof iterationsChoice)}
            aria-label="Simulaciones a correr"
          >
            <option value="100000">100.000 sim.</option>
            <option value="200000">200.000 sim.</option>
            <option value="300000">300.000 sim.</option>
            <option value="custom">Personalizado</option>
          </select>
          {iterationsChoice === "custom" ? (
            <input
              type="number"
              min={100}
              max={1000000}
              step={1000}
              value={customIterations}
              onChange={(event) => setCustomIterations(event.target.value)}
              aria-label="Cantidad personalizada de simulaciones"
            />
          ) : null}
        </div>
        <button className="update" onClick={updateWorldCup}>SIMULAR EN MI PC</button>
      </header>

      <section className="hero">
        <div>
          <p className="eyebrow">INTELIGENCIA DE TORNEO · v0.4.0</p>
          <h1>Mundial 2030<br /><em>Sirius Engine</em></h1>
          <p className="lede">Baseline futbolístico y modelos astrológicos experimentales, separados, comparables y trazables.</p>
        </div>
        <div className="status"><span className="pulse" />{status}</div>
      </section>

      {runCommand ? (
        <section className="run-command">
          <code>{runCommand}</code>
          <button onClick={copyRunCommand}>{commandCopied ? "Copiado ✓" : "Copiar comando"}</button>
          <p className="micro">
            Abrí PowerShell en la carpeta del proyecto y pegá el comando (o hacé doble clic en{" "}
            {formatSize === 48 ? "SIMULAR_Y_PUBLICAR_48.cmd" : "SIMULAR_Y_PUBLICAR.cmd"} para usar
            100.000 por defecto).
          </p>
        </section>
      ) : null}

      <aside className="disclaimer">
        La astrología no tiene validez científica demostrada para predecir fútbol. Sirius y Astrología Argumental se publican como experimentos y siempre junto a FOOTBALL_ONLY.
      </aside>

      <nav className="tabs" aria-label="Secciones">
        {tabs.map((tab) => (
          <button key={tab} className={active === tab ? "active" : ""} onClick={() => setActive(tab)}>{tab}</button>
        ))}
      </nav>

      <section className="content">
        <div className="section-heading"><div><p>VISTA ACTUAL</p><h2>{active}</h2></div>{sources[0] ? <SourceBadge source={sources[0]} /> : null}</div>
        <div className="metrics">
          <MetricCard label="Selecciones" value={scenario?.format.teams ?? "—"} detail={`4 bombos de ${scenario?.format.pot_size ?? "—"}`} source={scenarioSource} />
          <MetricCard label="Grupos" value={scenario?.format.groups ?? "—"} detail={scenario?.format.best_third_placed ? `2 + ${scenario.format.best_third_placed} mejores terceros` : "Clasifican 2"} source={scenarioSource} />
          <MetricCard label="Final" value={scenario ? `${scenario.final.city}` : "—"} detail={scenario?.final.local_date} source={scenarioSource} />
          <MetricCard label="Simulaciones" value={prediction?.iterations.toLocaleString("es-UY") ?? "Pendiente"} detail={prediction?.mode ?? "3 modelos separados"} source={modelSource} />
        </div>

        {active === "Predicción" ? (
          <>
            <SectionNav sections={PREDICCION_SECTIONS} />
            <SectionHeading
              id="resumen"
              title="Resumen"
              description="Ranking futbolístico, foco Argentina y comparador de modelos."
            />
            <div className="dashboard-grid">
              <article className="panel ranking">
                <div className="panel-title"><div><p>RANKING DE CANDIDATOS</p><h3>Fuerza futbolística proyectada</h3></div><span>Confianza ≠ fuerza</span></div>
                <div className="ranking-list">
                  {candidates.map((team, index) => (
                    <div className="rank-row" key={team.team_id}>
                      <b>{String(index + 1).padStart(2, "0")}</b><span className="flag">{team.team_id}</span><strong>{team.team}</strong>
                      <div className="bar"><i style={{ width: `${Math.max(8, (team.projected_elo - 1300) / 7)}%` }} /></div>
                      <code>{team.projected_elo}</code>
                    </div>
                  ))}
                  {!candidates.length ? <p className="empty">Esperando API de equipos.</p> : null}
                </div>
              </article>

              <article className="panel argentina">
                <div className="panel-title"><div><p>FOCO ARGENTINA</p><h3>Camino de la selección</h3></div><span className="arg-pill">ARG</span></div>
                <div className="probability"><span>Probabilidad de campeón</span><strong>{String(prediction?.ranking?.find((row) => row.ID === "ARG")?.["Campeón %"] ?? "—")}{prediction ? "%" : ""}</strong></div>
                <div className="sirius-indices">
                  <span><small>Confianza validada</small><b>{argentinaAssessment ? `${(argentinaAssessment.data_confidence * 100).toFixed(0)}%` : "0%"}</b></span>
                  <span><small>Índice recorrido</small><b>{argentinaAssessment?.journey_index.value?.toFixed(1) ?? "—"}</b></span>
                  <span><small>Índice coronación</small><b>{argentinaAssessment?.coronation_index.value?.toFixed(1) ?? "—"}</b></span>
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
            </div>

            <SectionHeading
              id="argentina"
              title="Argentina en detalle"
              description="Probabilidad de avance por etapa y rivales condicionales."
            />
            <div className="two-columns tab-detail">
              <article className="panel">
                <div className="panel-title"><div><p>ETAPAS</p><h3>Probabilidad de avance</h3></div></div>
                <DataTable rows={prediction?.argentina_stages ?? []} empty="Sin snapshot ejecutado." />
              </article>
              <article className="panel">
                <div className="panel-title"><div><p>RIVALES</p><h3>Frecuencia condicional por ronda</h3></div></div>
                {Object.entries(prediction?.argentina_rivals ?? {}).map(([round, rows]) => <div className="round-block" key={round}><b>{round}</b><DataTable rows={rows.slice(0, 5)} empty="Sin encuentros" /></div>)}
              </article>
            </div>

            <SectionHeading
              id="selecciones"
              title="Selecciones y sorteo"
              description="Campo proyectado y grupo de Argentina."
            />
            <article className="panel wide">
              <div className="panel-title"><div><p>CAMPO PROYECTADO</p><h3>{formatSize} selecciones · no es clasificación oficial</h3></div>{scenarioSource ? <SourceBadge source={scenarioSource} /> : null}</div>
              <div className="team-grid">{teams.map((team) => <div key={team.team_id}><b>{team.team_id}</b><strong>{team.team}</strong><span>{team.confed} · Bombo {team.pot}</span><small>Elo {team.projected_elo}</small></div>)}</div>
            </article>
            <div className="two-columns">
              <article className="panel">
                <div className="panel-title"><div><p>SEED 2030</p><h3>Un sorteo legal reproducible</h3></div>{scenarioSource ? <SourceBadge source={scenarioSource} /> : null}</div>
                <div className="groups-grid">{Object.entries(draw).map(([group, members]) => <div key={group}><b>Grupo {group}</b>{members.map((team) => <span key={team.team_id}>{team.team_id} · {team.team}</span>)}</div>)}</div>
              </article>
              <article className="panel">
                <div className="panel-title"><div><p>ARGENTINA</p><h3>Los 10 grupos más probables</h3></div></div>
                {probableGroups.length ? (
                  <div className="probable-groups">
                    {probableGroups.map((row, index) => (
                      <div className="probable-group-row" key={String(row["Otros tres equipos"])}>
                        <b>{String(index + 1).padStart(2, "0")}</b>
                        <span>Argentina · {String(row["Otros tres equipos"])}</span>
                        <div className="bar">
                          <i
                            style={{
                              width: `${Math.max(6, (Number(row["Frecuencia %"]) / maxGroupFrequency) * 100)}%`
                            }}
                          />
                        </div>
                        <code>{Number(row["Frecuencia %"]).toFixed(3)}%</code>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="empty">Ejecutá una actualización para estimar familias.</p>
                )}
                {argentinaGroup ? (
                  <div className="focus-group-example">
                    <small>Ejemplo de sorteo reproducible (semilla fija) · no es una predicción</small>
                    <div className="focus-group">
                      <b>Grupo {argentinaGroup[0]}</b>
                      {argentinaGroup[1].map((team) => <span key={team.team_id}>{team.team}</span>)}
                    </div>
                  </div>
                ) : null}
              </article>
            </div>

            <SectionHeading
              id="simulacion"
              title="Simulación"
              description="Ranking Monte Carlo, cruces decisivos y exportaciones de llaves."
            />
            <aside className={`sirius-state ${prediction?.sirius_application?.effective ? "active" : "neutral"}`}>
              <b>{prediction?.sirius_application?.label ?? "Sirius todavía no fue evaluado"}</b>
              <span>
                {prediction?.sirius_application
                  ? `${prediction.sirius_application.reviewed_observations} observaciones revisadas · ${prediction.sirius_application.teams_with_evidence} selecciones con evidencia`
                  : "Ejecutá la simulación local para verificar si Sirius aporta una señal diferencial."}
              </span>
            </aside>
            <div className="two-columns">
              <article className="panel">
                <div className="panel-title"><div><p>MONTE CARLO</p><h3>Ranking de campeón</h3></div>{modelSource ? <SourceBadge source={modelSource} /> : null}</div>
                <DataTable rows={prediction?.ranking?.slice(0, 20) ?? []} empty="Todavía no hay simulación persistida." maxColumns={8} />
              </article>
              <article className="panel">
                <div className="panel-title"><div><p>CRUCES DECISIVOS</p><h3>Los cinco escenarios conjuntos más frecuentes</h3></div></div>
                <div className="bracket-list">
                  {prediction?.top_brackets?.map((bracket, index) => {
                    const semifinals = (bracket.decisive_matches ?? []).filter((match) => match.round === "SF");
                    return <div key={bracket.signature}>
                      <b>#{index + 1} · {bracket.champion}</b>
                      <span>{semifinals.length ? `${semifinals.map((match) => `${match.team_a}–${match.team_b}`).join(" · ")} · ` : ""}{Number(bracket.density_percent).toFixed(4)}% conjunto</span>
                    </div>;
                  })}
                </div>
                {!prediction?.top_brackets?.length ? <p className="empty">Sin escenarios decisivos simulados.</p> : null}
              </article>
            </div>
            <article className="panel wide bracket-gallery">
              <div className="panel-title"><div><p>EXPORTACIONES REPRODUCIBLES</p><h3>Semifinales, final y campeón · PNG 4K, SVG y PDF</h3></div></div>
              {prediction?.bracket_urls?.length ? <>
                {(() => {
                  const featured = prediction.bracket_urls[0];
                  const featuredStats = prediction.top_brackets?.[0];
                  const featuredTeam = featuredStats ? teams.find((team) => team.team_id === featuredStats.champion) : undefined;
                  return <div className="bracket-featured">
                    <div className="bracket-featured-label">
                      <span className="badge-star">★ Escenario más probable</span>
                      {featuredStats ? <span>{featuredTeam?.team ?? featuredStats.champion} campeón · {Number(featuredStats.density_percent).toFixed(4)}% del Monte Carlo</span> : null}
                    </div>
                    <a className="bracket-zoom" href={api.asset(featured.svg)} target="_blank" rel="noreferrer" aria-label="Ampliar escenario decisivo 1 en una pestaña nueva">
                      <object aria-label="Escenario decisivo 1, el más probable" data={api.asset(featured.svg)} type="image/svg+xml" />
                      <span className="bracket-zoom-hint">🔍 Ampliar (abre en pestaña nueva, con zoom)</span>
                    </a>
                    <div className="bracket-actions">
                      <a href={api.asset(featured.png)} download>PNG</a>
                      <a href={api.asset(featured.svg)} download>SVG</a>
                      <a href={api.asset(featured.pdf)} download>PDF</a>
                    </div>
                  </div>;
                })()}
                <div className="bracket-grid">{prediction.bracket_urls.slice(1).map((bracket) => <div key={bracket.rank}><a className="bracket-zoom" href={api.asset(bracket.svg)} target="_blank" rel="noreferrer" aria-label={`Ampliar escenario decisivo ${bracket.rank} en una pestaña nueva`}><object aria-label={`Escenario decisivo ${bracket.rank}`} data={api.asset(bracket.svg)} type="image/svg+xml" /><span className="bracket-zoom-hint">🔍 Ampliar</span></a><div><b>Escenario #{bracket.rank}</b><a href={api.asset(bracket.png)} download>PNG</a><a href={api.asset(bracket.svg)} download>SVG</a><a href={api.asset(bracket.pdf)} download>PDF</a></div></div>)}</div>
              </> : <p className="empty">Ejecutá SIMULAR_Y_PUBLICAR.cmd. Las imágenes quedan guardadas en storage/outbox/runs aunque falle una etapa posterior.</p>}
            </article>
            <article className="panel wide">
              <div className="panel-title"><div><p>SENSIBILIDAD</p><h3>Hora de la final y datos desconocidos</h3></div></div>
              <DataTable rows={prediction?.sensitivity ?? []} empty="Se genera con una simulación; 4 horas × 3 offsets." />
            </article>

            <SectionHeading
              id="historial"
              title="Historial"
              description="Evolución append-only de la probabilidad de campeón."
            />
            <article className="panel history">
              <div className="panel-title"><div><p>EVOLUCIÓN APPEND-ONLY</p><h3>Argentina · España · Francia · Brasil</h3></div></div>
              <HistoryChart points={history} />
            </article>
          </>
        ) : null}

        {active === "Astrología" ? (
          <>
            <div className="section-block">
              <p>
                Dos fuentes astrológicas públicas independientes, cada una con su propia cola de
                revisión humana append-only: Sirius (múltiples cartas natales combinadas) y
                Astrología Argumental (método Frawley sobre la carta del partido, astrología
                electiva y mundana). Ninguna influye en el Monte Carlo; los modelos FOOTBALL_ONLY,
                SIRIUS_ONLY e HYBRID siguen separados como siempre.
              </p>
            </div>
            <AstrologiaPanel teams={teams} />
          </>
        ) : null}

        {active === "Sistema" ? (
          <>
            <SectionHeading
              id="fuentes"
              title="Fuentes"
              description="Catálogo y gobernanza de cada fuente pública utilizada."
            />
            <article className="panel wide">
              <div className="panel-title"><div><p>CATÁLOGO Y GOBERNANZA</p><h3>Fuente · URL · calidad · uso</h3></div></div>
              <div className="source-grid">{sourceCatalog.map((source) => <div key={source.id}><span className={`grade quality-${source.grade}`}>{source.grade}</span><strong>{source.name}</strong><p>{source.use}</p>{source.url?.startsWith("http") ? <a href={source.url} target="_blank" rel="noreferrer">Abrir fuente ↗</a> : <code>{source.url ?? "Adaptador pendiente"}</code>}<small>{source.enabled ? "Habilitada" : "Deshabilitada"} · robots: {source.robots_policy ?? "sin registrar"}</small></div>)}</div>
            </article>

            <SectionHeading
              id="backtesting"
              title="Backtesting"
              description="Validación temporal contra ediciones pasadas del Mundial."
            />
            <article className="panel wide">
              <div className="panel-title"><div><p>VALIDACIÓN TEMPORAL</p><h3>2010 · 2014 · 2018 · 2022 · 2026</h3></div>{modelSource ? <SourceBadge source={modelSource} /> : null}</div>
              {backtest ? <><p className="micro">{backtest.matches} partidos · disponibles {backtest.available_editions.join(", ")}{backtest.missing_editions.length ? ` · sin datos: ${backtest.missing_editions.join(", ")}` : ""}</p><DataTable rows={backtest.metrics} empty="Sin métricas." /><h3 className="subheading">Ablaciones</h3><DataTable rows={backtest.ablations} empty="Sin ablaciones." /></> : <p className="empty">Ejecutá scripts/release_acceptance.py; el dashboard no inventa resultados ausentes.</p>}
            </article>

            <article className="panel wide calibration-panel">
              <div className="panel-title"><div><p>CALIBRACIÓN EMPÍRICA</p><h3>Ningún parámetro se supone: se ajusta contra Mundiales reales</h3></div></div>
              {backtest?.next_edition_calibration ? <>
                <p className="micro">
                  Cada parámetro de ajuste (ventaja de local, peso de la señal lunar Sirius) se recalcula en cada corrida
                  con una búsqueda grid walk-forward que minimiza log-loss sólo contra ediciones anteriores a la que se evalúa,
                  sin fuga temporal. El valor de abajo es el entrenado con {backtest.available_editions.join(", ")} — el que
                  se usa para simular un Mundial todavía no jugado.
                </p>
                <div className="calibration-values">
                  <div>
                    <small>Ventaja de local</small>
                    <b>+{backtest.next_edition_calibration.host_bonus_elo.toFixed(0)} Elo</b>
                    <span>Sur 2010 y Qatar 2022 rindieron por debajo como anfitriones; Brasil 2014 y Rusia 2018, por encima. Se cancelan: sin evidencia histórica de una ventaja sistemática.</span>
                  </div>
                  <div>
                    <small>Peso señal lunar (Sirius)</small>
                    <b>{backtest.next_edition_calibration.alpha.toFixed(2)}</b>
                    <span>Se aplica sólo con evidencia lunar publicada por Sirius (hoy, Argentina); el resto de las selecciones queda neutral hasta tener datos propios.</span>
                  </div>
                </div>
                <h3 className="subheading">Historia de calibración por edición (walk-forward)</h3>
                <DataTable rows={backtest.calibration_manifest} empty="Sin historial de calibración." />
              </> : <p className="empty">Sin calibración persistida todavía.</p>}
            </article>

            <SectionHeading
              id="configuracion"
              title="Configuración"
              description="Supuestos del escenario y separación obligatoria de modelos."
            />
            <div className="two-columns">
              <article className="panel">
                <div className="panel-title"><div><p>ESCENARIO</p><h3>Supuestos configurables</h3></div>{scenarioSource ? <SourceBadge source={scenarioSource} /> : null}</div>
                <ul className="config-list">
                  <li>{formatSize} equipos · {scenario?.format.groups ?? "—"} grupos · {scenario?.format.best_third_placed ? "2 + 8 mejores terceros" : "clasifican 2"}</li>
                  <li>64 es el valor predeterminado; 48 usa la estructura oficial 2026 como alternativa</li>
                  <li>Monte Carlo, backtesting y llaves se calculan localmente; Fly sólo valida y publica</li>
                  <li>Máximo 2 UEFA y 1 de otras confederaciones</li>
                  <li>Argentina y España en sectores opuestos</li>
                  <li>Final Madrid · 21/07/2030 · 18:00 base</li>
                  <li>Sensibilidad 17/18/20/21 y ±15 minutos</li>
                </ul>
              </article>
              <article className="panel">
                <div className="panel-title"><div><p>MODELOS</p><h3>Separación obligatoria</h3></div></div>
                {["FOOTBALL_ONLY", "SIRIUS_ONLY", "HYBRID"].map((model) => <div className="model-row" key={model}><i /><b>{model}</b><span>versionado</span></div>)}
              </article>
            </div>
          </>
        ) : null}
      </section>

      <footer><span>Mundial 2030 Sirius Engine</span><span>Madrid · 21/07/2030 · 18:00 base · ±15 min</span></footer>
    </main>
  );
}

function DataTable({
  rows,
  empty,
  maxColumns = 6
}: {
  rows: Array<Record<string, unknown>>;
  empty: string;
  maxColumns?: number;
}) {
  if (!rows.length) return <p className="empty">{empty}</p>;
  const columns = Object.keys(rows[0]).slice(0, maxColumns);
  return <div className="data-table"><table><thead><tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={index}>{columns.map((column) => <td key={column}>{formatCell(row[column])}</td>)}</tr>)}</tbody></table></div>;
}

function formatCell(value: unknown): string {
  if (value == null) return "—";
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
