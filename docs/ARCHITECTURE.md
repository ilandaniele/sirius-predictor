# Arquitectura

```text
Fuentes oficiales / archivos / pistas
                 │
                 ▼
collectors ── allow-list, timeout, rate limit, snapshot SHA-256
                 │
                 ▼
SourceClaim ── normalización, deduplicación, calidad y revisión humana
                 │
       ┌─────────┴──────────┐
       ▼                    ▼
packages/football     packages/astrology
       │                    │
       └─────────┬──────────┘
                 ▼
         packages/sirius
 testimonios + confianza + robustez
                 │
                 │ input congelado y autenticado
                 ▼
 PC local: backtest + packages/montecarlo ── tres modos separados
                 │
       ┌─────────┴──────────┐
       ▼                    ▼
PredictionSnapshot    packages/reports
 PostgreSQL + storage  cinco llaves + informe
       │                    │
       └─────────┬──────────┘
                 ▼
       FastAPI ◄── bundle verificado ──► Next.js
```

## Límites de módulo

- `apps/web`: presentación y provenance; no contiene reglas del torneo.
- `services/api`: contratos HTTP, autenticación, inputs congelados e importación idempotente.
- `packages/common`: configuración, modos, seguridad y precedencia de fuentes.
- `packages/football`: sorteo, baseline, torneo y backtesting.
- `packages/astrology`: efemérides y técnicas deterministas; no decide pesos Sirius.
- `packages/sirius`: transforma observaciones en testimonios e índices descriptivos.
- `packages/montecarlo`: ejecución/aggregación reproducible y paralela.
- `packages/reports`: activos derivados; no contiene ganadores hardcodeados.
- `collectors`: descarga y parseo; una fuente caída no detiene las restantes.
- `db`/`alembic`: esquema relacional y migraciones.
- `engine`: fachada compatible con el prototipo; no forma parte del frontend.

## Flujo de actualización

1. Ejecutar collectors y escribir bytes por SHA-256.
2. Normalizar/deduplicar claims y aplicar precedencia conservadora.
3. Persistir claims append-only con URL/calidad congeladas y mantener C/D/X, inferencias o
   conflictos en revisión.
4. Recalcular sólo cartas con claims aceptados y contrato completo; reutilizar caché por hash para
   entradas idénticas y registrar omisiones sin imputar datos.
5. Congelar fuentes, revisión, escenario, equipos, versión y código en un input local.
6. Ejecutar primero HYBRID y persistir cinco escenarios decisivos visuales; luego ejecutar los modos
   de control y el backtesting en la PC. Los parciales nunca dependen de un directorio temporal.
7. Subir un ZIP con manifest de archivos y checksums; rechazar rutas, formatos o inputs inválidos.
8. Crear el manifest y persistir `PredictionSnapshot`/`SimulationRun` append-only por modo; un
   replay repara filas SQL ausentes y rechaza divergencias.
9. Comparar con el snapshot anterior.
10. Publicar informe, backtest y exactamente cinco visuales de semifinales, final y campeón.
11. Registrar auditoría de importación local.

El hash idempotente excluye timestamps de consulta e incluye hashes efectivos. Si una descarga
falla, se conserva el hash válido anterior y no se crea una predicción espuria.
Los snapshots remotos que todavía no producen claims se conservan como evidencia observacional,
pero sus bytes dinámicos no invalidan una predicción hasta que un parser integre un dato al modelo.
Cada consulta genera además un `update-event` append-only con URL, fecha, calidad, hash y estado,
incluso cuando la predicción resulta ser un replay idempotente.

## Reproducibilidad

Cada salida registra commit, versión, timestamp, hashes de fuente, escenario, equipos, supuestos,
semilla, número de simulaciones, modo y pesos. La paralelización usa semillas de chunk derivadas y
registra el número de workers. Los archivos históricos son write-once; sólo el puntero `latest` es
mutable. Fly no acepta un resultado si el código desplegado cambió después de congelar el input.
