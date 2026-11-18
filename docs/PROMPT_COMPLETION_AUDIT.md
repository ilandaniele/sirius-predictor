# Auditoría de cumplimiento de los prompts

Fecha de auditoría: 2026-08-20. Esta matriz usa código, tests y artefactos ejecutables como
evidencia. `Completo` no significa que los supuestos 2030 sean oficiales; significa que el contrato
solicitado está implementado y etiquetado. `Parcial` identifica trabajo real pendiente y no se
presenta como terminado.

| Prompt | Estado | Evidencia actual | Faltante verificable |
|---|---|---|---|
| 0. Auditoría inicial | Completo | `docs/ARCHITECTURE.md`, `docs/IMPROVEMENTS.md`, documentación de límites y riesgos | Mantener esta matriz actualizada |
| 1. Reglas permanentes | Completo | `AGENTS.md`, tests de provenance y hora desconocida | Ninguno conocido |
| 2. Arquitectura | Completo | `apps`, `services`, `packages`, `collectors`, `db`, Docker y CI | Retirar la fachada `engine` sólo cuando deje de ser necesaria |
| 3. Datos y provenance | Completo para v0.2 | 29 tablas SQLAlchemy, cinco migraciones Alembic, claims y predicciones por modo append-only con tests PostgreSQL | Materializar nuevas entidades sólo cuando existan adaptadores oficiales verificables |
| 4. Actualización/scraping | Parcial | snapshots inmutables, precedencia, conflictos, tolerancia a fallos, ranking FIFA JSON aprobado y archivo Sirius | Ranking FIFA permanece observacional para no inventar conversión a Elo; faltan adaptadores oficiales estables para equipos 2030, DT, capitanes, fixtures, sedes y nacimientos |
| 5. Astrología | Parcial | Swiss Ephemeris, cartas inmutables por hash, retornos solar/lunar/demi/cuartilunar con hora real obligatoria, progresiones, armónicas, dignidades, partes, estrellas, antiscias y sensibilidad | Los eclipses quedan como candidatos nodales hasta confirmación astronómica; ampliar cartas patrón independientes |
| 6. Sirius | Completo para evidencia disponible | cuatro capas, modos purist/calibrated, testimonios, contradicciones, confianza y cola append-only; aprobaciones estructuradas generan snapshots que el motor incluye por hash | La cola parte sin aprobaciones porque no deben inventarse testimonios; su cobertura depende de revisión humana real |
| 7. Sorteo | Completo | backtracking, restricciones, seeds, análisis y test de 100.000 sorteos | Sustituir reglas proyectadas cuando FIFA publique 2030 |
| 8. Monte Carlo | Completo para escenarios disponibles | grupos, desempates, eliminatorias, tres modelos, sensibilidad y 100.000 simulaciones | Fechas/rivales específicos por ronda dependen del calendario 2030 oficial |
| 9. Backtesting | Parcial | 2010–2026, cuatro modelos, métricas, calibración temporal y leakage audit | Sólo la señal lunar histórica tiene datos prematch evaluables; las demás ablaciones siguen correctamente como no evaluables |
| 10. Dashboard | Completo para datos disponibles | diez tabs, selector 48/64, polling, fuentes, historia, backtest y flujo Sirius pendiente/aprobado/rechazado con control de concurrencia | La autenticación productiva sigue delegada a la API key configurada |
| 11. Cinco llaves | Completo | exactamente cinco familias; cuadro completo 16vos→campeón en PNG 4K, SVG y PDF (16vos/8vos/cuartos como camino representativo con menor énfasis; semifinales/final/campeón con la densidad Monte Carlo real) y hashes | Ninguno conocido |
| 12. ACTUALIZAR | Completo para inputs disponibles | El botón que encolaba un job Celery fue reemplazado por un flujo de cómputo local verificado: `POST /api/v1/local-simulation-inputs` congela fuentes/inputs en Fly, `scripts/simulate_local_and_publish.py` corre Monte Carlo/llaves/backtest en la PC del operador, y `POST /api/v1/local-simulation-results` (`services/api/local_compute.py`) valida checksums, provenance, leakage y probabilidades antes de publicar en volumen y PostgreSQL. Idempotente y append-only; rechaza bundles alterados, inputs vencidos, código distinto y downgrade automático de fuente A a C/D | Claims sin hora zonificada o contrato completo quedan omitidos de forma trazable hasta validación; no se completan automáticamente |
| 13. Historial | Completo | manifests append-only, commit, versión, timestamp, seed, fuentes, supuestos y resultados | Ninguno conocido |
| 14. Seguridad/calidad | Completo para v0.2 | allow-list SSRF, límites, API key, auditorías, CI backend/frontend/integration | Revisar periódicamente dependencias y TOS |
| 15. Deploy | Completo y verificado en producción | Compose desarrollo/producción, health checks, migraciones, backups y `.env.example`. Alternativa económica en Fly.io: una sola Machine con volumen cifrado (`fly.toml`, `Dockerfile.fly`, `ops/fly/entrypoint.sh`) que empaqueta web/API/PostgreSQL/Redis, escala a cero (modo `suspend`, resume en <1s) y no corre el worker Monte Carlo en producción (`SIRIUS_ALLOW_REMOTE_COMPUTE=false`); lanzadores de un clic en Windows, incluido `SINCRONIZAR_TODO.cmd` (deploy + sync + simulación + publicación en un paso). Desplegado contra la cuenta real del operador en `sirius-engine-ilan-2030.fly.dev`, con al menos una publicación end-to-end verificada (simulación local real → snapshot publicado → servido en vivo) | Monitoreo/alertas productivas quedan fuera del repositorio |

