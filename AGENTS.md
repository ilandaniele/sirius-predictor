# Reglas permanentes del repositorio

Estas reglas aplican a todo el repositorio y a cualquier agente o colaborador que trabaje en él.

1. No inventar datos faltantes.
2. Todo dato externo debe guardar fuente, URL, fecha de consulta y calidad A/B/C/D/X.
3. Nunca tratar una hora natal desconocida como 12:00.
4. Si falta hora, no usar ASC/MC/casas salvo análisis de sensibilidad horaria explícito.
5. Separar fuerza del modelo y calidad de datos.
6. Mantener modelos `FOOTBALL_ONLY`, `SIRIUS_ONLY` y `HYBRID` separados.
7. Guardar snapshots históricos de cada actualización.
8. Toda predicción debe guardar versión de modelo y timestamp.
9. Ningún cambio de pesos puede reescribir predicciones pasadas.
10. Tests obligatorios para sorteo, efemérides, simulaciones y parsers.
11. Datos dudosos obtenidos mediante scraping no se integran automáticamente sin validación.
12. Una fuente A nunca puede ser reemplazada automáticamente por una C/D.
