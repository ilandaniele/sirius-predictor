from __future__ import annotations

import random
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import streamlit as st
import yaml

from engine.backtest import EDITION_FOLDERS, load_historical_matches, run_backtest
from engine.config import load_scenario, load_teams, validate_scenario
from engine.draw import draw_groups
from engine.reporting import bracket_html, build_markdown_report
from engine.sim import run_engine
from engine.sirius import lunar_longitude
from engine.updates import StateStore, refresh_sources

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
STATE = BASE / "state"

st.set_page_config(
    page_title="Mundial 2030 Sirius Engine",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(
    """
    <style>
    .block-container{padding-top:1.5rem;max-width:1500px}
    [data-testid="stMetric"]{background:#101827;border:1px solid #24334a;
                              border-radius:12px;padding:12px}
    .scenario-badge{display:inline-block;background:#5b3b00;color:#ffd978;border:1px solid #a86f00;
                    border-radius:999px;padding:4px 10px;font-size:.78rem;margin-bottom:8px}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False)
def load_contracts():
    scenario = load_scenario(DATA / "scenario.yaml")
    teams = load_teams(DATA / "teams.csv")
    validate_scenario(scenario, teams)
    sources = yaml.safe_load((DATA / "sources.yaml").read_text(encoding="utf-8"))
    methods = yaml.safe_load((DATA / "sirius_methods.yaml").read_text(encoding="utf-8"))
    return scenario, teams, sources, methods


scenario, teams, sources, methods = load_contracts()
store = StateStore(STATE)
team_names = {team.team_id: team.team for team in teams}

st.markdown(
    '<span class="scenario-badge">ESCENARIO HIPOTÉTICO VERSIONADO</span>', unsafe_allow_html=True
)
st.title("🏆 Mundial 2030 — Sirius Engine")
st.caption(
    "64 equipos · 16 grupos · seis anfitriones en Bombo 1 · final Madrid 21/07/2030 · "
    "Scaloni continúa (supuesto de trabajo)"
)
st.warning(
    "La astrología no es un método científicamente validado para predecir resultados deportivos. "
    "Sirius se presenta como capa experimental, siempre separada y comparada con el baseline "
    "futbolístico.",
    icon="⚠️",
)

with st.sidebar:
    st.header("Ejecución")
    iterations = st.select_slider(
        "Iteraciones Monte Carlo",
        options=[250, 1_000, 2_500, 5_000, 10_000, 25_000],
        value=1_000,
    )
    mode_label = st.radio(
        "Modelo",
        ["Baseline futbolístico", "Baseline + Sirius experimental"],
        index=1,
    )
    mode = "baseline" if mode_label.startswith("Baseline futbolístico") else "combined"
    final_hour = st.selectbox(
        "Hora base final (Madrid)",
        list(scenario.final.sensitivity_hours),
        index=list(scenario.final.sensitivity_hours).index(scenario.final.base_hour),
        format_func=lambda value: f"{value:02d}:00",
    )
    seed = int(st.number_input("Semilla", min_value=0, max_value=2**31 - 1, value=2030))
    run_button = st.button("▶ SIMULAR MUNDIAL 2030", type="primary", width="stretch")
    update_button = st.button("↻ ACTUALIZAR FUENTES", width="stretch")
    st.caption(
        "La actualización crea snapshots por hash. Una fuente caída no reemplaza el último "
        "dato válido."
    )

if update_button:
    with st.spinner("Consultando y versionando fuentes..."):
        st.session_state["last_update"] = refresh_sources(BASE, store, DATA / "sources.yaml")
    st.toast("Actualización terminada; revisá Fuentes y cambios.")

if run_button:
    progress = st.progress(0.0, text="Simulando grupos y llaves...")
    try:
        bundle = run_engine(
            teams,
            scenario,
            n=iterations,
            seed=seed,
            mode=mode,
            final_hour=final_hour,
            progress=lambda value: progress.progress(value, text=f"Simulando… {value:.0%}"),
        )
        store.record_simulation(bundle)
        st.session_state["simulation"] = bundle
        progress.progress(1.0, text="Simulación completa")
    except Exception as exc:
        progress.empty()
        st.exception(exc)

bundle = st.session_state.get("simulation")

tabs = st.tabs(
    [
        "Dashboard",
        "Ranking y Monte Carlo",
        "Bombos y sorteo",
        "Argentina",
        "5 llaves",
        "Fuentes y cambios",
        "Método Sirius",
        "Backtesting",
        "Versiones",
    ]
)

with tabs[0]:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Equipos", len(teams))
    c2.metric("Grupos", scenario.format.groups)
    c3.metric("Final", f"{scenario.final.city} · {scenario.final.local_date}")
    c4.metric("Escenario", scenario.as_of)
    st.subheader("Estado del escenario")
    st.info(
        "Participantes, bombos, ratings, entrenadores y horario son proyecciones editables. "
        "La app no los presenta como decisiones oficiales de FIFA."
    )
    if bundle is None:
        projected = pd.DataFrame([team.to_dict() for team in teams]).sort_values(
            "projected_elo", ascending=False
        )
        chart = px.bar(
            projected.head(16),
            x="team",
            y="projected_elo",
            color="confed",
            title="Priors futbolísticos proyectados (antes de simular)",
        )
        st.plotly_chart(chart, width="stretch")
        st.info("Usá “SIMULAR MUNDIAL 2030” para generar probabilidades, caminos y llaves.")
    else:
        leader = bundle.ranking.iloc[0]
        a1, a2, a3 = st.columns(3)
        a1.metric("Mayor probabilidad", leader["Selección"], f"{leader['Campeón %']:.2f}%")
        argentina = bundle.ranking[bundle.ranking["ID"] == "ARG"].iloc[0]
        a2.metric(
            "Argentina campeón",
            f"{argentina['Campeón %']:.2f}%",
            f"±{argentina['IC95 ± pp']:.2f} pp",
        )
        a3.metric("Run ID", bundle.manifest.run_id)
        chart = px.bar(
            bundle.ranking.head(20),
            x="Selección",
            y="Campeón %",
            error_y="IC95 ± pp",
            color="Final %",
            title="Probabilidad de título con intervalo Monte Carlo 95%",
        )
        st.plotly_chart(chart, width="stretch")
        st.dataframe(bundle.final_pairs.head(10), width="stretch", hide_index=True)

with tabs[1]:
    if bundle is None:
        st.info("Ejecutá una simulación para ver resultados.")
    else:
        st.caption(
            f"Modo: {bundle.manifest.mode} · {bundle.manifest.iterations:,} iteraciones · "
            f"semilla {bundle.manifest.seed} · hash {bundle.manifest.input_sha256[:12]}…"
        )
        st.dataframe(bundle.ranking, width="stretch", hide_index=True)
        st.plotly_chart(
            px.line(
                bundle.convergence,
                x="Iteraciones",
                y="Argentina campeón %",
                markers=True,
                title="Convergencia de la estimación para Argentina",
            ),
            width="stretch",
        )
        report = build_markdown_report(bundle, scenario.name)
        d1, d2 = st.columns(2)
        d1.download_button(
            "Descargar informe Markdown",
            report,
            file_name=f"sirius-{bundle.manifest.run_id}.md",
            mime="text/markdown",
            width="stretch",
        )
        d2.download_button(
            "Descargar ranking CSV",
            bundle.ranking.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"ranking-{bundle.manifest.run_id}.csv",
            mime="text/csv",
            width="stretch",
        )

with tabs[2]:
    pot_frame = pd.DataFrame([team.to_dict() for team in teams]).rename(
        columns={
            "team": "Selección",
            "confed": "Confederación",
            "pot": "Bombo",
            "qualification_status": "Estado",
            "projected_elo": "Elo proyectado",
            "as_of": "Corte",
        }
    )
    st.dataframe(
        pot_frame[
            ["Bombo", "Selección", "Confederación", "Estado", "Elo proyectado", "Corte"]
        ].sort_values(["Bombo", "Elo proyectado"], ascending=[True, False]),
        width="stretch",
        hide_index=True,
    )
    st.subheader("Sorteo legal reproducible")
    sample = draw_groups(teams, scenario, random.Random(seed))
    draw_rows = [
        {"Grupo": name, **{f"Bombo {team.pot}": team.team for team in group}}
        for name, group in sample.items()
    ]
    st.dataframe(pd.DataFrame(draw_rows), width="stretch", hide_index=True)
    st.caption(
        f"Algoritmo: {scenario.draw.sampling}; regla {scenario.draw.version}. "
        "Máximo dos UEFA y uno de las restantes confederaciones."
    )

with tabs[3]:
    if bundle is None:
        st.info("Ejecutá una simulación para calcular el camino de Argentina.")
    else:
        st.plotly_chart(
            px.bar(
                bundle.argentina_stages,
                x="Etapa alcanzada",
                y="Probabilidad %",
                title="Probabilidad acumulada de alcanzar cada etapa",
            ),
            width="stretch",
        )
        st.subheader("Grupos posibles")
        st.dataframe(bundle.argentina_groups, width="stretch", hide_index=True)
        st.caption(
            "No hay un único grupo dominante: las combinaciones legales individuales son raras."
        )
        st.subheader("Rivales por ronda")
        rival_tabs = st.tabs(list(bundle.argentina_rivals))
        for rival_tab, (_round_name, frame) in zip(
            rival_tabs, bundle.argentina_rivals.items(), strict=True
        ):
            with rival_tab:
                st.dataframe(frame, width="stretch", hide_index=True)
                st.caption("Frecuencia condicionada a que Argentina alcance esa ronda.")

with tabs[4]:
    if bundle is None:
        st.info("Ejecutá una simulación para generar las cinco llaves.")
    else:
        st.caption(
            "Se agrupan por campeón, subcampeón y semifinalistas. La densidad evita llamar “modal” "
            "a una llave completa que probablemente aparezca una sola vez."
        )
        for index, item in enumerate(bundle.top_brackets, 1):
            title = (
                f"{index}. {item['champion']} campeón · {item['runner_up']} finalista · "
                f"densidad {item['density_percent']:.3f}% ({item['count']} casos)"
            )
            with st.expander(title, expanded=index == 1):
                st.markdown(bracket_html(item["representative"], teams), unsafe_allow_html=True)

with tabs[5]:
    source_frame = pd.DataFrame(sources)
    st.dataframe(source_frame, width="stretch", hide_index=True)
    if "last_update" in st.session_state:
        st.subheader("Cambios de la última actualización")
        st.dataframe(st.session_state["last_update"], width="stretch", hide_index=True)
    st.subheader("Historial de snapshots")
    snapshots = store.snapshots()
    if snapshots.empty:
        st.info("Todavía no hay snapshots. Usá “ACTUALIZAR FUENTES”.")
    else:
        st.dataframe(snapshots, width="stretch", hide_index=True)
    st.caption("Cada captura conserva URL, timestamp, estado HTTP, hash SHA-256, tamaño y error.")

with tabs[6]:
    st.subheader("Proxy implementado")
    st.json(methods["implemented_proxy"], expanded=True)
    st.subheader("Registro de la metodología pública")
    st.json(methods["public_method_registry"], expanded=False)
    st.caption(
        "Las técnicas enumeradas como no implementadas no afectan probabilidades. No se inventan "
        "horas natales; ángulos y casas deben omitirse o marginalizarse cuando falte hora fiable."
    )
    final_dt = datetime.fromisoformat(scenario.final.local_date).replace(
        hour=final_hour, tzinfo=ZoneInfo(scenario.final.timezone)
    )
    ephemeris = lunar_longitude(final_dt)
    st.info(
        f"Proveedor astronómico activo: {ephemeris.provider}. Longitud lunar de control: "
        f"{ephemeris.longitude:.4f}° para {final_dt.isoformat()}."
    )
    if bundle is not None:
        st.subheader("Sensibilidad horaria de la final modal")
        st.dataframe(bundle.sensitivity, width="stretch", hide_index=True)

with tabs[7]:
    st.write(
        "Backtest prequential sobre partidos de Mundial 2010, 2014, 2018, 2022 y 2026. "
        "El Elo y el historial lunar sólo se actualizan después de cada resultado."
    )
    if st.button("Ejecutar backtesting histórico", width="stretch"):
        with st.spinner("Descargando snapshots CC0 y evaluando sin fuga temporal..."):
            editions = list(EDITION_FOLDERS)
            historical = load_historical_matches(editions, store)
            backtest = run_backtest(historical)
            store.record_backtest(backtest.run_id, editions, backtest.metrics)
            st.session_state["backtest"] = backtest
    backtest = st.session_state.get("backtest")
    if backtest is not None:
        st.dataframe(backtest.metrics, width="stretch", hide_index=True)
        totals = backtest.metrics[backtest.metrics["Edición"] == "Total"].set_index("Modelo")
        if len(totals) == 2:
            delta = totals.loc["Baseline + Sirius", "Brier"] - totals.loc["Baseline Elo", "Brier"]
            if delta < 0:
                st.success(f"En esta prueba la capa experimental reduce Brier en {-delta:.6f}.")
            else:
                st.warning(
                    f"En esta prueba la capa experimental empeora Brier en {delta:.6f}; "
                    "el resultado negativo se conserva y publica."
                )
        st.plotly_chart(
            px.line(
                backtest.metrics[backtest.metrics["Edición"] != "Total"],
                x="Edición",
                y="Brier",
                color="Modelo",
                markers=True,
                title="Brier por edición (menor es mejor)",
            ),
            width="stretch",
        )
        calibration_chart = px.scatter(
            backtest.calibration,
            x="Probabilidad media",
            y="Frecuencia observada",
            color="Modelo",
            size="Casos",
            title="Calibración (diagonal = calibración perfecta)",
        )
        calibration_chart.update_traces(mode="lines+markers")
        calibration_chart.add_shape(
            type="line", x0=0, y0=0, x1=1, y1=1, line={"dash": "dash", "color": "gray"}
        )
        st.plotly_chart(calibration_chart, width="stretch")
        with st.expander("Calidad temporal de los partidos"):
            st.dataframe(backtest.data_quality, width="stretch", hide_index=True)
            st.caption(
                "OpenFootball lista horas locales. Este prototipo las interpreta como UTC para el "
                "proxy lunar; por eso la calidad se muestra y no se oculta."
            )
        st.download_button(
            "Descargar predicciones de backtest",
            backtest.predictions.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"backtest-{backtest.run_id}.csv",
            mime="text/csv",
        )
    else:
        st.info("El backtest se ejecuta bajo demanda y conserva snapshots de entrada.")

with tabs[8]:
    history = store.simulation_history()
    if history.empty:
        st.info("Todavía no hay ejecuciones persistidas.")
    else:
        st.dataframe(history, width="stretch", hide_index=True)
    if bundle is not None:
        st.subheader("Manifiesto activo")
        st.json(asdict(bundle.manifest), expanded=True)
    st.caption(
        "Un resultado sólo es reproducible si coinciden escenario, snapshot, versiones, modo, "
        "semilla, hora e iteraciones."
    )
