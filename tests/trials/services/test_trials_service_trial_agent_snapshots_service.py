from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.ai import ai_policy_snapshot_service as policy_snapshot_service
from app.ai import build_ai_policy_snapshot
from app.evaluations.repositories import (
    delete_trial_agent_snapshots,
    get_required_trial_agent_snapshot,
    list_trial_agent_snapshots,
    replace_trial_agent_snapshots,
)
from app.trials.services import trials_services_trials_creation_service as trial_service
from tests.shared.factories import build_trial_agent_snapshots, create_talent_partner


def _payload() -> SimpleNamespace:
    return SimpleNamespace(
        title="Snapshot Trial",
        role="Backend Engineer",
        preferredLanguageFramework="Python/FastAPI",
        seniority="Mid",
        focus="Build a workflow service",
        templateKey="python-fastapi",
        companyContext={"domain": "operations", "productArea": "workflow tools"},
    )


def test_trial_agent_snapshot_fixture_uses_runtime_specific_metadata() -> None:
    snapshots = build_trial_agent_snapshots()
    by_name = {snapshot.agent_name: snapshot for snapshot in snapshots}

    code_impl = by_name["Code Implementation Reviewer"]
    winoe = by_name["Winoe"]

    assert (code_impl.model_provider, code_impl.model_name) == (
        "openai",
        "gpt-5.3-codex",
    )
    assert (winoe.model_provider, winoe.model_name) == ("openai", "gpt-5.2")
    assert (code_impl.model_provider, code_impl.model_name) != (
        winoe.model_provider,
        winoe.model_name,
    )


def test_winoe_prompt_assembly_includes_soul_persona_content() -> None:
    snapshots = build_ai_policy_snapshot(trial=SimpleNamespace(agent_snapshots=[]))
    winoe_prompt = snapshots["agents"]["winoeReport"]["resolvedInstructionsMd"]
    soul_text = (
        (
            Path(__file__).resolve().parents[3]
            / "app"
            / "ai"
            / "prompt_assets"
            / "v4"
            / "winoe_soul.md"
        )
        .read_text(encoding="utf-8")
        .strip()
    )

    assert "## Persona Governance" in winoe_prompt
    assert soul_text in winoe_prompt


@pytest.mark.asyncio
async def test_trial_creation_materializes_six_agent_snapshots(async_session):
    talent_partner = await create_talent_partner(
        async_session, email="snapshot-trial@test.com"
    )

    trial, _tasks, _job = await trial_service.create_trial_with_tasks(
        async_session, _payload(), talent_partner
    )

    snapshots = await list_trial_agent_snapshots(async_session, trial_id=trial.id)

    assert len(snapshots) == 6
    assert {snapshot.agent_name for snapshot in snapshots} == {
        "Prestart Project Brief Creator",
        "Design Doc Reviewer",
        "Code Implementation Reviewer",
        "Handoff + Demo Reviewer",
        "Reflection Reviewer",
        "Winoe",
    }
    for snapshot in snapshots:
        assert len(snapshot.prompt_content_hash) == 64
        assert len(snapshot.rubric_content_hash) == 64
        assert snapshot.locked_at is not None


@pytest.mark.asyncio
async def test_existing_trial_snapshot_content_survives_prompt_pack_changes(
    async_session,
    monkeypatch,
):
    talent_partner = await create_talent_partner(
        async_session, email="snapshot-immutability@test.com"
    )
    trial, _tasks, _job = await trial_service.create_trial_with_tasks(
        async_session, _payload(), talent_partner
    )
    snapshots = await list_trial_agent_snapshots(async_session, trial_id=trial.id)
    prestart_snapshot = next(
        snapshot
        for snapshot in snapshots
        if snapshot.agent_name == "Prestart Project Brief Creator"
    )

    monkeypatch.setattr(
        policy_snapshot_service,
        "build_prompt_pack_entry",
        lambda _agent_key: SimpleNamespace(
            prompt_version="mutated-v99",
            rubric_version="mutated-r99",
            policy_file_name="mutated-policy.md",
            policy_sha256="mutated-policy-sha256",
            schema_file_name="mutated-schema.json",
            schema_sha256="mutated-schema-sha256",
            instructions_sha256="mutated-instructions-sha256",
            rubric_sha256="mutated-rubric-sha256",
            instructions_md="## Mutated\nChanged prompt text.",
            rubric_md="## Mutated\nChanged rubric text.",
        ),
    )

    snapshot_json = build_ai_policy_snapshot(trial=trial)

    assert snapshot_json["agents"]["prestart"]["resolvedInstructionsMd"] == (
        prestart_snapshot.prompt_content
    )
    assert snapshot_json["agents"]["prestart"]["resolvedInstructionsMd"] != (
        "## Mutated\nChanged prompt text."
    )
    assert snapshot_json["agents"]["prestart"]["resolvedRubricMd"] == (
        prestart_snapshot.rubric_content
    )


