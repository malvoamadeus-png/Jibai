from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppPaths:
    root_dir: Path
    backend_dir: Path
    frontend_dir: Path
    data_dir: Path
    config_dir: Path
    runtime_dir: Path
    x_runtime_dir: Path
    x_debug_dir: Path
    xhs_runtime_dir: Path
    xhs_notes_dir: Path
    xhs_debug_dir: Path
    state_dir: Path
    ai_runtime_dir: Path
    ai_snapshots_dir: Path
    ai_note_extracts_dir: Path
    ai_author_timelines_dir: Path
    ai_stock_timelines_dir: Path
    insight_db_path: Path
    x_watchlist_path: Path
    x_watchlist_example_path: Path
    watchlist_path: Path
    watchlist_example_path: Path
    runtime_settings_path: Path
    runtime_settings_example_path: Path
    security_aliases_path: Path
    security_aliases_example_path: Path
    ai_settings_path: Path
    ai_settings_example_path: Path
    x_state_path: Path
    xhs_user_data_dir: Path
    xhs_storage_state_path: Path
    xhs_state_path: Path


def get_paths() -> AppPaths:
    root_dir = Path(__file__).resolve().parents[3]
    backend_dir = root_dir / "backend"
    frontend_dir = root_dir / "frontend"
    data_dir = root_dir / "data"
    config_dir = data_dir / "config"
    runtime_dir = data_dir / "runtime"
    x_runtime_dir = runtime_dir / "x"
    x_debug_dir = x_runtime_dir / "debug"
    xhs_runtime_dir = runtime_dir / "xhs"
    xhs_notes_dir = xhs_runtime_dir / "notes"
    xhs_debug_dir = xhs_runtime_dir / "debug"
    state_dir = runtime_dir / "state"
    ai_runtime_dir = runtime_dir / "ai"
    ai_snapshots_dir = ai_runtime_dir / "snapshots"
    ai_note_extracts_dir = ai_runtime_dir / "note_extracts"
    ai_author_timelines_dir = ai_runtime_dir / "author_timelines"
    ai_stock_timelines_dir = ai_runtime_dir / "stock_timelines"
    insight_db_path = runtime_dir / "insight.db"

    return AppPaths(
        root_dir=root_dir,
        backend_dir=backend_dir,
        frontend_dir=frontend_dir,
        data_dir=data_dir,
        config_dir=config_dir,
        runtime_dir=runtime_dir,
        x_runtime_dir=x_runtime_dir,
        x_debug_dir=x_debug_dir,
        xhs_runtime_dir=xhs_runtime_dir,
        xhs_notes_dir=xhs_notes_dir,
        xhs_debug_dir=xhs_debug_dir,
        state_dir=state_dir,
        ai_runtime_dir=ai_runtime_dir,
        ai_snapshots_dir=ai_snapshots_dir,
        ai_note_extracts_dir=ai_note_extracts_dir,
        ai_author_timelines_dir=ai_author_timelines_dir,
        ai_stock_timelines_dir=ai_stock_timelines_dir,
        insight_db_path=insight_db_path,
        x_watchlist_path=config_dir / "x_watchlist.json",
        x_watchlist_example_path=config_dir / "x_watchlist.example.json",
        watchlist_path=config_dir / "watchlist.json",
        watchlist_example_path=config_dir / "watchlist.example.json",
        runtime_settings_path=config_dir / "runtime_settings.json",
        runtime_settings_example_path=config_dir / "runtime_settings.example.json",
        security_aliases_path=config_dir / "security_aliases.json",
        security_aliases_example_path=config_dir / "security_aliases.example.json",
        ai_settings_path=config_dir / "ai_settings.local.json",
        ai_settings_example_path=config_dir / "ai_settings.example.json",
        x_state_path=state_dir / "x_monitor_state.json",
        xhs_user_data_dir=state_dir / "xhs_chrome_user_data",
        xhs_storage_state_path=state_dir / "xhs_storage_state.json",
        xhs_state_path=state_dir / "xhs_monitor_state.json",
    )


def ensure_runtime_dirs(paths: AppPaths) -> None:
    for path in (
        paths.backend_dir,
        paths.frontend_dir,
        paths.config_dir,
        paths.runtime_dir,
        paths.x_runtime_dir,
        paths.x_debug_dir,
        paths.xhs_runtime_dir,
        paths.xhs_notes_dir,
        paths.xhs_debug_dir,
        paths.state_dir,
        paths.ai_runtime_dir,
        paths.ai_snapshots_dir,
        paths.ai_note_extracts_dir,
        paths.ai_author_timelines_dir,
        paths.ai_stock_timelines_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)
