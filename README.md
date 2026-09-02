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
- Cristian "Cuti" Romero es el capitán proyectado de Argentina por decisión de escenario; no se presenta
  como designación oficial. Messi queda conservado sólo como dato histórico tras su retiro.

Participantes, rankings, bombos, cuadro, sedes, horarios, DT y capitanes son proyecciones o datos
versionados hasta que fuentes oficiales los confirmen.

## Arquitectura

```text
apps/web          Next.js + TypeScript
services/api      FastAPI + intercambio de cómputo local; Celery sólo para desarrollo
packages          football / astrology / sirius / montecarlo / reports / common
collectors        FIFA / federaciones / históricos / natal / archivo Sirius
db                SQLAlchemy (29 tablas)
alembic           migraciones controladas
storage           snapshots, predicciones, informes y llaves (fuera de Git)
```

PostgreSQL es la persistencia de producción y el almacenamiento append-only
conserva cada predicción junto a hashes, fuentes, commit, estado/digest del árbol de trabajo,
versión, timestamp, semilla y pesos.

## Desarrollo sin Docker

### Windows: un doble clic

Con Docker Desktop instalado, ejecutar [`INICIAR_SIRIUS.cmd`](INICIAR_SIRIUS.cmd). El iniciador:

- abre Docker Desktop si todavía no está activo;
- crea `.env` la primera vez con secretos aleatorios, sin mostrarlos ni subirlos a Git;
- construye e inicia base de datos, Redis, migraciones, API, worker y web;
- espera a que la aplicación esté saludable y abre `http://localhost:3000`.

Los contenedores usan `restart: unless-stopped`. Para iniciar también Docker y Sirius al entrar a
Windows, ejecutar una vez [`INSTALAR_AUTOINICIO_SIRIUS.cmd`](INSTALAR_AUTOINICIO_SIRIUS.cmd). La
configuración es por usuario, no requiere guardar contraseñas de Windows y se revierte con
[`QUITAR_AUTOINICIO_SIRIUS.cmd`](QUITAR_AUTOINICIO_SIRIUS.cmd).

Para consultar o detener la instalación sin borrar los datos:

```text
VER_ESTADO_SIRIUS.cmd
DETENER_SIRIUS.cmd
```

### Inicio manual

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

Para probar los endpoints Celery de cómputo remoto sólo en desarrollo, Redis debe estar disponible
en `localhost:6379`. Iniciar además el worker en otra terminal, desde la raíz del repositorio:

```bash
celery -A services.api.tasks:celery_app worker --loglevel=INFO --pool=solo --concurrency=1
```

En Windows, Redis puede ejecutarse con Docker sin levantar el resto de los servicios:

