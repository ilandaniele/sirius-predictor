# Mundial 2030 Sirius Engine

Aplicación profesional y actualizable para estudiar **escenarios hipotéticos** de Mundial 2030
con 64 selecciones por defecto o una alternativa de 48. Compara tres modelos independientes:
`FOOTBALL_ONLY`, `SIRIUS_ONLY` y `HYBRID`.

> La astrología no está científicamente validada para predecir resultados deportivos. Sirius se
> implementa como modelo experimental, auditable y siempre comparado con el baseline futbolístico.

## Formatos disponibles

- Predeterminado: 64 selecciones; 4 bombos de 16; grupos A–P; clasifican dos.
- Alternativo: 48 selecciones; 4 bombos de 12; grupos A–L; clasifican dos y los ocho
  mejores terceros, siguiendo la [estructura oficial de 2026](https://inside.fifa.com/organisation/fifa-council/media-releases/fifa-council-approves-international-match-calendars).
  La asignación del cuadro 2030 sigue siendo una proyección explícita.
- España, Portugal, Marruecos, Argentina, Paraguay y Uruguay en Bombo 1.
- Máximo dos UEFA y máximo una selección de cualquier otra confederación por grupo.
- Argentina y España en sectores opuestos como supuesto configurable.
- Final en Madrid el 21/07/2030 a las 18:00; sensibilidad 17/18/20/21 y ±15 minutos.
- Lionel Scaloni continúa con Argentina como supuesto de trabajo, no como hecho futuro.

Participantes, rankings, bombos, cuadro, sedes, horarios, DT y capitanes son proyecciones o datos
versionados hasta que fuentes oficiales los confirmen.

## Arquitectura

```text
apps/web          Next.js + TypeScript
services/api      FastAPI + Celery
packages          football / astrology / sirius / montecarlo / reports / common
collectors        FIFA / federaciones / históricos / natal / archivo Sirius
db                SQLAlchemy (27 tablas)
alembic           migraciones controladas
storage           snapshots, predicciones, informes y llaves (fuera de Git)
```

PostgreSQL es la persistencia de producción, Redis coordina jobs y el almacenamiento append-only
conserva cada predicción junto a hashes, fuentes, commit, versión, timestamp, semilla y pesos.

## Desarrollo sin Docker

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m alembic upgrade head
uvicorn services.api.main:app --reload
```

En otra terminal:

```bash
cd apps/web
npm ci
npm run dev
```

API: `http://localhost:8000`; web: `http://localhost:3000`.

El selector `64 CUPOS / 48 CUPOS` está arriba del dashboard. `64` siempre abre primero.

## Docker Compose

Copiar `.env.example` a `.env`, reemplazar secretos y ejecutar:

```bash
docker compose up --build
```

Las migraciones se ejecutan en un servicio one-shot antes de API/worker. Consultar
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) para producción y backups.

## Verificación

```bash
python -m ruff check .
python -m mypy services packages collectors db
python -m pytest
cd apps/web
npm run lint
npm run test
npm run build
```

El acceptance de release ejecuta 100.000 sorteos y 100.000 torneos; por eso está marcado como
prueba lenta y se corre explícitamente antes de publicar.

```bash
python scripts/release_acceptance.py --iterations 100000
```

El comando ejecuta 100.000 torneos por cada modo (300.000 en total), el backtest temporal y la
exportación de cinco llaves en PNG 4K, SVG y PDF. Guarda el bundle trazable bajo
`storage/release-acceptance/`.

Para crear el `PredictionSnapshot` inicial o ejecutar la misma operación que encola el botón:

```bash
python scripts/update_world_cup.py --iterations 100000 --workers 24
```

Para correr el formato alternativo:

```bash
python scripts/update_world_cup.py --format-size 48 --iterations 100000 --workers 8
python scripts/release_acceptance.py --format-size 48 --iterations 100000 --workers 8
```

Una prueba rápida, útil antes de lanzar 100.000 simulaciones:

```bash
python scripts/update_world_cup.py --format-size 64 --iterations 1000 --workers 1
```

`ACTUALIZAR` captura el feed paginado completo de Juan Cruz Sirius desde la primera publicación
disponible, conserva hashes y provenance, detecta menciones técnicas y manda toda interpretación a
revisión. Sólo observaciones confirmadas en `data/sirius_observations.yaml` afectan a Sirius; si no
hay evidencia, el ajuste es neutral y el dashboard lo declara.

## Contratos y límites

- Cada dato externo guarda fuente, URL, consulta y calidad A/B/C/D/X.
- Una fuente A nunca se reemplaza automáticamente por C/D.
- Horas natales desconocidas permanecen nulas; no se usa 12:00 ni casas/ASC/MC.
- Los snapshots dudosos van a revisión humana.
- Ninguna calibración modifica predicciones históricas.
- Técnicas Sirius sin datos prematch se marcan no evaluables en el backtest.

Más información: [arquitectura](docs/ARCHITECTURE.md),
[contrato de datos](docs/DATA_CONTRACT.md), [metodología](docs/METHODOLOGY.md) y
[auditoría de seguridad](docs/SECURITY_AUDIT.md).
