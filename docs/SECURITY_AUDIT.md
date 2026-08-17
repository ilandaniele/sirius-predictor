# Auditoría de seguridad y calidad — v0.1.0

Fecha: 2026-08-17.

## Controles implementados

- Secretos sólo por variables de entorno; `.env` está ignorado y producción exige API key.
- Endpoints de mutación requieren `X-API-Key` en producción.
- CORS allow-list, cuerpo POST máximo de 1 MiB y rate limit local.
- Collectors sólo HTTPS, hosts explícitos, puerto 443, sin credenciales, redirects desactivados,
  proxy de entorno desactivado, validación DNS pública previa, timeout, límite de 5 MiB y pausa
  entre solicitudes.
- TOS/robots quedan registrados por fuente; no hay bypass con navegador.
- SQLAlchemy parametriza consultas; no se construye SQL con entradas HTTP.
- React escapa valores; exportación SVG aplica escape HTML.
- IDs de snapshot aceptan exclusivamente SHA-256 lowercase antes de resolver rutas.
- Snapshots/predicciones son append-only y atómicos; una fuente caída conserva el último hash.
- Errores de collectors se aíslan y no incluyen payloads o secretos en la respuesta.
- Imágenes Docker ejecutan como usuario no root; bases/Redis no se publican en producción.
- Logs Docker rotan; backups usan permisos restrictivos y volumen separado.
- CI exige Ruff, mypy, pytest, integración, migraciones, frontend, Playwright y auditorías.

## Riesgos residuales

- El rate limit de proceso debe duplicarse en el ingress/Redis para múltiples réplicas.
- La API key única debe reemplazarse por identidad/roles si hay múltiples operadores.
- `engine/updates.py` y `app.py` son compatibilidad legacy; Streamlit usa HTML controlado y no se
  incluye en las imágenes productivas.
- Los adaptadores futuros requieren revisión individual de robots, TOS, licencia y estabilidad.
- La validación DNS reduce SSRF por resolución privada, pero el cierre total de DNS rebinding exige
  egress de red/allow-list en infraestructura; está requerido en la guía de producción.
- Dependencias Python usan rangos compatibles; CI audita, pero un lock reproducible por plataforma
  sigue recomendado antes de un despliegue público.
- Los backups necesitan copia externa cifrada y simulacros de restauración.
- No se prepara despliegue si cualquier job obligatorio de CI falla.

## Revisión de performance

- Sorteos masivos usan una cadena de swaps válidos luego del backtracking inicial.
- Monte Carlo se divide en procesos y agrega masa probabilística con verificación.
- Jobs largos se ejecutan en Celery con límite de una hora y prefetch uno.
- API no ejecuta 100.000 torneos dentro del request HTTP.