```bash
docker compose up -d redis
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

## Fly.io: publicado y con escala a cero

El despliegue económico usa una sola Fly Machine y un volumen cifrado. Web, API, PostgreSQL,
snapshots e imágenes permanecen juntos para conservar las rutas y hashes append-only. El worker
Monte Carlo no se inicia en producción: el cómputo pesado se hace localmente. No depende de una
base administrada paga.

Con `flyctl` autenticado, hacer doble clic en [`PUBLICAR_SIRIUS_FLY.cmd`](PUBLICAR_SIRIUS_FLY.cmd).
El script crea la app y el volumen si faltan, sincroniza una clave local `.env` con el secreto
cifrado `SIRIUS_API_KEY`, valida `fly.toml`, publica una sola máquina y muestra la URL:

```text
https://sirius-engine-ilan-2030.fly.dev
```

La máquina se detiene automáticamente cuando no recibe tráfico y despierta con la siguiente
visita. El primer acceso puede tardar algunos segundos. Una simulación local despierta Fly sólo
para congelar inputs y para validar/publicar el bundle final.

Accesos rápidos:

```text
ABRIR_SIRIUS_FLY.cmd
ESTADO_SIRIUS_FLY.cmd
PAUSAR_SIRIUS_FLY.cmd
REANUDAR_SIRIUS_FLY.cmd
LOGS_SIRIUS_FLY.cmd
```

Escala a cero elimina el cargo de CPU/RAM mientras la Machine está detenida, pero no convierte
el servicio en costo cero: el volumen de 5 GB sigue provisionado. Fly cobra el volumen según su
tarifa vigente y conserva snapshots automáticos por siete días. Fuente oficial A consultada el
2026-08-20: [precios de recursos de Fly.io](https://fly.io/docs/about/pricing/).

Esta modalidad prioriza costo bajo sobre alta disponibilidad: existe una sola Machine y un solo
volumen en São Paulo. `PUBLICAR_SIRIUS_FLY.cmd` puede ejecutarse nuevamente para actualizar el
código sin reescribir los datos persistentes.

## Simular localmente y publicar sólo resultados

Éste es el flujo de producción recomendado. Primero publicar el código con
[`PUBLICAR_SIRIUS_FLY.cmd`](PUBLICAR_SIRIUS_FLY.cmd). Después, para el formato predeterminado de
64 equipos, hacer doble clic en:

```text
SIMULAR_Y_PUBLICAR.cmd
```

Para el formato alternativo de 48 equipos:

```text
SIMULAR_Y_PUBLICAR_48.cmd
```

La primera ejecución instala Python 3.12 si hace falta, crea `.venv-sirius-local-py312` e instala Swiss
Ephemeris y las demás dependencias. El comando usa por defecto 100.000 iteraciones y todos los
núcleos menos uno. No hace falta mantener el dashboard abierto.
Para cambiar parámetros desde PowerShell:

```powershell
scripts\windows\simulate-and-publish.ps1 -FormatSize 64 -Iterations 250000 -Workers 12
```

El flujo completo es:

1. Fly consulta y guarda las fuentes, aplica la cola de revisión y congela un input inmutable.
2. La PC comprueba que commit, árbol de trabajo, escenario, equipos y observaciones Sirius sean
   exactamente los mismos que en Fly.
3. La PC ejecuta primero `HYBRID` y declara si Sirius está activo o neutral según la evidencia
   revisada; nunca confunde la ausencia de evidencia con una señal Sirius.
4. Inmediatamente genera cinco escenarios decisivos —dos semifinales, final y campeón— en PNG 4K,
   SVG y PDF.
5. Después ejecuta `FOOTBALL_ONLY`, `SIRIUS_ONLY` y el backtesting como controles separados.
6. Cada intento queda visible bajo `storage/outbox/runs/<corrida>/`, con `status.json` e imágenes
   recuperables incluso si falla una etapa posterior. El ZIP final queda en `storage/outbox/`.
7. Fly verifica tamaño, rutas del ZIP, checksums, provenance, leakage, probabilidades, sensibilidad,
   assets, versión y antigüedad del input antes de publicar en volumen y PostgreSQL.

La importación es idempotente y append-only. Rechaza bundles alterados, inputs anteriores a la
predicción vigente, código distinto y reemplazos automáticos de una fuente A por C/D. Los ZIP de
`storage/outbox/` quedan como copia local recuperable y no se suben a Git.

También se puede ejecutar el comando Python directamente o generar el ZIP sin subirlo:

```powershell
python scripts/simulate_local_and_publish.py --format-size 64 --iterations 100000
python scripts/simulate_local_and_publish.py --format-size 48 --iterations 100000 --no-upload
```

Para probar el flujo sin publicar, también se puede pasar el parámetro al acceso directo:

```powershell
SIMULAR_Y_PUBLICAR.cmd -Iterations 1000 -NoUpload
```

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
exportación de cinco escenarios decisivos en PNG 4K, SVG y PDF. Guarda el bundle trazable bajo
`storage/release-acceptance/`.

Para diagnosticar el pipeline completo sin intercambio con Fly, sólo en desarrollo local:

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

La preparación remota del cómputo local captura el feed paginado completo de Juan Cruz Sirius desde
la primera publicación disponible, conserva hashes y provenance, detecta menciones técnicas y manda
toda interpretación a revisión. El tab **Sirius** permite sincronizar la cola y agregar decisiones
humanas append-only.
Una aprobación exige equipo, técnica detectada, polaridad, fuerza descriptiva, confianza del dato y
control de hora real. Las observaciones aprobadas se exportan a snapshots inmutables bajo
`storage/sirius-review/` y entran al motor recién en la siguiente simulación local; rechazar o
revertir una aprobación crea otra decisión, nunca reescribe la anterior.

Para poblar la cola desde el último archivo ya capturado sin volver a consultar Internet:

```bash
python -m alembic upgrade head
python scripts/sync_sirius_review.py
```

`data/sirius_observations.yaml` sigue disponible para evidencia revisada y versionada en Git. La
cola SQL es la vía operativa; ambas exigen `manually_confirmed=true`. Si no hay evidencia, el ajuste
es neutral y el dashboard lo declara. En producción, las decisiones requieren `SIRIUS_API_KEY`; el
campo del dashboard vive sólo en memoria del navegador y no persiste la clave.

El mismo pipeline recalcula únicamente cartas afectadas por claims aceptados. La caché inmutable
usa el hash de todos los inputs y de la versión de efemérides: una repetición es un `cache_hit` y un
cambio crea una carta nueva. El informe y el manifest separan solicitudes, recálculos, aciertos,
omisiones y fallos. Una hora sin zona o desconocida nunca dispara este cálculo; debe pasar por el
análisis explícito de sensibilidad.

El ranking masculino se captura desde el endpoint JSON oficial que utiliza la página pública de
FIFA. El adapter consulta el calendario, elige exclusivamente la publicación aprobada más reciente,
rechaza respuestas parciales y guarda las respuestas y sus hashes. Es evidencia observacional:
los puntos FIFA no se convierten a Elo ni a bombos 2030 hasta definir y validar públicamente esa
transformación.

Los claims de los collectors se guardan además en SQL como eventos append-only. Un fingerprint
deduplica observaciones idénticas sin usar la nueva hora de consulta; cada fila congela URL,
calidad y fecha. El `update-event` informa cuántos claims fueron insertados, deduplicados, elegibles
o enviados a revisión, sin desactivar evidencia anterior.

Cada manifest de predicción se replica en PostgreSQL/SQLite como un `PredictionSnapshot` y un
`SimulationRun` por modo. Las claves `(snapshot_id, mode)` y `run_id` hacen el replay idempotente;
si el archivo existe pero faltan filas SQL, la siguiente ejecución las reconstruye desde el
manifest inmutable. La versión relacional del modelo combina la versión semántica y el hash del
estado de código, sin mezclar los resultados de los tres modos.

## Contratos y límites

- Cada dato externo guarda fuente, URL, consulta y calidad A/B/C/D/X.
- Una fuente A nunca se reemplaza automáticamente por C/D.
- Horas natales desconocidas permanecen nulas; no se usa 12:00 ni casas/ASC/MC.
- Los snapshots dudosos van a revisión humana.
- Ninguna calibración modifica predicciones históricas.
- Técnicas Sirius sin datos prematch se marcan no evaluables en el backtest.

Más información: [arquitectura](docs/ARCHITECTURE.md),
[auditoría de prompts](docs/PROMPT_COMPLETION_AUDIT.md),
[contrato de datos](docs/DATA_CONTRACT.md), [metodología](docs/METHODOLOGY.md) y
[auditoría de seguridad](docs/SECURITY_AUDIT.md).
