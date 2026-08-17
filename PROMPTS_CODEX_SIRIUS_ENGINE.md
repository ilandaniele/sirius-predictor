# Mundial 2030 Sirius Engine — Prompts completos para Codex

## Objetivo del proyecto
Construir una app profesional y actualizable que combine:
- Mundial 2030 de 64 equipos.
- 16 grupos de 4; clasifican 2.
- España, Portugal, Marruecos, Argentina, Paraguay y Uruguay en Bombo 1.
- Final en Madrid el 21/07/2030; hora base 18:00, con sensibilidad 17:00/18:00/20:00/21:00 y ±15 min.
- Supuesto de trabajo: Lionel Scaloni continúa con Argentina.
- Metodología pública de Juan Cruz Sirius.
- Motor de sorteo FIFA extrapolado.
- Monte Carlo de grupos, cruces y llaves.
- Backtesting histórico.
- Scraping/actualización de datos con trazabilidad.
- Dashboard, informes y 5 llaves visuales más probables.

---

## PROMPT 0 — Auditoría inicial (NO modificar código)

> Quiero convertir este repositorio en una aplicación profesional llamada **Mundial 2030 Sirius Engine**.
>
> Antes de modificar cualquier archivo:
> 1. Leé todo el repositorio.
> 2. Identificá arquitectura actual, deuda técnica, archivos redundantes, dependencias y riesgos.
> 3. Identificá qué partes son prototipo/mock y cuáles son reutilizables.
> 4. Revisá README y documentación existente.
> 5. Proponé arquitectura objetivo.
> 6. Proponé un plan por fases con entregables, tests y criterios de aceptación.
> 7. Listá decisiones que no deberían tomarse todavía.
> 8. No implementes nada aún.
>
> Escenario fijo:
> - 64 equipos.
> - 16 grupos de 4.
> - clasifican 2.
> - seis anfitriones en Bombo 1: España, Portugal, Marruecos, Argentina, Paraguay y Uruguay.
> - máximo 2 UEFA por grupo y máximo 1 de cualquier otra confederación.
> - final en Madrid, 21/07/2030.
> - hora base 18:00 local, con sensibilidad 17:00/18:00/20:00/21:00 y ±15 minutos.
> - asumir que Lionel Scaloni continúa con Argentina.
>
> No asumas que la astrología tiene validez científica. Debe mostrarse como modelo experimental y compararse con un baseline futbolístico.

---

## PROMPT 1 — Crear AGENTS.md y reglas permanentes

> Creá un `AGENTS.md` en la raíz del repo con estas reglas:
> - No inventar datos faltantes.
> - Todo dato externo debe guardar fuente, URL, fecha de consulta y calidad A/B/C/D/X.
> - Nunca tratar una hora natal desconocida como 12:00.
> - Si falta hora, no usar ASC/MC/casas salvo análisis de sensibilidad horaria explícito.
> - Separar fuerza del modelo y calidad de datos.
> - Mantener modelos `FOOTBALL_ONLY`, `SIRIUS_ONLY` y `HYBRID` separados.
> - Guardar snapshots históricos de cada actualización.
> - Toda predicción debe guardar versión de modelo y timestamp.
> - Ningún cambio de pesos puede reescribir predicciones pasadas.
> - Tests obligatorios para sorteo, efemérides, simulaciones y parsers.
> - Datos dudosos scraped no se integran automáticamente sin validación.
> - Una fuente A nunca puede ser reemplazada automáticamente por una C/D.
> Después hacé commit sólo de documentación/configuración.

---

## PROMPT 2 — Arquitectura profesional

> Reestructurá el proyecto con esta arquitectura:
>
> ```
> apps/
>   web/
> services/
>   api/
> packages/
>   football/
>   astrology/
>   sirius/
>   montecarlo/
>   reports/
>   common/
> collectors/
>   fifa/
>   federations/
>   historical/
>   natal/
>   sirius_archive/
> db/
> tests/
> docs/
> ```
>
> Stack:
> - Next.js + TypeScript.
> - FastAPI + Python.
> - PostgreSQL + SQLAlchemy + Alembic.
> - Redis + Celery (o equivalente simple) para jobs.
> - requests/BeautifulSoup y Playwright sólo donde haga falta.
> - Swiss Ephemeris para astrología.
> - NumPy para Monte Carlo.
> - pytest + mypy + ruff.
> - Vitest/Playwright frontend.
> - Docker Compose local.
>
> Creá interfaces claras entre módulos. No migres lógica vieja a ciegas: encapsulá primero y agregá tests.

