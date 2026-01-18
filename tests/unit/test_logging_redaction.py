import logging

from app.infra import logging as logging_mod
from app.infra.logging import configure_logging


def test_log_redaction_masks_bearer_token(caplog):
    configure_logging()
    logger = logging.getLogger("test.redaction")
    token = "Bearer abc.def.ghi"

    with caplog.at_level(logging.INFO):
        logger.info("Authorization: %s", token)

    assert "Bearer [redacted]" in caplog.text
    assert token not in caplog.text

    caplog.clear()
    with caplog.at_level(logging.INFO):
        logger.info("auth extras", extra={"headers": {"authorization": token}})

    record = caplog.records[0]
    assert record.headers["authorization"] == "[redacted]"


def test_attach_filter_to_handlers():
    handler = logging.StreamHandler()
    root = logging.getLogger("attach")
    root.addHandler(handler)
    configure_logging()
    assert any("RedactionFilter" in str(f.__class__) for f in handler.filters)


def test_redaction_handles_nested_values_and_messages(caplog):
    configure_logging()
    # Directly exercise helper paths for list/tuple and message redaction.
    nested = logging_mod._redact_value(["Bearer secret", ("token=abc",)])
    assert nested[0].startswith("Bearer [redacted]")
    assert nested[1][0].endswith("[redacted]")

    with caplog.at_level(logging.INFO):
        logging.getLogger("test.redaction.msg").info(
            "api-key=supersecret", extra={"token": "should-hide"}
        )

    record = caplog.records[0]
    assert record.msg.endswith("[redacted]")
    assert record.token == "[redacted]"


def test_attach_filter_and_dict_args(caplog):
    handler = logging.StreamHandler()
    logger = logging.getLogger("dictargs")
    logger.addHandler(handler)
    logging_mod._attach_filter_to_handlers()
    with caplog.at_level(logging.INFO, logger="dictargs"):
        logger.info("msg %s", {"foo": "bar", "authorization": "secret"})
    rec = caplog.records[0]
    assert rec.args["foo"] == "bar"
    assert rec.args["authorization"] == "[redacted]"
