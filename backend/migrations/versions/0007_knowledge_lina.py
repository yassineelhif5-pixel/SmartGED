"""Phase 4: document chunks (full-text + pgvector), embedding model per provider, Lina conversations

Revision ID: 0007
Revises: 0006
"""
import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

BYPASS = "((select current_setting('app.bypass_rls', true)) = 'on')"
OWN = "(tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid))"
TABLES = ["document_chunks", "lina_conversations", "lina_messages"]


def upgrade() -> None:
    # pgvector lives in the ``extensions`` schema (Supabase convention, on the search_path of the app).
    # Creating the extension needs a privileged role: on a self-hosted database run once as superuser:
    #   CREATE SCHEMA IF NOT EXISTS extensions; CREATE EXTENSION vector WITH SCHEMA extensions;
    op.execute("CREATE SCHEMA IF NOT EXISTS extensions")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions")
    op.add_column("ai_providers", sa.Column("embedding_model", sa.String(length=120), nullable=True))

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("page_from", sa.Integer(), nullable=True),
        sa.Column("page_to", sa.Integer(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(), nullable=True),
        sa.Column("embedding_model", sa.String(length=160), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("search_vector", postgresql.TSVECTOR(),
                  sa.Computed("to_tsvector('simple', coalesce(text, ''))", persisted=True), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], name=op.f("fk_document_chunks_document_id_documents"),
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_document_chunks_tenant_id_tenants"),
                                ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_chunks")),
    )
    op.create_index("ix_document_chunks_document", "document_chunks", ["document_id", "version_number", "chunk_index"])
    op.create_index("ix_document_chunks_search", "document_chunks", ["search_vector"], postgresql_using="gin")
    op.create_index(op.f("ix_document_chunks_tenant_id"), "document_chunks", ["tenant_id"])

    op.create_table(
        "lina_conversations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("scope", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_lina_conversations_tenant_id_tenants"),
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_lina_conversations_user_id_users"),
                                ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lina_conversations")),
    )
    op.create_index("ix_lina_conversations_user", "lina_conversations", ["tenant_id", "user_id"])
    op.create_index("ix_lina_conversations_user_id_fk", "lina_conversations", ["user_id"])
    op.create_index(op.f("ix_lina_conversations_tenant_id"), "lina_conversations", ["tenant_id"])

    op.create_table(
        "lina_messages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["lina_conversations.id"],
                                name=op.f("fk_lina_messages_conversation_id_lina_conversations"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_lina_messages_tenant_id_tenants"),
                                ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lina_messages")),
    )
    op.create_index("ix_lina_messages_conversation", "lina_messages", ["conversation_id", "created_at"])
    op.create_index(op.f("ix_lina_messages_tenant_id"), "lina_messages", ["tenant_id"])

    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY tenant_isolation ON {table} USING ({BYPASS} OR {OWN}) WITH CHECK ({BYPASS} OR {OWN})")


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
    op.drop_table("lina_messages")
    op.drop_table("lina_conversations")
    op.drop_table("document_chunks")
    op.drop_column("ai_providers", "embedding_model")
