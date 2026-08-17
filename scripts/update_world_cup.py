from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from packages.common.types import ModelMode
from services.api.update_pipeline import UpdateCommand, UpdateOrchestrator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Execute an append-only Mundial 2030 update")
    parser.add_argument("--iterations", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=2030)
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--final-hour", type=int, choices=(17, 18, 20, 21), default=18)
    parser.add_argument(
        "--modes",
        nargs="+",
        choices=[mode.value for mode in ModelMode],
        default=[mode.value for mode in ModelMode],
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.iterations < 100:
        raise ValueError("iterations must be at least 100")
    execution = UpdateOrchestrator().run(
        UpdateCommand(
            iterations=args.iterations,
            seed=args.seed,
            modes=tuple(ModelMode(mode) for mode in args.modes),
            final_hour=args.final_hour,
            workers=args.workers,
        )
    )
    print(json.dumps(asdict(execution), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
