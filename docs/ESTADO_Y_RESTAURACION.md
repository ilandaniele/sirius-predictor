# Estado del repositorio y restauración (2026-11-17)

Este documento deja asentado dónde quedó cada cosa antes de borrar la copia local del proyecto
para ahorrar espacio, y cómo volver a tener todo funcionando.

## 1. Qué está en GitHub

- Repositorio: <https://github.com/ilandaniele/sirius-predictor> (público).
- La rama `agent/v0-2-formats-sirius-archive` estaba completamente pusheada y con el working tree
  limpio. Se mergeó a `master` mediante el PR #1 (merge commit); `master` quedó con todo el
  trabajo, incluido el `model_version` 0.5.0.
- Un `git clone` normal trae la versión vigente. No hace falta indicar ninguna rama.
- La rama `agent/v0-2-formats-sirius-archive` sigue existiendo en GitHub; no se borró.

### Verificación hecha

Se clonó la rama en un directorio limpio, se creó un venv con Python 3.12, se instaló con
`pip install -e ".[dev]"` y se corrió `pytest -m "not slow"`: pasó completo.

No se verificó en el clon limpio: los tests marcados `slow`, el build de la web (`npm ci`,
`npm run build`) ni el arranque con Docker (`INICIAR_SIRIUS.cmd`).

## 2. Qué NO está en Git

`.gitignore` excluye estas rutas, así que **no viajan con el clon**:

| Ruta local | Tamaño aprox. | Contenido |
| --- | --- | --- |
| `storage/` | 155 MB, ~1.740 archivos | predicciones append-only, snapshots de fuentes, informes, release-acceptance, backtests, sirius-review, update-events y `outbox/` (ZIPs de corridas locales, ~111 MB) |
| `state/` | 13 MB, 42 archivos | `sirius.db` (SQLite local), snapshots de fuentes (`state/snapshots/`), `validation-v02/` |
| `.env` | pequeño | secretos locales, incluida `SIRIUS_API_KEY` |

Por las reglas del repositorio (snapshots históricos append-only, predicciones con versión y
timestamp), estos datos son evidencia histórica: si se borra la carpeta sin copia, se pierden.

### Backup

Antes de borrar se generó un zip con `storage/`, `state/` y `.env` **fuera del repositorio**:

```text
C:\Users\Ilan\Desktop\Proyectos\sirius-predictor-LOCAL-BACKUP-2026-11-17.zip   (~89 MB)
```

- Contiene `.env` con secretos (`SIRIUS_API_KEY`, contraseña de Postgres). No subirlo a ningún
  lado ni compartirlo.
- Conviene copiarlo a un segundo lugar (disco externo, nube privada) antes de borrar nada, porque
  vive en el mismo disco que el proyecto.
- No se verificó si Fly.io guarda una copia de `state/sirius.db`; el zip es la única copia
  confirmada.

## 3. Restaurar y ejecutar

### Opción A: Windows con Docker Desktop (la más simple)

```powershell
git clone https://github.com/ilandaniele/sirius-predictor.git
cd sirius-predictor
INICIAR_SIRIUS.cmd
```

`INICIAR_SIRIUS.cmd` crea un `.env` nuevo con secretos aleatorios, levanta base de datos, Redis,
migraciones, API, worker y web, y abre <http://localhost:3000>.

### Opción B: sin Docker

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
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

API en `http://localhost:8000`, web en `http://localhost:3000`. Para el cómputo local de
simulaciones se usa Python 3.12 (`SIMULAR_Y_PUBLICAR.cmd` lo instala si falta).

### Recuperar los datos históricos

Después de clonar, **antes** de ejecutar nada:

1. Extraer el zip de backup dentro de la raíz del repo clonado. Quedan `storage/`, `state/` y
   `.env` en su lugar.
2. Usar el `.env` restaurado en lugar de dejar que `INICIAR_SIRIUS.cmd` genere uno nuevo. Así la
   `SIRIUS_API_KEY` sigue coincidiendo con el secreto ya cargado en Fly.io.

Si en cambio se parte de un `.env` nuevo, la próxima corrida de `PUBLICAR_SIRIUS_FLY.cmd`
sincroniza la clave nueva con el secreto `SIRIUS_API_KEY` de Fly.

## 4. Espacio que se puede liberar

Todo lo siguiente se regenera con los comandos de la sección 3:

| Ruta | Tamaño aprox. |
| --- | --- |
| `apps/web/node_modules/` | 311 MB |
| `.venv-sirius-local-py312/` | 284 MB |
| `apps/web/.next/` | 162 MB |
| `.venv-sirius-local/`, `.venv/` | ~10 MB c/u |

`storage/outbox/` (~111 MB) son ZIPs de corridas locales; están incluidos en el backup.

Borrar la carpeta del proyecto es irreversible: verificar el zip de backup antes.

## 5. Publicación en Fly.io

La app publicada es <https://sirius-engine-ilan-2030.fly.dev>. El flujo de publicación y los accesos
rápidos (`PUBLICAR_SIRIUS_FLY.cmd`, `SIMULAR_Y_PUBLICAR.cmd`, etc.) están descritos en el
[README](../README.md) y en [`DEPLOYMENT.md`](DEPLOYMENT.md). Requieren `flyctl` autenticado.
