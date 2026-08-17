from packages.common.types import ModelMode
from scripts.update_world_cup import build_parser


def test_update_cli_defaults_to_all_isolated_modes() -> None:
    args = build_parser().parse_args([])
    assert args.iterations == 100_000
    assert args.seed == 2030
    assert args.modes == [mode.value for mode in ModelMode]
