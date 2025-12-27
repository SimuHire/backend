"""Add GitHub workspaces and template repo mapping

Revision ID: c4f2c76e5c3a
Revises: 3d7f8c5b6b8c
Create Date: 2025-02-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4f2c76e5c3a"
down_revision: Union[str, Sequence[str], None] = "3d7f8c5b6b8c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("template_repo", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "submissions",
        sa.Column("commit_sha", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "submissions",
        sa.Column("workflow_run_id", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "submissions",
        sa.Column("diff_summary_json", sa.Text(), nullable=True),
    )

    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("candidate_session_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("template_repo_full_name", sa.String(length=255), nullable=False),
        sa.Column("repo_full_name", sa.String(length=255), nullable=False),
        sa.Column("repo_id", sa.Integer(), nullable=True),
        sa.Column("default_branch", sa.String(length=120), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("latest_commit_sha", sa.String(length=100), nullable=True),
        sa.Column("last_workflow_run_id", sa.String(length=100), nullable=True),
        sa.Column("last_workflow_conclusion", sa.String(length=50), nullable=True),
        sa.Column("last_test_summary_json", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["candidate_session_id"],
            ["candidate_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "candidate_session_id",
            "task_id",
            name="uq_workspaces_session_task",
        ),
    )


def downgrade() -> None:
    op.drop_table("workspaces")
    op.drop_column("submissions", "diff_summary_json")
    op.drop_column("submissions", "workflow_run_id")
    op.drop_column("submissions", "commit_sha")
    op.drop_column("tasks", "template_repo")
