"use client";

import { useEffect, useState } from "react";

import { AstroReviewQueue } from "@/components/AstroReviewQueue";
import { api } from "@/lib/api";
import type { CombinedAssessment, CycleFortune, SiriusArchive, Team } from "@/lib/types";

const DIGNITY_LABELS: Record<string, string> = {
  domicile: "domicilio",
  exaltation: "exaltación",
  detriment: "exilio",
  fall: "caída",
  peregrine: "peregrino"
};

function CycleFortuneTable({
  fortunes,
  teams,
  status
}: {
  fortunes: Record<string, CycleFortune> | null;
  teams: Team[];
  status: string;
}) {
  if (!fortunes) return <p className="empty">{status || "Calculando…"}</p>;
  const teamNames = new Map(teams.map((team) => [team.team_id, team.team]));
  const ranked = Object.values(fortunes).sort((a, b) => b.fortune_index - a.fortune_index);
  if (!ranked.length) return <p className="empty">Sin selecciones con carta de debut del DT.</p>;
  const unavailable = ranked[0]?.status === "ephemeris_unavailable";
  return (
    <div className="cycle-fortune-list">
      {unavailable ? (
        <p className="micro">
          Swiss Ephemeris no está disponible en este entorno: los índices quedan en 0 (neutro)
          hasta correr la simulación local, donde sí se calculan con datos reales.
        </p>
      ) : null}
      {ranked.map((item) => (
        <div className="cycle-fortune-row" key={item.team_id}>
          <b>{teamNames.get(item.team_id) ?? item.team_id}</b>
          <span className="cycle-fortune-coach">
            DT {item.coach_name}
            {item.status === "computed"
              ? ` · MC en ${item.midheaven_sign} regido por ${item.midheaven_ruler} (${
                  DIGNITY_LABELS[item.midheaven_ruler_dignity] ?? item.midheaven_ruler_dignity
                }, ${item.midheaven_ruler_house_class})`
              : ""}
          </span>
          <div className="bar">
            <i
              style={{
                width: `${Math.max(2, ((item.fortune_index + 1) / 2) * 100)}%`,
                background: item.fortune_index >= 0 ? undefined : "#b5654f"
              }}
            />
          </div>
          <code>{item.fortune_index >= 0 ? "+" : ""}{item.fortune_index.toFixed(2)}</code>
          {item.favorable_testimonies.length || item.adverse_testimonies.length ? (
            <span className="cycle-fortune-testimonies">
              {item.favorable_testimonies.map((t) => `+ ${t}`).join(" · ")}
              {item.favorable_testimonies.length && item.adverse_testimonies.length ? " · " : ""}
              {item.adverse_testimonies.map((t) => `− ${t}`).join(" · ")}
            </span>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function ArchiveCard({ archive, empty }: { archive: SiriusArchive | null; empty: string }) {
  if (!archive) return <p className="empty">{empty}</p>;
  return (
    <>
      <div className="archive-stats">
        <b>
          {archive.captured_total}/{archive.declared_total}
        </b>
        <span>posts completos · {archive.sports_relevant_total} deportivos</span>
        <small>
          {new Date(archive.earliest_published_at).toLocaleDateString("es-UY")} →{" "}
          {new Date(archive.latest_published_at).toLocaleDateString("es-UY")} · calidad B
        </small>
      </div>
      <div className="archive-posts">
        {archive.recent_sports_posts.slice(0, 8).map((post) => (
          <a key={post.post_id} href={post.url} target="_blank" rel="noreferrer">
            <b>{post.title}</b>
            <span>
              {new Date(post.published_at).toLocaleDateString("es-UY")} · revisión pendiente
            </span>
          </a>
        ))}
      </div>
    </>
  );
}

export function AstrologiaPanel({ teams }: { teams: Team[] }) {
  const [siriusArchive, setSiriusArchive] = useState<SiriusArchive | null>(null);
  const [argumentalArchive, setArgumentalArchive] = useState<SiriusArchive | null>(null);
  const [combined, setCombined] = useState<CombinedAssessment | null>(null);
  const [status, setStatus] = useState("Cargando comparación de fuentes…");
  const [showComplementary, setShowComplementary] = useState(false);
  const [cycleFortunes, setCycleFortunes] = useState<Record<string, CycleFortune> | null>(null);
  const [cycleFortuneStatus, setCycleFortuneStatus] = useState("Calculando revolución solar…");

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.siriusArchive(), api.argumentalArchive(), api.combinedAssessment()])
      .then(([sirius, argumental, combinedResult]) => {
        if (cancelled) return;
        setSiriusArchive(sirius.data);
        setArgumentalArchive(argumental.data);
        setCombined(combinedResult.data);
        setStatus("");
      })
      .catch((error: Error) => {
        if (!cancelled) setStatus(`No se pudo calcular la comparación · ${error.message}`);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!showComplementary || cycleFortunes) return;
    let cancelled = false;
    api
      .argumentalCycleFortune()
      .then((result) => {
        if (cancelled) return;
        setCycleFortunes(result.data);
      })
      .catch((error: Error) => {
        if (!cancelled) setCycleFortuneStatus(`No se pudo calcular · ${error.message}`);
      });
    return () => {
      cancelled = true;
    };
  }, [showComplementary, cycleFortunes]);

  const rows: Array<{ key: "sirius" | "argumental" | "combined"; label: string }> = [
    { key: "sirius", label: "Sirius" },
    { key: "argumental", label: "Astrología Argumental" },
    { key: "combined", label: "Combinado" },
  ];

  return (
    <div className="astrologia-panel">
      <article className="panel">
        <div className="panel-title">
          <div>
            <p>ARCHIVO JUAN CRUZ SIRIUS</p>
            <h3>astrologiadeportivaa.blogspot.com</h3>
          </div>
        </div>
        <ArchiveCard
          archive={siriusArchive}
          empty="La preparación del input captura el archivo completo; las coincidencias quedan pendientes de revisión manual."
        />
      </article>

      <AstroReviewQueue teams={teams} source="sirius" />

      <button
        type="button"
        className="complementary-toggle"
        onClick={() => setShowComplementary((value) => !value)}
        aria-expanded={showComplementary}
      >
        {showComplementary ? "− Ocultar" : "+ Ver"} análisis complementarios (otra fuente
        independiente)
      </button>

      {showComplementary ? (
        <div className="complementary-block">
          <p className="micro">
            Astrología Argumental es un astrólogo tradicional y electivo independiente
            (Santiago Rodríguez Spuch, autor del libro homónimo; también publica en{" "}
            <a href="https://www.instagram.com/astrologia.argumental/" target="_blank" rel="noreferrer">
              Instagram
            </a>
            , pero ese canal no puede scrapearse: su robots.txt prohíbe explícitamente la
            recolección automatizada). Se lo trae acá como segunda opinión astrológica
            —método Frawley, astrología electiva y mundana— nunca mezclado con el índice
            de Sirius ni con el Monte Carlo: mismo circuito de revisión humana append-only
            que Sirius, con su propia cola pendiente y su propia fuente citada.
          </p>
          <article className="panel wide">
            <div className="panel-title">
              <div>
                <p>COMPARACIÓN DE ÍNDICES · ARGENTINA</p>
                <h3>Sirius vs. Astrología Argumental vs. combinado</h3>
              </div>
            </div>
            <p className="micro" aria-live="polite">
              {status ||
                "Cálculo en vivo a partir de la evidencia aprobada en cada cola de revisión; no está ligado a una simulación puntual."}
            </p>
            <div className="compare-grid">
              <div className="compare-head">
                <span />
                <span>Índice recorrido</span>
                <span>Índice coronación</span>
                <span>Confianza</span>
                <span>Evidencia revisada</span>
              </div>
              {rows.map(({ key, label }) => {
                const assessment = combined?.[key]?.ARG;
                const audit = combined?.[`${key}_evidence_audit`];
                return (
                  <div className="compare-row" key={key}>
                    <b>{label}</b>
                    <span data-label="Índice recorrido">
                      {assessment?.journey_index.value?.toFixed(1) ?? "Sin evidencia"}
                    </span>
                    <span data-label="Índice coronación">
                      {assessment?.coronation_index.value?.toFixed(1) ?? "Sin evidencia"}
                    </span>
                    <span data-label="Confianza">
                      {assessment ? `${(assessment.data_confidence * 100).toFixed(0)}%` : "0%"}
                    </span>
                    <span data-label="Evidencia">
                      {audit?.reviewed_observations ?? 0} observaciones
                    </span>
                  </div>
                );
              })}
            </div>
          </article>
          <article className="panel wide">
            <div className="panel-title">
              <div>
                <p>REVOLUCIÓN SOLAR DEL CICLO · TÉCNICA ARGUMENTAL</p>
                <h3>Fortuna anual del ciclo del DT, por selección</h3>
              </div>
            </div>
            <p className="micro">
              Cálculo propio aplicando la técnica que Astrología Argumental usó él mismo en su
              análisis de la final real del Mundial 2026 (Argentina–España): la revolución solar
              de la carta debut de cada DT, leída por dignidad y angularidad del regente del
              Medio Cielo y sus aspectos a Júpiter/Saturno/Neptuno — sus propias palabras fueron
              &ldquo;siempre es importante lo más macro, la Solar&rdquo;. No es un pronóstico suyo, es
              nuestra aplicación de su método público, y no toca el Monte Carlo. Dato honesto:
              con esa misma lógica, él predijo a Argentina campeona de la final real 2026 y
              España ganó.
            </p>
            <CycleFortuneTable fortunes={cycleFortunes} teams={teams} status={cycleFortuneStatus} />
          </article>
          <article className="panel">
            <div className="panel-title">
              <div>
                <p>ARCHIVO ASTROLOGÍA ARGUMENTAL</p>
                <h3>astrologiaargumental.blogspot.com</h3>
              </div>
            </div>
            <ArchiveCard
              archive={argumentalArchive}
              empty="Segunda fuente pública (método Frawley, astrología electiva y mundana); todavía no fue capturada por ACTUALIZAR."
            />
          </article>
          <AstroReviewQueue teams={teams} source="argumental" />
        </div>
      ) : null}
    </div>
  );
}
