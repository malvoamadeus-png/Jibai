from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .pipeline import AnalysisRunSummary

__all__ = [
    "AnalysisRunSummary",
    "normalize_existing_analysis",
    "reanalyze_existing_content",
    "run_analysis",
]


def normalize_existing_analysis(*args: Any, **kwargs: Any) -> Any:
    from .pipeline import normalize_existing_analysis as _normalize_existing_analysis

    return _normalize_existing_analysis(*args, **kwargs)


def reanalyze_existing_content(*args: Any, **kwargs: Any) -> Any:
    from .pipeline import reanalyze_existing_content as _reanalyze_existing_content

    return _reanalyze_existing_content(*args, **kwargs)


def run_analysis(*args: Any, **kwargs: Any) -> Any:
    from .pipeline import run_analysis as _run_analysis

    return _run_analysis(*args, **kwargs)
