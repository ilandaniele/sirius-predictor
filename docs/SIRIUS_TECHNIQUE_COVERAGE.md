# Cobertura de técnicas Sirius — resumen conciso

Generado 2026-08-23 a partir de: `data/sirius_rules.yaml` (26 técnicas documentadas, definidas en
el prompt original del proyecto), el archivo real del blog de Juan Cruz Sirius (741 posts,
2014–2026, ya capturado en `storage/source_snapshots/sirius_blog`), tres artículos de prensa
independiente sobre su predicción 2026, y una búsqueda general de metodología de astrología
deportiva para contrastar con otros practicantes serios del rubro.

## Qué se usó para identificar las técnicas

1. **`data/sirius_rules.yaml`** — la lista canónica de 26 técnicas (estructural/anual/torneo/partido),
   ya definida en `PROMPTS_CODEX_SIRIUS_ENGINE.md` (Prompt 5/6) antes de esta sesión.
2. **El archivo real del blog** — 741 posts capturados, 682 candidatos con texto real extraído.
3. **Investigación web dirigida** — búsquedas específicas sobre su metodología, un artículo donde
   explica en sus propias palabras por qué falló su pronóstico de la final 2026 (le faltaban cartas
   de España), y una revisión general de cómo trabajan otros astrólogos deportivos (casas natales de
   países, tránsitos de jugadores, cartas de fundación de federación) para verificar que el enfoque
   de Sirius (múltiples cartas natales combinadas: país, federación, DT, capitán/referente) es
   consistente con la práctica seria del rubro y no un caso aislado inventado.

## Qué faltaba y se corrigió hoy

El **detector automático** de técnicas (`collectors/sirius_archive/parser.py`) sólo reconocía 13 de
las 26 técnicas documentadas. Esto no es un problema menor: la interfaz de revisión **bloquea el
botón "Aprobar"** cuando no se detecta ninguna técnica (`disabled={!selected.technique_mentions.length}`
en `SiriusReviewQueue.tsx`) — es decir, un revisor humano no podía aprobar una observación válida
que mencionara Proluna, casas I/VII, cuartilunar, armónicas, dignidades/recepciones, regentes,
carta natal del DT, carta del kickoff, minutos críticos o factores sol/luna, aunque la reconociera
perfectamente leyendo el texto. Se agregaron patrones para las 12 técnicas faltantes y se verificó
con 13 tests nuevos (`tests/unit/test_sirius_archive.py`).

| Cobertura antes | Cobertura ahora |
|---|---|
| 13 / 26 técnicas detectables | 24 / 26 (ver nota) |

No se agregó detección específica para `match_arabic_parts` (usa el mismo patrón que
`arabic_parts`; el revisor humano decide la capa/layer correcta al estructurar la observación) ni
para `extra_time_penalties` (es una característica del resultado del partido, no una técnica que se
"menciona" en un texto).

## Qué NO se encontró — y no se inventó

La investigación no encontró ninguna técnica pública que Sirius use y que no estuviera ya en
`data/sirius_rules.yaml`. Su metodología declarada (4-6 cartas natales combinadas: debut mundialista
1930, AFA, ciclo del DT, capitán de cada escenario) es estable en el tiempo — se repite igual en
las campañas
2018, 2022 y 2026 revisadas. No se agregó ninguna técnica nueva al archivo de reglas porque no hay
evidencia de que exista una; agregar una "por las dudas" violaría la regla del proyecto de no
inventar datos.

## Precisión del detector — advertencia honesta

Los patrones nuevos son heurísticas de texto (regex), no comprensión semántica. Términos como
"regentes", "casa 7" o "modalidad cardinal" pueden aparecer por casualidad en un post que no habla
realmente de esa técnica (el filtro de "deportivo" ya reduce mucho ese ruido, pero no lo elimina).
Esto **no corrompe la evidencia aprobada** — el detector sólo habilita el botón y sugiere una
técnica por defecto; el revisor humano sigue eligiendo la técnica exacta, la polaridad y la
confianza al estructurar cada decisión.
