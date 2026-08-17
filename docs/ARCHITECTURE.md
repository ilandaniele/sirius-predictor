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
                 ▼
 packages/montecarlo ── tres modos separados
                 │
       ┌─────────┴──────────┐
       ▼                    ▼
PredictionSnapshot    packages/reports
 PostgreSQL + storage  cinco llaves + informe
       │                    │
       └─────────┬──────────┘
                 ▼
       FastAPI ◄── Celery/Redis ──► Next.js
```

## Límites de módulo

- `apps/web`: presentación y provenance; no contiene reglas del torneo.
- `services/api`: contratos HTTP, autenticación, jobs y orquestación idempotente.
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
3. Mantener C/D/X o conflictos en revisión.
4. Recalcular sólo cartas afectadas.
5. Recalcular testimonios Sirius.
6. Ejecutar Monte Carlo por modo.
7. crear `PredictionSnapshot` append-only.
8. comparar con el snapshot anterior.
9. generar informe y exactamente cinco llaves.
10. registrar notificación local.

El hash idempotente excluye timestamps de consulta e incluye hashes efectivos. Si una descarga
falla, se conserva el hash válido anterior y no se crea una predicción espuria.
Los snapshots remotos que todavía no producen claims se conservan como evidencia observacional,
pero sus bytes dinámicos no invalidan una predicción hasta que un parser integre un dato al modelo.

## Reproducibilidad

Cada salida registra commit, versión, timestamp, hashes de fuente, supuestos, semilla, número de
simulaciones, modo y pesos. La paralelización usa semillas de chunk derivadas y registra el número
de workers. Los archivos históricos son write-once; sólo el puntero `latest` es mutable.
