from app.domains.submissions import exceptions
from app.infra import env
from app.infra.config import settings


def test_env_helpers_local(monkeypatch):
    monkeypatch.setenv("ENV", "local")
    monkeypatch.setattr(settings, "ENV", "local")
    assert env.env_name() == "local"
    assert env.is_local_or_test() is True
    assert env.is_prod() is False


def test_env_helpers_prod(monkeypatch):
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.setattr(settings, "ENV", "prod")
    assert env.env_name() == "prod"
    assert env.is_local_or_test() is False
    assert env.is_prod() is True


def test_submission_exceptions_payloads():
    conflict = exceptions.SubmissionConflict()
    order_error = exceptions.SubmissionOrderError()
    sim_complete = exceptions.SimulationComplete()
    workspace_missing = exceptions.WorkspaceMissing()

    assert conflict.status_code == 409
    assert order_error.status_code == 400
    assert sim_complete.status_code == 409
    assert workspace_missing.status_code == 400

    # Custom detail propagates through __init__
    custom = exceptions.WorkspaceMissing(detail="Init first")
    assert custom.detail == "Init first"
