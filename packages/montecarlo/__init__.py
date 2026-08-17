"""Orquestación Monte Carlo reproducible y paralelizable."""

from .runner import ParallelSimulationResult, run_parallel

__all__ = ["ParallelSimulationResult", "run_parallel"]