## Hallazgo corregido durante esta auditoría

El parser OpenFootball anterior dejaba marcadores parciales, números de partido y horarios dentro
de los nombres de selecciones. Esto producía, entre otros errores, 169 participantes en 2026 y no
podía reconocer a Argentina como campeón 2022 por penales. Ahora:

- elimina anotaciones de descanso, prórroga y penales sin perder el resultado de la tanda;
- convierte a UTC sólo cuando la fuente incluye un offset explícito;
- deja `kickoff=null` cuando la zona horaria no está demostrada;
- conserva el orden de la fuente para el protocolo prequential;
- exige las formas históricas 64/32 y 104/48, rondas completas y una final decisiva;
- no inventa un ranking pretorneo Sirius cuando no existe un forecast congelado.

## Orden de trabajo restante

1. Completar y probar las técnicas astrológicas faltantes sin conectarlas a un score arbitrario.
2. Implementar adaptadores oficiales versionados de fútbol a medida que sus contratos sean
   verificables; hasta entonces conservar snapshots observacionales.
3. Ampliar el backtest sólo con predicciones y datos prematch congelados, nunca reconstruidos a
   posteriori.

## Adenda 2026-08-21: revisión del flujo Fly + cómputo local

El trabajo de despliegue en Fly.io y cómputo local (fila 12 y 15) llegó a esta sesión sin commitear.
Antes de darlo por cerrado se ejecutó una revisión de código (7 hallazgos independientes) y se
corrigieron nueve problemas reales, todos verificados con la suite completa después de cada cambio:

- `services/api/update_pipeline.py`: `_git_commit`/`_git_state` ya no confunden un fallo transitorio
  de `git` con un árbol de trabajo limpio (sólo `FileNotFoundError` cae al valor `"unavailable"`);
  se alineó además el chequeo de `SIRIUS_GIT_DIRTY` con el de `SIRIUS_GIT_COMMIT`. Esto protege la
  garantía anti-manipulación de la que depende todo el flujo de cómputo local.
- `services/api/main.py`: `local_simulation_result` movió `import_local_result` a un threadpool
  (`run_in_threadpool`) para no bloquear el loop de eventos durante la verificación de imágenes y
  la persistencia SQL.
- `services/api/local_compute.py`: se valida el `rank` de cada llave antes de indexar los archivos
  verificados (evita un `KeyError` no controlado) y `LocalInputStore.append` ya no puede fallar por
  una carrera en `mkdir`.
- `scripts/simulate_local_and_publish.py`: si se omite `--workers` en una máquina con más de 64
  núcleos, ahora se aplica el mismo tope que exige el servidor en vez de correr una simulación
  completa que el servidor iba a rechazar igual.
