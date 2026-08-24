"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";
import type {
  AstroSource,
  SiriusReviewCandidate,
  SiriusReviewDecisionInput,
  SiriusReviewQueue as SiriusReviewQueueData,
  SiriusReviewStatus,
  Team,
} from "@/lib/types";

const TIME_REQUIRED_BY_SOURCE: Record<AstroSource, Set<string>> = {
  sirius: new Set([
    "solar_return",
    "primary_directions",
    "arabic_parts",
    "lunar_return",
    "demi_lunar",
    "quarti_lunar",
    "kickoff_chart",
    "houses_i_vii",
    "rulers_mc_moon",
    "match_arabic_parts",
    "extra_time_penalties",
    "critical_minutes",
  ]),
  argumental: new Set([
    "frawley_method",
    "house_rulers",
    "aspects_applying_separating",
    "midheaven_ascendant",
    "electional_domification",
  ]),
};

const SOURCE_LABEL: Record<AstroSource, string> = {
  sirius: "Sirius",
  argumental: "Astrología Argumental",
};

type ReviewForm = {
  action: "approved" | "rejected";
  reviewer: string;
  reason: string;
  teamId: string;
  featureId: string;
  polarity: "favorable" | "adverse" | "neutral";
  strength: string;
  dataConfidence: string;
  hourRobustness: string;
  description: string;
  timeKnown: boolean;
  timeSourceUrl: string;
  timeConsultedAt: string;
  timeDataGrade: "" | "A" | "B" | "C" | "D" | "X";
  timeSourceNote: string;
};

const EMPTY_FORM: ReviewForm = {
  action: "rejected",
  reviewer: "",
  reason: "",
  teamId: "ARG",
  featureId: "",
  polarity: "neutral",
  strength: "0.50",
  dataConfidence: "0.60",
  hourRobustness: "",
  description: "",
  timeKnown: false,
  timeSourceUrl: "",
  timeConsultedAt: "",
  timeDataGrade: "",
  timeSourceNote: "",
};

function formForCandidate(
  candidate: SiriusReviewCandidate,
  current: ReviewForm,
): ReviewForm {
  return {
    ...EMPTY_FORM,
    reviewer: current.reviewer,
    teamId: current.teamId,
    featureId: candidate.technique_mentions[0] ?? "",
    description: candidate.claim_text,
  };
}