---

## PROMPT 3 — Modelo de datos + provenance

> Diseñá PostgreSQL con entidades mínimas:
> `Team`, `Confederation`, `Tournament`, `TournamentFormat`, `RankingSnapshot`, `DrawPot`, `Group`, `Fixture`, `Venue`, `Person`, `CoachTenure`, `CaptainTenure`, `BirthData`, `BirthDataSource`, `FederationEvent`, `WorldCupDebutEvent`, `CoachDebutEvent`, `AstrologyChart`, `AstrologyTechniqueResult`, `Source`, `SourceClaim`, `DataQuality`, `ModelVersion`, `PredictionSnapshot`, `SimulationRun`, `SimulationPath`, `BacktestRun`.
>
> Cada `SourceClaim` debe guardar:
> - valor;
> - fuente;
> - fecha de consulta;
> - confianza;
> - oficial sí/no;
> - inferido sí/no;
> - confirmado manualmente sí/no.
>
> Implementá migraciones y tests.

---

## PROMPT 4 — Pipeline de actualización y scraping

> Implementá collectors modulares con prioridad:
> 1. FIFA y federaciones oficiales.
> 2. Archivos históricos confiables.
> 3. Astro-Databank para horas natales.
> 4. Bases astrológicas secundarias como fallback.
> 5. TikTok/Instagram/YouTube/redes sólo como **pistas**, nunca como verdad automática.
>
> El pipeline debe:
> - detectar cambios;
> - normalizar nombres;
> - deduplicar;
> - comparar snapshot anterior;
> - producir changelog;
> - resolver precedencia por calidad;
> - marcar conflictos para revisión humana;
> - continuar aunque falle una fuente.
>
> Implementá primero ranking FIFA, equipos, DT, capitanes, fixtures, sedes, horarios, resultados y datos de nacimiento.

---

## PROMPT 5 — Motor astrológico Swiss Ephemeris

> Implementá `packages/astrology` con Swiss Ephemeris.
>
> Funciones:
> - carta natal/evento;
> - ASC/MC/casas;
> - relocalización;
> - tránsitos;
> - revolución solar;
> - revolución lunar;
> - demi-lunar;
> - cuartilunar;
> - progresiones secundarias;
> - direcciones primarias sólo con hora suficientemente confiable;
> - Proluna opcional;
> - dignidades esenciales/accidentales;
> - recepciones;
> - regentes y almutens;
> - Parte de Fortuna;
> - Parte de Victoria;
> - Parte del Espíritu;
> - otras partes configurables;
> - antiscias/contra-antiscias;
> - estrellas fijas configurables;
> - aspectos/orbes;
> - lunaciones/eclipses/ingresos;
> - carta del kickoff;
> - sensibilidad horaria.
>
> Reglas:
> - resultados deterministas;
> - tests con cartas conocidas;
> - guardar parámetros de cálculo;
> - no calcular casas si falta hora real.
>
> Agregá `birth_time_sensitivity()` para muestrear 00:00–23:59 cuando la hora sea desconocida y reportar qué conclusiones sobreviven al cambio horario.

---

## PROMPT 6 — Motor Sirius

> Implementá `packages/sirius` sin reducir todavía todo a un score arbitrario.
>
> **Nivel estructural**
> - ciclo/debut DT;
> - debut mundialista;
> - país/federación;
> - capitán;
> - DT natal.
>
> **Nivel anual**
> - RS;
> - progresiones;
> - direcciones/Proluna si corresponde;
> - tránsitos;
> - dignidades/recepciones;
> - Júpiter/Saturno/Sol/Luna;
> - PF/PV/partes.
>
> **Nivel torneo**
> - RL;
> - demi-lunar;
> - cuartilunar;
> - lunaciones/eclipses/ingresos;
> - armónicas;
> - estrellas;
> - antiscias.
>
> **Nivel partido**
> - carta kickoff;
> - Casas I/VII;
> - regentes;
> - MC;
> - Luna;
> - partes arábigas;
> - modalidad fija/cardinal/mutable;
> - posible alargue/penales;
> - ventanas/minutos críticos.
>
> Salidas:
> - `journey_index`;
> - `coronation_index`;
> - `data_confidence`;
> - testimonios favorables/adversos;
> - contradicciones;
> - robustez horaria;
> - explicación textual.
>
> Modos:
> - `SIRIUS_PURIST`: reproduce reglas públicas documentadas.
> - `SIRIUS_CALIBRATED`: mismos features, pesos calibrables por backtesting.
>
> No entrenes pesos todavía.

