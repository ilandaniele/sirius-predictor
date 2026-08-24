# Astrología Argumental — segunda fuente, resumen conciso

Generado 2026-08-23. Investigación pedida por el usuario: buscar otro astrólogo argentino
reconocido ("Astrología Argumental"), revisar en Instagram/TikTok/X qué técnicas usa realmente,
y agregar eso como un **análisis separado** (no mezclado con Sirius), en su propia pestaña.

## Quién es y qué se investigó

**Santiago Rodríguez Spuch** (`@AstroArgumental` en X, `@astrologia.argumental` en Instagram,
`@astrologiaargumental` en TikTok), autor de *"Astrología Argumental: el arte de elegir el mejor
momento"*. Mantiene un blog público en Blogger (`astrologiaargumental.blogspot.com`, 40 posts
totales al momento de la captura) con el mismo formato de feed JSON paginado que ya usábamos para
Sirius — se capturó el corpus completo igual que con Sirius, sin inventar nada.

Se identificaron sus técnicas reales contando menciones explícitas en los 40 posts (no
suposiciones): **método Frawley** (22 menciones — su técnica insignia, análisis horario/tradicional
de la "carta eventual" del partido mediante significadores planetarios y aspectos aplicativos vs.
separativos), regentes de casa (108), ascendente/medio cielo (152+27), tránsitos (73), aspectos
(conjunción/cuadratura/trígono/oposición/sextil, 200+), progresiones y direcciones (60+, incluye
direcciones secundarias como "Neptuno direccionado en la carta de Argentina"), nodos lunares (35),
dignidades esenciales (26), astrología electiva y domificación (su especialidad declarada),
sinastría, estrellas fijas, retrogradación y astrología mundana.

## Qué lo distingue de Sirius

Sirius combina **múltiples cartas natales** (país, federación, ciclo del DT, capitán) en una
lectura descriptiva. Astrología Argumental es principalmente **horaria/electiva**: genera una
carta del evento (fecha/hora/lugar exactos del partido) y juzga el resultado por los
significadores de cada equipo y sus aspectos — el método Frawley es una técnica real y específica
de astrología tradicional (John Frawley), no algo inventado para este proyecto. Hay overlap
parcial (tránsitos, dignidades, progresiones, nodos, estrellas fijas ya existen en
`data/sirius_rules.yaml`), pero se catalogaron con IDs propios en `data/argumental_rules.yaml`
porque se aplican de forma distinta (carta evento vs. cartas natales combinadas).

## Cómo se integró (arquitectura, no un mockup)

La cola de revisión de Sirius (`packages/sirius/review.py`) ya era casi source-agnostic a nivel de
esquema (`SiriusReviewCandidate.source_id` es un `String` libre, sin FK). Se generalizó
(`source_id`, `parse_archive_index` inyectables) y se reutilizó tal cual para la segunda fuente,
en vez de duplicar la clase. Igual patrón para el endpoint de assessments
(`build_sirius_assessments` ya soportaba fusionar un archivo adicional de observaciones revisadas;
se extendió a una lista para poder fusionar Sirius + Argumental en un tercer cálculo "combinado").

- Nuevo collector real: `collectors/argumental_archive/` (mismo patrón Blogger que Sirius).
- Nuevo catálogo de técnicas: `data/argumental_rules.yaml`.
- Nueva fuente en `data/sources.yaml` (`argumental_blog`), recolectada por el mismo pipeline
  `ACTUALIZAR` que ya corría para Sirius.
- Cola de revisión humana propia (append-only, misma UI genérica `AstroReviewQueue.tsx`).
- Endpoints nuevos: `/api/v1/argumental/*` (espejo de `/api/v1/sirius/*`) y
  `/api/v1/astrology/combined-assessment` (cálculo descriptivo en vivo: Sirius solo, Argumental
  solo, y combinado).

## Decisión explícita: no se conecta al Monte Carlo

`SIRIUS_ONLY` e `HYBRID` siguen dependiendo únicamente de la evidencia de Sirius, igual que antes.
La evidencia de Argumental **no** ajusta el Elo ni las probabilidades simuladas — el nuevo análisis
es puramente descriptivo/comparativo (índices de recorrido y coronación calculados con el mismo
motor `SiriusEngine`, pero sin tocar `engine/model.py`). Motivo: enchufar una segunda fuente al
Monte Carlo real habría exigido reabrir el cálculo de `run_id`/`snapshot_id` que tuvo dos bugs
serios esta misma sesión (colisión de hash, mismatch de snapshot) — un cambio de alto riesgo para
una fuente todavía sin evidencia humana revisada. Si en el futuro se quiere que Argumental también
mueva el Monte Carlo, es un paso adicional explícito, no algo que quedó "a medias" por descuido.

## Qué falta (a propósito, no por omisión)

Sin observaciones revisadas todavía (la cola arranca vacía, igual que Sirius arrancó vacía). El
primer paso real es correr `ACTUALIZAR` para que el collector capture el archivo, y después un
revisor humano tiene que aprobar observaciones específicas en la pestaña Astrología antes de que
el índice de Argumental muestre algo distinto de "Sin evidencia".