@pytest.mark.asyncio
async def test_missing_trial_agent_snapshot_fails_clearly(async_session):
    talent_partner = await create_talent_partner(
        async_session, email="snapshot-missing@test.com"
    )
    trial, _tasks, _job = await trial_service.create_trial_with_tasks(
        async_session, _payload(), talent_partner
    )
    await delete_trial_agent_snapshots(async_session, trial_id=trial.id)
    await async_session.commit()

    with pytest.raises(LookupError, match="Missing trial agent snapshot"):
        await get_required_trial_agent_snapshot(
            async_session,
            trial_id=trial.id,
            agent_name="Winoe",
        )


@pytest.mark.asyncio
async def test_stale_trial_agent_snapshots_are_repaired_before_candidate_sessions(
    async_session,
):
    talent_partner = await create_talent_partner(
        async_session, email="snapshot-repair@test.com"
    )
    trial, _tasks, _job = await trial_service.create_trial_with_tasks(
        async_session, _payload(), talent_partner
    )
    current_snapshots = []
    for snapshot in await list_trial_agent_snapshots(async_session, trial_id=trial.id):
        if snapshot.agent_name == "Winoe":
            continue
        current_snapshots.append(
            {
                "agent_name": snapshot.agent_name,
                "agent_type": snapshot.agent_type,
                "model_provider": snapshot.model_provider,
                "model_name": snapshot.model_name,
                "model_version": snapshot.model_version,
                "prompt_version": snapshot.prompt_version,
                "prompt_content": snapshot.prompt_content,
                "prompt_content_hash": snapshot.prompt_content_hash,
                "rubric_version": snapshot.rubric_version,
                "rubric_content": snapshot.rubric_content,
                "rubric_content_hash": snapshot.rubric_content_hash,
                "locked_at": snapshot.locked_at,
            }
        )
    await replace_trial_agent_snapshots(
        async_session,
        trial_id=trial.id,
        snapshots=[
            {
                "agent_name": "Winoe",
                "agent_type": "synthesis",
                "model_provider": "openai",
                "model_name": "gpt-5.2",
                "model_version": "gpt-5.2",
                "prompt_version": "winoe-ai-pack-v1:winoeReport",
                "prompt_content": "# Legacy Winoe prompt",
                "prompt_content_hash": "legacy-prompt-hash",
                "rubric_version": "winoe-ai-pack-v1:winoeReport:rubric",
                "rubric_content": "# Legacy Winoe rubric",
                "rubric_content_hash": "legacy-rubric-hash",
                "locked_at": None,
            },
            *current_snapshots,
        ],
    )
    await async_session.commit()

    repaired = await trial_service.materialize_trial_agent_snapshots(
        async_session,
        trial=trial,
    )
    repaired_by_name = {snapshot.agent_name: snapshot for snapshot in repaired}

    assert repaired_by_name["Winoe"].prompt_version == "winoe-ai-pack-v4:winoeReport"
    assert (
        repaired_by_name["Winoe"].rubric_version
        == "winoe-ai-pack-v4:winoeReport:rubric"
    )
    assert repaired_by_name["Winoe"].prompt_content != "# Legacy Winoe prompt"
