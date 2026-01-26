from app.api.app_builder import create_app
from app.api.app_meta import _env_name, _parse_csv
from app.api.lifespan import lifespan
from app.core.db import init_db_if_needed
from app.core.perf import perf_logging_enabled
from app.core.settings import settings

app = create_app()


def _cors_config() -> tuple[list[str], str | None]:
    cors_cfg = getattr(settings, "cors", None)
    origins = list(cors_cfg.CORS_ALLOW_ORIGINS or []) if cors_cfg else []
    origin_regex = cors_cfg.CORS_ALLOW_ORIGIN_REGEX if cors_cfg else None
    if not origins and not origin_regex:
        origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
    return origins, origin_regex


def _configure_perf_logging(app) -> None:
    if not perf_logging_enabled():
        return
    from app.core import db, perf

    perf.attach_sqlalchemy_listeners(db.engine)
    app.add_middleware(perf.RequestPerfMiddleware)


__all__ = [
    "app",
    "create_app",
    "lifespan",
    "_parse_csv",
    "_env_name",
    "_cors_config",
    "_configure_perf_logging",
    "perf_logging_enabled",
    "settings",
    "init_db_if_needed",
]
