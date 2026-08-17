from packages.reports import BracketExportSpec, export_five_brackets


def test_exactly_five_brackets_export_svg_png_and_pdf(tmp_path, scenario, teams) -> None:
    from engine.sim import run_engine

    bundle = run_engine(teams, scenario, n=15, seed=44, mode="baseline")
    manifests = export_five_brackets(
        bundle.top_brackets,
        teams,
        tmp_path,
        sirius_reasons={"ARG": ["Testimonio documentado"]},
        spec=BracketExportSpec(960, 540, 20),
    )
    assert len(manifests) == 5
    assert all(set(item["files"]) == {"svg", "png", "pdf"} for item in manifests)
    assert all(item["canvas"] == {"width": 960, "height": 540} for item in manifests)
    assert (tmp_path / "manifest.json").exists()