- `packages/common/config.py`: `SIRIUS_ROOT` vacío ya no resuelve silenciosamente al directorio de
  trabajo actual.
- Limpieza: `.gitignore` sumó `*.tsbuildinfo`; se corrigió un mensaje de error que decía Python 3.13
  en vez de 3.12; se eliminaron `apps/web/src/app/api/update/route.ts` y las funciones
  `job`/`update`/`JobStatus` del cliente frontend, huérfanas desde que el botón ACTUALIZAR fue
  reemplazado por SIMULAR EN MI PC.

Verificación ejecutada: 148 tests Python (`pytest -m "not slow"`), ESLint, `tsc --noEmit`, Vitest, y
Playwright end-to-end contra un servidor de desarrollo aislado (el stack Docker existente en el
puerto 3000 servía código previamente publicado y no debe usarse para verificar cambios locales).
Todo en verde.

Deuda técnica identificada pero no resuelta en esta revisión (no son bugs, son mejoras de
mantenibilidad; ver hallazgos completos en el historial de la sesión): helpers de escritura atómica
duplicados entre `PredictionArchive`, `tasks.py` y `local_compute.py`; geometría de llaves
recalculada varias veces por exportación; símbolos con prefijo `_` de `update_pipeline.py`
compartidos como API implícita entre tres módulos. Ninguno afecta corrección hoy.

Este trabajo fue commiteado y pusheado a `agent/v0-2-formats-sirius-archive` (4 commits) tras
confirmación explícita del operador, y desplegado contra la cuenta real de Fly.

## Adenda 2026-08-22: primer deploy real, bugs encontrados en producción y auditoría de sesgo

El primer deploy contra la cuenta real de Fly y la primera publicación end-to-end (simulación local
completa → subida → validación en el servidor) expusieron dos bugs que ninguna suite de tests local
podía atrapar, porque dependían de estado ya persistido en la base de datos de producción:

- El `run_id` del Monte Carlo no incluía la versión del modelo: un cambio de código que alteraba la
  forma del resultado (por ejemplo, agregar `sirius_application`) colisionaba con una fila ya
  publicada bajo el mismo seed/escenario en vez de convivir como una versión nueva
  (`packages/montecarlo/runner.py`, `engine/sim.py`).
- `SimulationRun` exigía que el `prediction_snapshot_id` coincidiera exactamente con el snapshot
  nuevo, pero un re-sync que sólo refresca `consulted_at` de las fuentes genera un `snapshot_id`
  distinto reutilizando el mismo cálculo Monte Carlo — se comparó byte a byte contra lo guardado en
  Postgres (vía `flyctl ssh console` + `psql`) para confirmar que los datos eran idénticos antes de
  relajar el chequeo (`db/predictions.py`, con test de regresión).

Además, dos hallazgos de UX en vivo: `X-Frame-Options: DENY` global impedía que el `<object>` del
dashboard embebiera el SVG de las llaves (se acotó a `SAMEORIGIN` sólo para esa ruta), y
`Content-Disposition: attachment` forzaba una descarga en vez de mostrar la imagen inline.

Se rediseñó el cuadro de llaves como árbol de dos lados (16vos convergiendo desde cada borde hacia
semifinales/final/campeón centrado) reemplazando el diseño de una sola tira; se cambió
`auto_stop_machines` a `suspend` (resume en cientos de milisegundos en vez de un boot completo,
verificado con dos suspensiones manuales reales) y se paralelizó el arranque de Postgres/Redis en
`ops/fly/entrypoint.sh`.

Auditoría de sesgo pedida explícitamente por el operador ("no te subjetives porque soy argentino"):
se verificó empíricamente que `sirius_index`/`sirius_confidence` de `data/teams.csv` no afectan
ninguna predicción real (HYBRID = FOOTBALL_ONLY exacto), pero Argentina tenía el valor más alto de
los 64 equipos en ambos campos sin ninguna fuente que lo justificara — se llevaron a cero para todos
los equipos. Ver `docs/DATA_CONTRACT.md`.