---

## PROMPT 7 — Sorteo 64 equipos

> Implementá sorteo completo:
> - 4 bombos de 16;
> - seis anfitriones siempre en Bombo 1;
> - otros 10 del Bombo 1 según ranking/proyección;
> - máximo 2 UEFA por grupo;
> - máximo 1 de otra confederación;
> - grupos A-P;
> - backtracking real para garantizar viabilidad;
> - seed reproducible.
>
> Agregá tests que generen 100.000 sorteos sin violar reglas.
>
> Outputs:
> - distribución de rivales de Argentina por bombo;
> - familias de grupos;
> - grupos fáciles/medios/duros;
> - probabilidad de cada rival.
>
> Mantener Argentina y España en sectores opuestos del cuadro como supuesto configurable.

---

## PROMPT 8 — Monte Carlo completo

> Simulá torneo completo:
> - sorteo;
> - grupos partido a partido;
> - desempates;
> - 1º/2º;
> - dieciseisavos;
> - octavos;
> - cuartos;
> - semifinal;
> - final.
>
> No usar un rating Sirius fijo durante todo el torneo. Separar señal anual, señal temporal por ronda, rival específico e incertidumbre.
>
> Modos:
> - FOOTBALL_ONLY
> - SIRIUS_ONLY
> - HYBRID
>
> Outputs:
> - campeón/finalista/semifinalista;
> - probabilidades por ronda;
> - rivales de Argentina por ronda;
> - final más frecuente;
> - cinco caminos/llaves de mayor densidad;
> - sensibilidad a hora final, capitán y datos desconocidos.
>
> Optimizar para >=100.000 simulaciones y agregar tests de reproducibilidad.

---

## PROMPT 9 — Backtesting histórico y ablation

> Construí backtesting para 2010, 2014, 2018, 2022 y 2026.
>
> Regla crítica: para cada fecha histórica usar únicamente información disponible antes de ese partido.
>
> Comparar:
> - FOOTBALL_ONLY;
> - SIRIUS_PURIST;
> - SIRIUS_CALIBRATED;
> - HYBRID.
>
> Métricas:
> - log loss;
> - Brier score;
> - accuracy;
> - calibration curve;
> - ranking del campeón;
> - precisión por ronda.
>
> Hacer ablation study quitando de a una:
> ciclo DT, debut mundialista, RS, RL, cuartilunar, PF, estrellas, antiscias, eclipses, etc.
>
> Mostrar qué técnicas mejoran o empeoran resultados fuera de muestra. No calibrar sobre el mismo Mundial evaluado.

---

## PROMPT 10 — Dashboard frontend

> Construí dashboard con botón `ACTUALIZAR MUNDIAL 2030`.
>
> Mostrar:
> - última actualización;
> - cambios detectados;
> - ranking de candidatos;
> - Fuerza Sirius;
> - Confianza de Datos;
> - Índice Recorrido;
> - Índice Coronación;
> - probabilidades FOOTBALL/SIRIUS/HYBRID;
> - camino de Argentina;
> - grupos posibles;
> - rivales por ronda;
> - final más probable;
> - changelog histórico.
>
> Tabs:
> Dashboard / Argentina / 64 selecciones / Sorteo / Simulaciones / Sirius / Fuentes / Backtesting / Historial / Configuración.
>
> Cada dato visible debe poder abrir su fuente/provenance.

---

## PROMPT 11 — Generador de las 5 llaves

> Generá exactamente cinco llaves completas por actualización:
> 1. llave más probable;
> 2. segunda;
> 3. tercera;
> 4. cuarta;
> 5. quinta.
>
> Diseño:
> - cuadro de fútbol profesional;
> - 32 equipos en eliminación;
> - eliminado en gris desde la ronda en que queda afuera;
> - ganador permanece a color;
> - campeón central muy destacado;
> - resultados modales o probabilidad de cada cruce;
> - final Madrid destacada;
> - probabilidad de la familia de llave;
> - panel pequeño con razones Sirius del campeón.
>
> Exportar PNG 4K, SVG y PDF.
> Debe generarse programáticamente desde simulaciones, nunca con texto hardcodeado.

