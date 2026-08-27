"use client";

import { useEffect, useState } from "react";

import { AstroReviewQueue } from "@/components/AstroReviewQueue";
import { api } from "@/lib/api";
import type { CombinedAssessment, SiriusArchive, Team } from "@/lib/types";

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
