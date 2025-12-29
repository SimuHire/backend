import pytest

from app.services.template_catalog import (
    ALLOWED_TEMPLATE_KEYS,
    DEFAULT_TEMPLATE_KEY,
    LEGACY_TEMPLATE_REPO_REWRITES,
    TemplateKeyError,
    normalize_template_repo_value,
    resolve_template_repo_full_name,
    validate_template_key,
)


@pytest.mark.parametrize(
    ("template_key", "expected_repo"),
    [
        ("python-fastapi", "simuhire-dev/simuhire-template-python-fastapi"),
        ("node-express-ts", "simuhire-dev/simuhire-template-node-express-ts"),
        (
            "monorepo-nextjs-fastapi",
            "simuhire-dev/simuhire-template-monorepo-nextjs-fastapi",
        ),
        (
            "monorepo-react-springboot",
            "simuhire-dev/simuhire-template-monorepo-react-springboot",
        ),
        (
            "mobile-backend-fastapi",
            "simuhire-dev/simuhire-template-mobile-backend-fastapi",
        ),
        ("ml-infra-mlops", "simuhire-dev/simuhire-template-ml-infra-mlops"),
    ],
)
def test_resolve_template_repo_full_name(template_key: str, expected_repo: str):
    assert resolve_template_repo_full_name(template_key) == expected_repo


def test_invalid_template_key_raises():
    with pytest.raises(TemplateKeyError) as excinfo:
        resolve_template_repo_full_name("unknown-stack")
    msg = str(excinfo.value)
    assert "Invalid templateKey" in msg
    for allowed in sorted(ALLOWED_TEMPLATE_KEYS)[:3]:
        assert allowed in msg


@pytest.mark.parametrize(
    ("legacy_repo", "expected_repo"),
    [
        (
            "simuhire-templates/node-day2-api",
            LEGACY_TEMPLATE_REPO_REWRITES["simuhire-templates/node-day2-api"],
        ),
        (
            "simuhire-templates/node-day3-debug",
            LEGACY_TEMPLATE_REPO_REWRITES["simuhire-templates/node-day3-debug"],
        ),
        (
            "simuhire-dev/simuhire-template-python",
            "simuhire-dev/simuhire-template-python-fastapi",
        ),
    ],
)
def test_normalize_template_repo_value_rewrites_legacy(
    legacy_repo: str, expected_repo: str
):
    assert normalize_template_repo_value(legacy_repo) == expected_repo


def test_normalize_template_repo_value_uses_template_key_for_blank():
    resolved = normalize_template_repo_value(None, template_key=DEFAULT_TEMPLATE_KEY)
    assert resolved == resolve_template_repo_full_name(DEFAULT_TEMPLATE_KEY)


def test_normalize_template_repo_value_rewrites_legacy_with_template_key():
    repo = normalize_template_repo_value(
        "simuhire-templates/node-day2-api", template_key="node-express-ts"
    )
    assert repo == "simuhire-dev/simuhire-template-node-express-ts"


def test_normalize_template_repo_value_returns_none_when_no_hints():
    assert normalize_template_repo_value("", template_key=None) is None


def test_validate_template_key_requires_string():
    with pytest.raises(TemplateKeyError):
        validate_template_key(123)  # type: ignore[arg-type]


def test_normalize_template_repo_value_invalid_key_and_custom_repo():
    assert normalize_template_repo_value(None, template_key="invalid-key") is None
    assert (
        normalize_template_repo_value("custom/repo", template_key="invalid-key")
        == "custom/repo"
    )
