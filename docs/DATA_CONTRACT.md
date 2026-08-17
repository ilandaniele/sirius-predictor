# Contrato de datos

## Escenario

`data/scenario.yaml` es la autoridad para el formato hipotético. Debe cumplir:

- 64 equipos = 4 bombos × 16 = 16 grupos × 4.
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

PostgreSQL conserva 27 tablas para equipos/formato/sorteo/fixtures, personas y tenures, datos
natales y fuentes, eventos, cartas/técnicas, versiones, predicciones, simulaciones/caminos y
backtests. `ModelVersion`, `PredictionSnapshot`, `SimulationPath` y `BacktestRun` son append-only.

Una hora natal desconocida es `NULL` con `time_known=false`. La restricción de base impide marcarla
conocida sin hora y zona; el parser impide guardar una hora cuando `time_known=false`.