export function AstroReviewQueue({ teams, source }: { teams: Team[]; source: AstroSource }) {
  const [filter, setFilter] = useState<SiriusReviewStatus>("pending");
  const [offset, setOffset] = useState(0);
  const [queue, setQueue] = useState<SiriusReviewQueueData | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [form, setForm] = useState<ReviewForm>(EMPTY_FORM);
  const [apiKey, setApiKey] = useState("");
  const [message, setMessage] = useState("Cargando cola de revisión…");
  const [busy, setBusy] = useState(false);

  const selected = useMemo(
    () => queue?.items.find((candidate) => candidate.id === selectedId) ?? null,
    [queue, selectedId],
  );

  async function load(
    nextFilter: SiriusReviewStatus = filter,
    nextOffset = offset,
  ) {
    try {
      const result = await api.astroReviewCandidates(source, nextFilter, nextOffset);
      setQueue(result.data);
      setMessage(
        result.data.counts.total
          ? `${result.data.counts.pending} pendientes · ${result.data.counts.approved} aprobadas · ${result.data.counts.rejected} rechazadas`
          : "La cola está vacía. Sincronizá el archivo capturado.",
      );
      if (!result.data.items.some((candidate) => candidate.id === selectedId)) {
        const first = result.data.items[0] ?? null;
        setSelectedId(first?.id ?? null);
        if (first) setForm((current) => formForCandidate(first, current));
      }
    } catch (error) {
      setMessage(`No se pudo leer la cola · ${(error as Error).message}`);
    }
  }

  useEffect(() => {
    let cancelled = false;
    void api.astroReviewCandidates(source, filter, offset).then(
      (result) => {
        if (cancelled) return;
        setQueue(result.data);
        setMessage(
          result.data.counts.total
            ? `${result.data.counts.pending} pendientes · ${result.data.counts.approved} aprobadas · ${result.data.counts.rejected} rechazadas`
            : "La cola está vacía. Sincronizá el archivo capturado.",
        );
        const first = result.data.items[0] ?? null;
        setSelectedId(first?.id ?? null);
        if (first) setForm((current) => formForCandidate(first, current));
      },
      (error: Error) => {
        if (!cancelled)
          setMessage(`No se pudo leer la cola · ${error.message}`);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [source, filter, offset]);

  async function syncArchive() {
    setBusy(true);
    setMessage("Sincronizando candidatos sin aprobarlos…");
    try {
      await api.syncAstroReviewCandidates(source, apiKey);
      await load(filter, offset);
    } catch (error) {
      setMessage(`No se pudo sincronizar · ${(error as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const payload: SiriusReviewDecisionInput = {
      action: form.action,
      reviewer: form.reviewer,
      reason: form.reason,
      expected_decision_id: selected.latest_decision?.id ?? null,
    };
    if (form.action === "approved") {
      payload.approval = {
        team_id: form.teamId,
        feature_id: form.featureId,
        polarity: form.polarity,
        strength: Number(form.strength),
        data_confidence: Number(form.dataConfidence),
        hour_robustness: form.hourRobustness
          ? Number(form.hourRobustness)
          : null,
        description: form.description,
        time_known: form.timeKnown,
        time_source_url: form.timeSourceUrl || null,
        time_consulted_at: form.timeConsultedAt || null,
        time_data_grade: form.timeDataGrade || null,
        time_source_note: form.timeSourceNote || null,
      };
    }
    setBusy(true);
    setMessage("Guardando una nueva decisión inmutable…");
    try {
      await api.decideAstroReviewCandidate(source, selected.id, payload, apiKey);
      setMessage(
        "Decisión guardada. La próxima simulación local generará un snapshot si cambió la evidencia.",
      );
      await load(filter, offset);
    } catch (error) {
      setMessage(`No se pudo guardar · ${(error as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  const requiresTime = TIME_REQUIRED_BY_SOURCE[source].has(form.featureId);

  return (
    <article className="panel wide review-queue">
      <div className="panel-title">
        <div>
          <p>REVISIÓN HUMANA APPEND-ONLY · {SOURCE_LABEL[source].toUpperCase()}</p>
          <h3>Candidatos del archivo → evidencia estructurada</h3>
        </div>
        <button type="button" onClick={syncArchive} disabled={busy}>
          Sincronizar archivo
        </button>
      </div>
      <div className="review-toolbar">
        <div role="group" aria-label="Estado de revisión">
          {(["pending", "approved", "rejected", "all"] as const).map(
            (status) => (
              <button
                type="button"
                key={status}
                className={filter === status ? "active" : ""}
                onClick={() => {
                  setOffset(0);
                  setFilter(status);
                }}
              >
                {status === "pending"
                  ? "Pendientes"
                  : status === "approved"
                    ? "Aprobadas"
                    : status === "rejected"
                      ? "Rechazadas"
                      : "Todas"}
              </button>
            ),
          )}
        </div>
        <label>
          API key de revisión
          <input
            type="password"
            value={apiKey}
            onChange={(event) => setApiKey(event.target.value)}
            autoComplete="off"
            placeholder="Sólo requerida en producción"
          />
        </label>
      </div>
      <p className="micro" aria-live="polite">
        {message}
      </p>
      {queue?.counts.total ? (
        <div className="review-pagination">
          <button
            type="button"
            disabled={offset === 0 || busy}
            onClick={() => setOffset(Math.max(0, offset - 200))}
          >
            ← Anteriores
          </button>
          <span>
            {offset + 1}–
            {Math.min(
              offset + queue.items.length,
              queue.counts[filter === "all" ? "total" : filter],
            )}{" "}
            de {queue.counts[filter === "all" ? "total" : filter]}
          </span>
          <button
            type="button"
            disabled={
              offset + queue.items.length >=
                queue.counts[filter === "all" ? "total" : filter] || busy
            }
            onClick={() => setOffset(offset + 200)}
          >
            Siguientes →
          </button>
        </div>
      ) : null}
      <div className="review-layout">
        <div className="review-list">
          {queue?.items.map((candidate) => (
            <button
              type="button"
              key={candidate.id}
              className={selected?.id === candidate.id ? "active" : ""}
              onClick={() => {
                setSelectedId(candidate.id);
                setForm((current) => formForCandidate(candidate, current));
              }}
            >
              <span>
                {candidate.status} · B ·{" "}
                {new Date(candidate.published_at).toLocaleDateString("es-UY")}
              </span>
              <b>{candidate.title}</b>
              <small>{candidate.claim_text}</small>
            </button>
          ))}
          {!queue?.items.length ? (
            <p className="empty">No hay candidatos para este filtro.</p>
          ) : null}
        </div>
        {selected ? (
          <form className="review-form" onSubmit={submit}>
            <div className="review-source">
              <span>FUENTE B · inferida · no integrada automáticamente</span>
              <blockquote>{selected.claim_text}</blockquote>
              <a href={selected.source_url} target="_blank" rel="noreferrer">
                Abrir publicación fuente ↗
              </a>
              <small>
                Consultada{" "}
                {new Date(selected.consulted_at).toLocaleString("es-UY")} · SHA{" "}
                {selected.content_sha256.slice(0, 12)}
              </small>
            </div>
            <div className="review-action">
              <label>
                <input
                  type="radio"
                  checked={form.action === "rejected"}
                  onChange={() => setForm({ ...form, action: "rejected" })}
                />{" "}
                Rechazar
              </label>
              <label>
                <input
                  type="radio"
                  checked={form.action === "approved"}
                  disabled={!selected.technique_mentions.length}
                  onChange={() => setForm({ ...form, action: "approved" })}
                />{" "}
                Aprobar estructurada
              </label>
            </div>
            <label>
              Revisor
              <input
                required
                minLength={2}
                value={form.reviewer}
                onChange={(event) =>
                  setForm({ ...form, reviewer: event.target.value })
                }
              />
            </label>
            <label>
              Motivo de la decisión
              <textarea
                required
                minLength={5}
                value={form.reason}
                onChange={(event) =>
                  setForm({ ...form, reason: event.target.value })
                }
              />
            </label>
            {form.action === "approved" ? (
              <div className="approval-fields">
                <label>
                  Selección
                  <select
                    value={form.teamId}
                    onChange={(event) =>
                      setForm({ ...form, teamId: event.target.value })
                    }
                  >
                    {teams.map((team) => (
                      <option value={team.team_id} key={team.team_id}>
                        {team.team_id} · {team.team}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Técnica
                  <select
                    value={form.featureId}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        featureId: event.target.value,
                        timeKnown: false,
                        hourRobustness: "",
                        timeSourceUrl: "",
                        timeConsultedAt: "",
                        timeDataGrade: "",
                        timeSourceNote: "",
                      })
                    }
                  >
                    {selected.technique_mentions.map((technique) => (
                      <option value={technique} key={technique}>
                        {technique}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Polaridad
                  <select
                    value={form.polarity}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        polarity: event.target.value as ReviewForm["polarity"],
                      })
                    }
                  >
                    <option value="favorable">Favorable</option>
                    <option value="adverse">Adversa</option>
                    <option value="neutral">Neutral</option>
                  </select>
                </label>
                <label>
                  Fuerza descriptiva
                  <input
                    type="number"
                    min="0"
                    max="1"
                    step="0.05"
                    required
                    value={form.strength}
                    onChange={(event) =>
                      setForm({ ...form, strength: event.target.value })
                    }
                  />
                </label>
                <label>
                  Confianza del dato
                  <input
                    type="number"
                    min="0"
                    max="1"
                    step="0.05"
                    required
                    value={form.dataConfidence}
                    onChange={(event) =>
                      setForm({ ...form, dataConfidence: event.target.value })
                    }
                  />
                </label>
                <label>
                  Robustez horaria
                  <input
                    type="number"
                    min="0"
                    max="1"
                    step="0.05"
                    value={form.hourRobustness}
                    onChange={(event) =>
                      setForm({ ...form, hourRobustness: event.target.value })
                    }
                  />
                </label>
                <label className="full">
                  Descripción revisada
                  <textarea
                    required
                    minLength={5}
                    value={form.description}
                    onChange={(event) =>
                      setForm({ ...form, description: event.target.value })
                    }
                  />
                </label>
                <label className="time-check full">
                  <input
                    type="checkbox"
                    checked={form.timeKnown}
                    onChange={(event) =>
                      setForm({ ...form, timeKnown: event.target.checked })
                    }
                  />{" "}
                  Hora real verificada; nunca se usa 12:00 como reemplazo
                </label>
                {requiresTime && form.timeKnown ? (
                  <div className="time-provenance full">
                    <label>
                      URL de la fuente horaria
                      <input
                        type="url"
                        required
                        value={form.timeSourceUrl}
                        onChange={(event) =>
                          setForm({
                            ...form,
                            timeSourceUrl: event.target.value,
                          })
                        }
                      />
                    </label>
                    <label>
                      Consultada (ISO 8601 con offset)
                      <input
                        type="text"
                        required
                        placeholder="2026-08-20T18:00:00-03:00"
                        value={form.timeConsultedAt}
                        onChange={(event) =>
                          setForm({
                            ...form,
                            timeConsultedAt: event.target.value,
                          })
                        }
                      />
                    </label>
                    <label>
                      Calidad de la fuente
                      <select
                        required
                        value={form.timeDataGrade}
                        onChange={(event) =>
                          setForm({
                            ...form,
                            timeDataGrade: event.target
                              .value as ReviewForm["timeDataGrade"],
                          })
                        }
                      >
                        <option value="">Elegir A/B/C/D/X</option>
                        {(["A", "B", "C", "D", "X"] as const).map((grade) => (
                          <option value={grade} key={grade}>
                            {grade}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Nota de verificación
                      <textarea
                        required
                        minLength={5}
                        value={form.timeSourceNote}
                        onChange={(event) =>
                          setForm({
                            ...form,
                            timeSourceNote: event.target.value,
                          })
                        }
                      />
                    </label>
                  </div>
                ) : null}
                {requiresTime && !form.timeKnown ? (
                  <p className="review-warning full">
                    Esta técnica requiere hora real. El backend bloqueará la
                    aprobación mientras siga desconocida.
                  </p>
                ) : null}
              </div>
            ) : null}
            {!selected.technique_mentions.length ? (
              <p className="review-warning">
                No se detectó una técnica pública en esta frase: sólo puede
                rechazarse.
              </p>
            ) : null}
            <button
              className="review-submit"
              type="submit"
              disabled={
                busy ||
                (form.action === "approved" && requiresTime && !form.timeKnown)
              }
            >
              {busy ? "Guardando…" : "Agregar decisión inmutable"}
            </button>
          </form>
        ) : (
          <p className="empty">Elegí un candidato.</p>
        )}
      </div>
    </article>
  );
}
