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
| 3. Datos y provenance | Completo para v0.2 | 27 tablas SQLAlchemy, migración Alembic y tests PostgreSQL | Persistir más resultados de collectors cuando existan adaptadores oficiales |
| 4. Actualización/scraping | Parcial | snapshots inmutables, precedencia, conflictos, tolerancia a fallos, parsers y archivo Sirius | Ranking FIFA aún es snapshot observacional; faltan adaptadores oficiales estables para equipos, DT, capitanes, fixtures, sedes y nacimientos |
| 5. Astrología | Parcial | Swiss Ephemeris, cartas, casas guardadas, retornos, progresiones, armónicas, dignidades esenciales/accidentales, partes configurables, estrellas, antiscias y sensibilidad | Los eclipses quedan como candidatos nodales hasta confirmación astronómica; ampliar cartas patrón independientes |
| 6. Sirius | Parcial y neutral | cuatro capas, modos purist/calibrated, testimonios, contradicciones, confianza y revisión manual | Registro estructural sin observaciones confirmadas; `data/sirius_observations.yaml` está vacío y no deben inventarse testimonios |
| 7. Sorteo | Completo | backtracking, restricciones, seeds, análisis y test de 100.000 sorteos | Sustituir reglas proyectadas cuando FIFA publique 2030 |
| 8. Monte Carlo | Completo para escenarios disponibles | grupos, desempates, eliminatorias, tres modelos, sensibilidad y 100.000 simulaciones | Fechas/rivales específicos por ronda dependen del calendario 2030 oficial |
| 9. Backtesting | Parcial | 2010–2026, cuatro modelos, métricas, calibración temporal y leakage audit | Sólo la señal lunar histórica tiene datos prematch evaluables; las demás ablaciones siguen correctamente como no evaluables |
| 10. Dashboard | Completo para datos disponibles | diez tabs, selector 48/64, polling, fuentes, historia, backtest y Sirius | Añadir flujo de revisión humana para candidatos Sirius y conflictos |
| 11. Cinco llaves | Completo | exactamente cinco familias; PNG 4K, SVG, PDF y hashes | Ninguno conocido |
| 12. ACTUALIZAR | Parcial | pipeline idempotente, snapshots, simulación, informe, llaves y evento local | `affected_charts` identifica invalidaciones, pero aún no existe una caché persistente de cartas que recalcule sólo esas entidades |
| 13. Historial | Completo | manifests append-only, commit, versión, timestamp, seed, fuentes, supuestos y resultados | Ninguno conocido |
| 14. Seguridad/calidad | Completo para v0.2 | allow-list SSRF, límites, API key, auditorías, CI backend/frontend/integration | Revisar periódicamente dependencias y TOS |
| 15. Deploy | Completo | Compose desarrollo/producción, health checks, migraciones, backups y `.env.example` | Validación en una infraestructura productiva real queda fuera del repositorio |

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
2. Crear una cola de revisión persistente para convertir candidatos Sirius en observaciones
   confirmadas con provenance completo.
3. Implementar adaptadores oficiales versionados de fútbol a medida que sus contratos sean
   verificables; hasta entonces conservar snapshots observacionales.
4. Añadir caché de cartas por hash de inputs y recálculo selectivo real.
5. Ampliar el backtest sólo con predicciones y datos prematch congelados, nunca reconstruidos a
   posteriori.
