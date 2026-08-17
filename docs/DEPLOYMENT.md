# Deployment

## Desarrollo local

1. Copiar `.env.example` a `.env` y reemplazar todas las credenciales.
2. Ejecutar `docker compose up --build`.
3. Abrir `http://localhost:3000`; la documentación de la API queda en
   `http://localhost:8000/docs` sólo fuera de producción.

El servicio `migrate` debe terminar correctamente antes de iniciar API y worker. No se ejecutan
migraciones implícitas durante el arranque de la aplicación.

El worker usa pool Celery `solo`: cada tarea Monte Carlo controla su propio pool de procesos. No
debe cambiarse a prefork sin desactivar primero la paralelización interna.

## Producción

Validar CI y luego ejecutar:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml config
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

El override productivo no publica API, PostgreSQL, Redis ni web directamente: deben quedar detrás
de un ingress TLS con autenticación/rate limit global. `SIRIUS_API_KEY`, `POSTGRES_PASSWORD` y
`SIRIUS_CORS_ORIGINS` son obligatorios y deben venir de un secret manager.

La red del worker debe aplicar egress allow-list para los hosts declarados en `data/sources.yaml`
y bloquear rangos privados, metadata cloud y DNS internos. La validación de aplicación es defensa
en profundidad, no sustituye ese control frente a DNS rebinding.

## Backups y restauración

El perfil `backup` conserva dumps PostgreSQL comprimidos en un volumen separado y elimina sólo los
que exceden la retención configurada. Hay que copiar ese volumen a almacenamiento externo cifrado
y probar restauraciones periódicamente. Para restaurar, detener escrituras, crear una base vacía y
usar `gunzip -c backup.sql.gz | psql`; después ejecutar `alembic upgrade head` y los smoke tests.

Los assets y PredictionSnapshots viven en `report_storage`. Su backup es independiente del dump SQL
y debe preservar rutas y hashes SHA-256.