---

## PROMPT 12 — Botón ACTUALIZAR

> Implementá pipeline idempotente:
> 1. consultar fuentes;
> 2. detectar cambios;
> 3. validar calidad;
> 4. crear snapshot;
> 5. recalcular sólo cartas afectadas;
> 6. recalcular Sirius;
> 7. ejecutar Monte Carlo;
> 8. guardar `PredictionSnapshot`;
> 9. comparar contra snapshot anterior;
> 10. generar informe;
> 11. generar cinco llaves;
> 12. notificar cambios relevantes.
>
> Resumen visible:
> `8 fuentes actualizadas · 3 cambios relevantes · Argentina +1.2 pp · España -0.6 pp · nueva hora natal pendiente de revisión`.

---

## PROMPT 13 — Historial/versionado

> Cada ejecución debe guardar:
> - git commit;
> - versión del modelo;
> - timestamp;
> - fuentes;
> - supuestos;
> - seed;
> - número de simulaciones;
> - pesos;
> - resultados.
>
> Nunca sobrescribir predicciones pasadas.
> Crear gráfico histórico Argentina/España/Francia/Brasil/etc.

---

## PROMPT 14 — Auditoría de seguridad y calidad

> Revisá secretos, SSRF, scraping inseguro, inyección, XSS, SQL injection, dependencias, timeouts, rate limits, robots/TOS, manejo de errores, logs, reproducibilidad y performance.
>
> CI obligatorio:
> - lint;
> - mypy;
> - pytest;
> - frontend tests;
> - integration tests;
> - migrations check.
>
> No preparar deploy si CI falla.

---

## PROMPT 15 — Deploy

> Prepará Docker Compose para desarrollo y deployment productivo con frontend/API/PostgreSQL/Redis/workers/storage.
> Crear `.env.example`, health checks, logging, backups y migraciones controladas. No hardcodear secretos.

---

# AGENTES PARALELOS

**Agente Datos de fútbol**
> Trabajá sólo en collectors/football + normalización + provenance. No modifiques astrology/frontend.

**Agente Birth Data**
> Pipeline de horas natales, calidad A/B/C/D/X, conflictos y sensibilidad horaria. Nunca aceptar 12:00 como hora real.

**Agente Astrología**
> Swiss Ephemeris, cálculos y tests. No decidir pesos Sirius.

**Agente Sirius Research**
> Convertí metodología pública documentada de Sirius en reglas configurables. Separá explícito vs inferido.

**Agente Sorteo/Monte Carlo**
> Sortear 64 y simular. Priorizar correctitud, reproducibilidad y performance.

**Agente Backtesting**
> Dataset temporalmente limpio 2010–2026. Prohibido usar información futura.

**Agente Frontend**
> Dashboard y llaves consumiendo APIs. No duplicar lógica de dominio.

---

# PROMPT DE CIERRE DE CADA FASE

> Antes de declarar terminada esta fase:
> 1. resumí lo implementado;
> 2. listá archivos modificados;
> 3. corré tests;
> 4. mostr á resultados;
> 5. listá deuda técnica;
> 6. verificá que no inventaste datos;
> 7. proponé próximo paso;
> 8. no empieces la fase siguiente sin aprobación.

---

# PRIMER RELEASE v0.1.0

> Debe permitir:
> - campo proyectado de 64 equipos;
> - bombos válidos;
> - sorteos legales;
> - >=100k simulaciones;
> - grupos plausibles de Argentina;
> - rivales por ronda;
> - ranking de campeón;
> - cinco llaves visuales;
> - snapshots;
> - fuentes/calidad de datos.
>
> La parte Sirius puede estar parcialmente mocked si todavía no está terminada, pero todo mock debe estar explícitamente etiquetado. Crear changelog y pendientes.

---

## Regla global
Si Codex encuentra una decisión dudosa: documentarla, elegir la opción conservadora, no inventar, dejarla configurable y agregar TODO si depende de información futura.
