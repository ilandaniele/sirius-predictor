# Contrato de datos

## Escenario

`data/scenario.yaml` es la autoridad del formato predeterminado y `data/scenario-48.yaml` de la
alternativa. Deben cumplir:

- 64 equipos = 4 bombos × 16 = 16 grupos × 4.
- 48 equipos = 4 bombos × 12 = 12 grupos × 4; 24 clasificados directos y 8 mejores terceros.
- Un equipo de cada bombo por grupo.
- Dos clasificados por grupo.
- Anfitriones `ESP`, `POR`, `MAR`, `ARG`, `PAR` y `UR` en Bombo 1.
- Máximo dos UEFA y uno de cualquier otra confederación por grupo.
- Final Madrid 21/07/2030; horas 17, 18, 20 y 21; offsets −15, 0 y +15 minutos.

El campo `status: hypothetical_scenario` evita presentar la configuración como confirmación FIFA.

## Equipos

Columnas obligatorias de `data/teams.csv`:

| Campo | Significado |
|---|---|
| `team_id` | ID estable, único y ajeno al nombre visible |
| `team` | Nombre de presentación |
| `confed` | Confederación usada por el sorteo |
| `host`, `pot` | Hipótesis de anfitrión y bombo |
| `projected_elo` | Prior exclusivamente futbolístico |
| `rating_uncertainty` | Incertidumbre del rating, no calidad Sirius |
| `sirius_index` | Prior experimental hipotético entre equipos |
| `sirius_confidence` | Confianza del dato Sirius en `[0,1]` |
| `qualification_status` | `host_assumption` o `projected` |
| `coach`, `captain` | Valores conocidos o `Por definir`; nunca inventar horas natales |
| `source_id`, `as_of` | Procedencia y fecha de corte |

`validate_scenario` detiene la ejecución ante IDs duplicados, bombos incompletos, anfitriones
incorrectos, capacidad imposible de confederación o confianza fuera de rango.

## Procedencia

Cada snapshot registra fuente, URL, fecha/hora, HTTP status, content type, SHA-256, bytes,
ruta relativa, indicador de cambio y error. Los bytes son content-addressed y nunca se sobrescriben.

Cada `SourceClaim` agrega valor JSON, confianza `[0,1]`, indicador oficial, inferido, confirmado
manualmente y estado activo. Las calidades son A (primaria oficial), B (archivo confiable), C
(secundaria), D (pista) y X (supuesto/proyección). C/D/X no entran automáticamente sin confirmación,
y A no puede ser sustituida automáticamente por una calidad inferior.

Cada fila congela también URL y calidad y recibe un fingerprint canónico que excluye únicamente la
fecha de consulta. Reconsultar el mismo dato genera un duplicado trazado en el `update-event`, no
otra fila. Un valor o una procedencia distintos crean un nuevo evento; los anteriores son
inmutables. `active` representa elegibilidad al momento de inserción y no implica que otra evidencia
haya sido borrada o reescrita.

El adapter de ranking FIFA guarda en un único snapshot trazable la respuesta del calendario y la
tabla seleccionada, sus URL y hashes. Sólo admite una entrada `RankingApproved=true`, fecha con
zona, códigos/rangos/puntos válidos, al menos 100 selecciones, códigos únicos y ausencia
de token de continuación. La tabla permanece observacional porque el modelo no presupone una
conversión de puntos FIFA a Elo.

PostgreSQL conserva 29 tablas para equipos/formato/sorteo/fixtures, personas y tenures, datos
natales y fuentes, eventos, cartas/técnicas, versiones, predicciones, simulaciones/caminos y
backtests. `SourceClaim`, `AstrologyChart`, `AstrologyTechniqueResult`, `ModelVersion`,
`PredictionSnapshot`, `SimulationPath`, `BacktestRun` y la cola de revisión Sirius son append-only.

Un manifest genera un `PredictionSnapshot` y un `SimulationRun` independientes por modo. La clave
externa del snapshot SHA-256 más el modo y el `run_id` impiden duplicados. `ModelVersion` conserva
versión semántica, modo, commit y —para árboles no limpios— el hash del working tree dentro de su
feature schema. Un replay valida igualdad completa y falla si SQL diverge del archivo inmutable.

Una hora natal desconocida es `NULL` con `time_known=false`. La restricción de base impide marcarla
conocida sin hora y zona; el parser impide guardar una hora cuando `time_known=false`.
Retornos solar/lunar/demi/cuartilunar y cualquier regla Sirius dependiente de hora exigen ahora
`time_known=true` explícito; la ausencia del campo también falla. La conversión de una técnica a
observación Sirius exige al menos un `source_claim_id`.

## Recálculo y caché de cartas

Cada carta se identifica por un SHA-256 canónico de sujeto, instante UTC, ubicación, conocimiento
de hora, sistema de casas, cuerpos, orbes, proveedor y versión de efemérides. Una entrada idéntica
reutiliza el resultado persistido; cualquier parámetro diferente crea otra fila y nunca modifica la
anterior.

Un claim aceptado de tipo `BirthData`, `Fixture` o `CoachDebutEvent` sólo dispara el cálculo si su
valor contiene un `chart_request` completo: `moment` ISO con offset, `time_known=true`,
`house_system`, `location` explícita o nula y, opcionalmente, `bodies`, `orbs` y `label`. Si la hora
es desconocida, falta la URL o el contrato está incompleto, el manifest registra la omisión. Las
horas desconocidas se estudian únicamente por el flujo separado de sensibilidad horaria.

## Archivo y observaciones Sirius

El collector Blogger recorre todas las páginas del feed y sólo acepta un corpus como completo si el
total capturado coincide con el total declarado por Blogger. Conserva URL canónica, publicación,
consulta, calidad B y hash de contenido. Las frases y técnicas detectadas son candidatos inferidos:
no se integran automáticamente.

`data/sirius_observations.yaml` es el único contrato de observaciones que consume Monte Carlo. Cada
registro exige fuente, URL, consulta, calidad, IDs de claims y confirmación manual. Una técnica que
requiere hora real falla si `time_known` no es verdadero; jamás se completa con 12:00.
