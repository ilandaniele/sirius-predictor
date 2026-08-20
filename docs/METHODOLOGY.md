# Metodología y protocolo experimental

## Modelos separados

- `FOOTBALL_ONLY`: Elo proyectado, incertidumbre de rating y goles Poisson.
- `SIRIUS_ONLY`: testimonios Sirius sin incorporar Elo futbolístico.
- `HYBRID`: combina el baseline con la señal Sirius acotada.

La fuerza del modelo, la incertidumbre Monte Carlo y la confianza de datos son variables distintas.
No se publica Sirius sin el baseline y el aviso de ausencia de validación científica.

## Baseline futbolístico

Cada torneo sortea una fuerza latente por selección. La diferencia Elo reparte un total esperado de
2,65 goles y se muestrea con Poisson. En grupos se aplican puntos, diferencia de gol, goles a favor,
mini-tabla y sorteo reproducible como último recurso. Eliminatorias empatadas incluyen prórroga y
penales. Las reglas 2030 que FIFA no publicó permanecen configurables y etiquetadas como supuestos.

## Astrología y Sirius

Swiss Ephemeris calcula posiciones y, sólo con hora real, ASC/MC/casas. Si la hora natal se
desconoce permanece nula; la sensibilidad 00:00–23:59 usa muestras sintéticas explícitas que nunca
se guardan como hora natal.

Sirius organiza evidencia en cuatro niveles:

1. estructural: ciclo DT, debut mundialista, país/federación, capitán y natal DT;
2. anual: retornos, progresiones, direcciones guardadas, tránsitos, dignidades y partes;
3. torneo: retornos lunares, lunaciones, estrellas y antiscias;
4. partido: kickoff, casas I/VII, regentes, MC, Luna, partes y ventanas críticas.

`SIRIUS_PURIST` acepta sólo reglas públicas explícitas. `SIRIUS_CALIBRATED` admite pesos congelados
y versionados, pero v0.2.1 no entrena ninguno: usa pesos unitarios y lo advierte. Toda salida conserva
testimonios favorables/adversos, contradicciones, robustez horaria y provenance; los índices son
balances descriptivos, no probabilidades.

Los priors Sirius de `data/teams.csv` son mocks de escenario calidad X y se muestran como tales, pero
ya no entran en las simulaciones de producción. Monte Carlo consume evaluaciones generadas por el
motor Sirius a partir de observaciones revisadas. Sin evidencia, Recorrido y Coronación quedan en
`insufficient_evidence` y el ajuste es neutral. La carta de kickoff sólo aporta cuando existe un
testimonio específico y trazable para ambos competidores.

El archivo público de Sirius se captura completo desde abril de 2014. Los textos detectados se usan
como corpus de investigación y cola de revisión, nunca como features automáticos. Esto permite
incorporar aciertos y errores cronológicamente sin seleccionar sólo resultados favorables.

## Sorteo y Monte Carlo

El primer sorteo se construye con backtracking y luego una cadena de swaps simétricos conserva todas
las restricciones. La semilla es reproducible y ARG/ESP quedan en grupos A/I como supuesto de
sectores opuestos. El formato 64 simula 96 partidos de grupo y 31 eliminatorios; el de 48 simula 72
de grupo y 31 eliminatorios, con ocho mejores terceros. El emparejamiento 48 de 2030 es una
proyección reproducible y evita revanchas de grupo, no una regla oficial futura.

Una llave completa casi nunca se repite. Las cinco visuales se seleccionan por familia definida por
campeón, subcampeón y semifinalistas; la densidad se informa y se exporta un representante completo.

## Backtesting

Las ediciones 2010, 2014, 2018, 2022 y 2026 usan predicción prequential: ratings e historia lunar se
actualizan después de observar cada partido. Para cada edición, `SIRIUS_CALIBRATED` selecciona su
alpha sólo con ediciones anteriores; nunca usa el Mundial evaluado ni información futura. El parser
exige 64 partidos y 32 equipos para 2010–2022, y 104 partidos y 48 equipos para 2026. También valida
rondas, campeón y nombres libres de anotaciones de marcador.

Un horario se convierte a UTC únicamente cuando la fuente publica un offset explícito. Los horarios
sin zona quedan nulos para la señal lunar: no se interpreta una hora local como UTC ni se arrastra
automáticamente el horario de otro partido. Las tandas de penales se conservan separadas del
marcador para identificar al campeón sin alterar el resultado 1X2 observado.

Se informan log loss, Brier, accuracy, calibración, ranking del campeón y precisión por ronda. La
ablación lunar es evaluable; técnicas sin dataset prematch congelado figuran como
`not_evaluable_missing_pre_match_data`, evitando reconstrucciones retrospectivas favorables.
El ranking pretorneo de campeón se informa para el baseline y el híbrido cuando es evaluable. Sirius
queda `not_evaluable_without_pre_tournament_forecast` en lugar de recibir un rango fabricado.
Si varios equipos tienen el mismo rating, se publican `rank_min` y `rank_max`; `rank` queda nulo
hasta que exista un puesto único, por lo que el orden interno de una colección nunca rompe empates.

## Principios de lectura

- No confundir frecuencia Monte Carlo con certeza.
- No seleccionar sólo aciertos ni ocultar resultados negativos.
- No modificar pesos luego de conocer el evento.
- No reemplazar fuentes de mayor calidad automáticamente.
- No interpretar testimonios astrológicos como causalidad científica.
