"""Create resume, page text, and audit tables.

Revision ID: 0001_resume_persistence
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_resume_persistence"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "resumes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("uploaded_by", sa.String(length=36), nullable=False),
        sa.Column("storage_key", sa.String(length=255), nullable=False, unique=True),
        sa.Column("sha256_checksum", sa.String(length=64), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("parser_engine", sa.String(length=32), nullable=False),
        sa.Column("processing_status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("tenant_id", "sha256_checksum", name="uq_resume_tenant_checksum"),
    )
    op.create_index("ix_resumes_tenant_id", "resumes", ["tenant_id"])
    op.create_index("ix_resumes_tenant_created", "resumes", ["tenant_id", "created_at", "id"])

    op.create_table(
        "resume_pages",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("resume_id", sa.String(length=36), sa.ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("text_content", sa.Text(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.UniqueConstraint("resume_id", "page_number", name="uq_resume_page_number"),
    )
    op.create_index("ix_resume_pages_resume_id", "resume_pages", ["resume_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=36), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_audit_logs_tenant_id", "audit_logs", ["tenant_id"])
    op.create_index("ix_audit_tenant_created", "audit_logs", ["tenant_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_tenant_created", table_name="audit_logs")
    op.drop_index("ix_audit_logs_tenant_id", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index("ix_resume_pages_resume_id", table_name="resume_pages")
    op.drop_table("resume_pages")
    op.drop_index("ix_resumes_tenant_created", table_name="resumes")
    op.drop_index("ix_resumes_tenant_id", table_name="resumes")
    op.drop_table("resumes")
