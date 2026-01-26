from __future__ import annotations

import logging

from .redaction import REDACTOR, RedactionFilter


def _attach_filter_to_handlers() -> None:
    root = logging.getLogger()
    for handler in root.handlers:
        if not any(isinstance(f, RedactionFilter) for f in handler.filters):
            handler.addFilter(REDACTOR)


def configure_logging() -> None:
    _attach_filter_to_handlers()
    if getattr(configure_logging, "_configured", False):
        return
    original_factory = logging.getLogRecordFactory()

    def record_factory(*args, **kwargs):
        record = original_factory(*args, **kwargs)
        REDACTOR.filter(record)
        return record

    logging.setLogRecordFactory(record_factory)
    original_add_handler = logging.Logger.addHandler

    def add_handler(self, hdlr, *, _orig=original_add_handler):
        if not any(isinstance(f, RedactionFilter) for f in hdlr.filters):
            hdlr.addFilter(REDACTOR)
        return _orig(self, hdlr)

    logging.Logger.addHandler = add_handler
    configure_logging._configured = True


__all__ = [
    "configure_logging",
    "_attach_filter_to_handlers",
    "RedactionFilter",
    "REDACTOR",
]
