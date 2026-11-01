"""initial schema: users, notes, items, google_accounts

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_table(
        "notes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_notes_user_id", "notes", ["user_id"])
    op.create_table(
        "items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("note_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("notes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.Column("done", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_items_note_id", "items", ["note_id"])
    op.create_table(
        "google_accounts",
        sa.Column("owner", sa.String(64), primary_key=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("refresh_token", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("google_accounts")
    op.drop_table("items")
    op.drop_table("notes")
    op.drop_table("users")
