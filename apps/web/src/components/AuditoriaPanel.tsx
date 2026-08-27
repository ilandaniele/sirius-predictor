"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { TrackRecordAstrologer, TrackRecordAudit } from "@/lib/types";

const PENDING_COACH_DEBUTS: Array<{
  team: string;
  coach: string;
  opponent: string;
  date: string;
}> = [
  { team: "Bélgica", coach: "Mark van Bommel", opponent: "Italia (visitante)", date: "25/09/2026" },
  { team: "Uruguay", coach: "Diego Forlán (interino)", opponent: "Japón (visitante)", date: "24/09/2026" },
  { team: "Senegal", coach: "Patrick Vieira", opponent: "Mozambique (local)", date: "23/09/2026" },
  { team: "Croacia", coach: "Slaven Bilić (2º ciclo)", opponent: "Chequia (visitante)", date: "26/09/2026" },
  { team: "Cabo Verde", coach: "Humberto Bettencourt", opponent: "Malí (visitante)", date: "23/09/2026" },
  { team: "Haití", coach: "David Badía", opponent: "Trinidad y Tobago (neutral)", date: "24/09/2026" },
  { team: "Escocia", coach: "Sébastien Pocognoli", opponent: "Eslovenia (visitante)", date: "26/09/2026" },
  { team: "Emiratos Árabes Unidos", coach: "Zlatko Dalić", opponent: "Yemen (Copa del Golfo)", date: "24/09/2026" }
];

function AstrologerCard({ data }: { data: TrackRecordAstrologer }) {
  const correct = data.matches.filter((match) => match.outcome === "correct").length;
  return (
    <article className="panel audit-card">
      <div className="panel-title">
        <div>
          <p>{data.verifiability === "verifiable_from_dated_posts" ? "AUDITABLE" : "NO AUDITABLE"}</p>
          <h3>{data.astrologer}</h3>
        </div>
        {data.matches.length ? (
          <span className="audit-score">
            {correct}/{data.matches.length}
          </span>
        ) : null}
      </div>
      <blockquote className="audit-quote">
        &ldquo;{data.self_reported_summary}&rdquo;
        <a href={data.self_reported_url} target="_blank" rel="noreferrer">
          ver fuente ↗
        </a>
      </blockquote>
      {data.matches.length ? (
        <div className="audit-matches">
          {data.matches.map((match) => (
            <div className={`audit-match audit-match-${match.outcome}`} key={match.round}>
              <b>{match.round}</b>
              <span>{match.claim}</span>
              <div className="audit-match-meta">
                <a href={match.post_url} target="_blank" rel="noreferrer">
                  {match.published_at} ↗
                </a>
                <em>{match.outcome === "correct" ? "✓ correcto" : "✗ incorrecto"}</em>
              </div>
              {match.note ? <p className="micro">{match.note}</p> : null}
            </div>
          ))}
        </div>
      ) : (
        <p className="micro">{data.verifiability_note}</p>
      )}
    </article>
  );
}

export function AuditoriaPanel() {
  const [audit, setAudit] = useState<TrackRecordAudit | null>(null);
  const [status, setStatus] = useState("Cargando auditoría…");

  useEffect(() => {
    let cancelled = false;
    api
      .trackRecordAudit()
      .then((result) => {
        if (!cancelled) setAudit(result.data);
      })
      .catch((error: Error) => {
        if (!cancelled) setStatus(`No se pudo cargar · ${error.message}`);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="auditoria-panel">
      <div className="section-block">
        <p>
          Verificación independiente, no un cálculo del motor: contrasta lo que Sirius y Astrología
          Argumental publicaron sobre sí mismos contra sus propios posteos fechados y contra el
          resultado real del Mundial 2026. Vive en esta pestaña, separada de la de Sirius, para que
          no se confunda con su índice ni con el Monte Carlo.
        </p>
      </div>

      <SectionTitle
        title="Récord de aciertos · Mundial 2026"
        description="¿Lo que cada uno dice que acertó, lo acertó de verdad?"
      />
      {audit ? (
        <>
          <p className="micro">{audit.methodology_note}</p>
          <div className="two-columns">
            {audit.astrologers.map((entry) => (
              <AstrologerCard data={entry} key={entry.source_id} />
            ))}
          </div>
          <aside className="audit-final-note">
            <b>La final, ambos:</b> {audit.final_outcome.summary} Los dos habían predicho{" "}
            {audit.final_outcome.both_predicted.toLowerCase()}.
          </aside>
        </>
      ) : (
        <p className="empty">{status}</p>
      )}

      <SectionTitle
        title="Cobertura pendiente"
        description="Selecciones cuyo DT todavía no dirigió su primer partido a cargo del equipo."
      />
      <p className="micro">
        Investigado manualmente en agosto de 2026: estos ocho técnicos fueron nombrados semanas
        antes de esta auditoría y su debut real todavía no se jugó — no hay dato que fabricar, solo
        una fecha para volver a revisar.
      </p>
      <div className="pending-debuts">
        {PENDING_COACH_DEBUTS.map((row) => (
          <div className="pending-debut-row" key={row.team}>
            <b>{row.team}</b>
            <span>{row.coach}</span>
            <span>vs {row.opponent}</span>
            <code>{row.date}</code>
          </div>
        ))}
      </div>

      <SectionTitle
        title="Validez de la señal Argumental"
        description="¿La revolución solar del ciclo del DT predice algo real, o es ruido?"
      />
      <p className="micro">
        Calibrar esto correctamente requiere lo mismo que la calibración de ventaja de local: un
        backtest walk-forward contra Mundiales reales pasados (2010-2022), no solo 2026. Eso exige
        saber quién dirigía a cada selección en cada edición pasada y su carta de debut — datos que
        este proyecto todavía no recolectó (solo tiene al DT <em>actual</em> de cada selección, no su
        historial completo). Hacerlo con una sola edición (2026) daría una muestra demasiado chica
        para significar algo, el mismo problema que ya vimos con la ventaja de local (el ajuste
        saltó de 0 a +50 Elo con solo agregar una edición más). Pendiente: recolectar el historial de
        DTs 2010-2022 antes de calibrar esta señal — no se va a inventar un número mientras tanto.
      </p>
    </div>
  );
}

function SectionTitle({ title, description }: { title: string; description: string }) {
  return (
    <div className="section-block">
      <h2>{title}</h2>
      <p>{description}</p>
    </div>
  );
}
