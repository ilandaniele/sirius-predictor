# Changelog

## 0.2.1 — 2026-08-20

- Caché astrológica persistente y append-only por hash de inputs/efemérides; el pipeline informa
  recálculos, aciertos, omisiones y fallos reales y rechaza horas desconocidas o sin zona.
- Adapter del ranking FIFA sobre el JSON oficial: selecciona sólo publicaciones aprobadas, conserva
  respuestas/hashes, rechaza parciales o schema drift y no inventa una conversión a Elo.
- Cola Sirius persistente y append-only: candidatos separados de decisiones humanas, control de
  concurrencia, guardas de hora desconocida y snapshot revisado conectado al hash de simulación.
- Dashboard de revisión pendiente/aprobada/rechazada; ninguna coincidencia scraped entra sola al
  modelo y toda reversión conserva la decisión anterior.
- Técnicas dependientes de hora exigen provenance horario independiente; manifests y run IDs
  incorporan hashes de ambas fuentes Sirius y el digest del árbol Git si está sucio.
- Parser histórico estricto: nombres limpios, offsets UTC explícitos, prórrogas, penales, rondas y
  formas 64/32 o 104/48 validadas antes del backtest.
- Campeón 2022 reconocido por tanda; rankings pretorneo Sirius no evaluables y empates de rating
  informados como intervalos en lugar de puestos arbitrarios.
- Acceptance ampliado para fallar ante corrupción histórica, campeones ausentes o rankings
  inventados.
- Armónicas descriptivas, dignidades accidentales y partes arábigas configurables sin pesos Sirius.
- Lunaciones cercanas a nodos etiquetadas sólo como candidatos de eclipse pendientes de
  confirmación astronómica.
- Matriz honesta de cumplimiento y faltantes para todos los prompts.

## 0.2.0 — 2026-08-17

- Selector 48/64 en API, CLI y dashboard; 64 permanece predeterminado.
- Alternativa 48 con 12 grupos, ocho mejores terceros y cuadro R32 reproducible.
- Collector paginado del archivo Sirius completo desde 2014, con hashes y revisión obligatoria.
- Monte Carlo conectado al motor Sirius estructurado mediante observaciones confirmadas; faltantes
  neutrales y priors X excluidos de producción.
- Galería navegable y descargas de las cinco llaves PNG/SVG/PDF.
- Estado de jobs consultable y polling del botón ACTUALIZAR.
- Restricción de hora natal compatible con PostgreSQL.

## 0.1.0 — 2026-08-17

- Monorepo Next.js/FastAPI con PostgreSQL, Alembic, Redis y Celery.
- Modelo de 27 entidades y claims con provenance/calidad A/B/C/D/X.
- Collectors aislados, snapshots por contenido, precedencia y revisión de conflictos.
- Motor astrológico Swiss Ephemeris con guardias de hora y sensibilidad explícita.
- Sirius purista/calibrable con testimonios, contradicciones, robustez y confianza separada.
- Sorteo 64 equipos por backtracking y cadena de swaps reproducible.
- Modelos `FOOTBALL_ONLY`, `SIRIUS_ONLY` y `HYBRID` separados.
- Monte Carlo multiproceso, camino de Argentina y cinco familias de llave.
- Backtesting 2010–2026 sin fuga temporal, métricas, calibración rodante y ablaciones.
- Dashboard con diez áreas y provenance navegable.
- Cinco llaves programáticas exportables en PNG 4K, SVG y PDF.
- Botón de actualización idempotente y PredictionSnapshots append-only.
- CI backend/frontend/integración/migraciones/e2e y auditoría de dependencias.
- Docker Compose desarrollo/producción, health checks, logs y backups PostgreSQL.

## Pendiente posterior a 0.1.0

- Sustituir proyecciones por el campo, bombos, cuadro y calendario oficiales cuando existan.
- Completar adaptadores oficiales de las 64 federaciones y validar licencias/TOS individualmente.
- Congelar más predicciones públicas Sirius prematch para evaluar técnicas hoy no observables.
- Preregistrar y entrenar `SIRIUS_CALIBRATED` sólo con validación temporal anidada.
