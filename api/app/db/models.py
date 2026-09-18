from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import SchemaItem

from app.db.base import Base


class Subsystem(Base):
    __tablename__: str = "subsystem"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)

    display_name: Mapped[str | None] = mapped_column(String(64), nullable=True)

    category: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__: tuple[SchemaItem, ...] = (
        CheckConstraint("name ~ '^[a-z0-9_]+$'", name="name_slug"),
        CheckConstraint("category IN ('top_level', 'subsystem')", name="category_enum"),
    )


class Node(Base):
    __tablename__: str = "node"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    subsystem_id: Mapped[int] = mapped_column(ForeignKey("subsystem.id"), nullable=False)

    name: Mapped[str] = mapped_column(String(64), nullable=False)

    category: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__: tuple[SchemaItem, ...] = (
        UniqueConstraint("subsystem_id", "name"),
        CheckConstraint("name ~ '^[a-z0-9_]+$'", name="name_slug"),
        CheckConstraint(
            "category IN "
            + "('algo', 'infra', 'run_settings', 'hardware', 'tcds', 'l1_menu', 'external')",
            name="category_enum",
        ),
    )


class NodeEdge(Base):
    __tablename__: str = "node_edge"

    parent_node_id: Mapped[int] = mapped_column(ForeignKey("node.id"), primary_key=True)

    child_node_id: Mapped[int] = mapped_column(ForeignKey("node.id"), primary_key=True)

    alias: Mapped[str] = mapped_column(String(64), primary_key=True)

    __table_args__: tuple[SchemaItem, ...] = (
        UniqueConstraint("parent_node_id", "alias"),
        CheckConstraint("parent_node_id <> child_node_id", name="no_self_loop"),
        CheckConstraint("alias ~ '^[a-z0-9_]+$'", name="alias_slug"),
    )


class Mode(Base):
    __tablename__: str = "mode"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    node_id: Mapped[int] = mapped_column(ForeignKey("node.id"), nullable=False)

    name: Mapped[str] = mapped_column(String(64), nullable=False)

    description: Mapped[str] = mapped_column(String(255), nullable=False)

    forked_from_key_id: Mapped[int | None] = mapped_column(nullable=True)

    created_by: Mapped[str] = mapped_column(ForeignKey("app_user.cern_login"), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    archived_by: Mapped[str | None] = mapped_column(
        ForeignKey("app_user.cern_login"), nullable=True
    )

    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__: tuple[SchemaItem, ...] = (
        ForeignKeyConstraint(
            ["forked_from_key_id", "node_id"], ["key.id", "key.node_id"], use_alter=True
        ),
        UniqueConstraint("id", "node_id"),
        UniqueConstraint("node_id", "name"),
        CheckConstraint("name ~ '^[a-z0-9_]+$'", name="name_slug"),
        CheckConstraint(
            "(archived_at IS NULL) = (archived_by IS NULL)",
            name="archival_complete",
        ),
    )


class Key(Base):
    __tablename__: str = "key"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    mode_id: Mapped[int] = mapped_column(nullable=False)

    node_id: Mapped[int] = mapped_column(nullable=False)

    version: Mapped[int] = mapped_column(nullable=False)

    label: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    payload: Mapped[str | None] = mapped_column(Text, nullable=True)

    staged_edit_id: Mapped[int] = mapped_column(
        ForeignKey("staged_edit.id"), unique=True, nullable=False
    )

    created_by: Mapped[str] = mapped_column(ForeignKey("app_user.cern_login"), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    comment: Mapped[str] = mapped_column(Text, nullable=False)

    validation_status: Mapped[str] = mapped_column(String(255), nullable=False)

    __table_args__: tuple[SchemaItem, ...] = (
        ForeignKeyConstraint(["mode_id", "node_id"], ["mode.id", "mode.node_id"]),
        UniqueConstraint("mode_id", "version"),
        UniqueConstraint("id", "mode_id"),
        UniqueConstraint("id", "node_id"),
        CheckConstraint(
            "label ~ '^[a-z0-9_]+/[a-z0-9_]+/[a-z0-9_]+/v[0-9]+$'", name="label_format"
        ),
        CheckConstraint("version > 0", name="version_positive"),
        CheckConstraint(
            "validation_status IN ('skipped', 'passed', 'failed')", name="validation_status_enum"
        ),
    )


class KeyChild(Base):
    __tablename__: str = "key_child"

    parent_key_id: Mapped[int] = mapped_column(primary_key=True)

    alias: Mapped[str] = mapped_column(String(64), primary_key=True)

    child_key_id: Mapped[int] = mapped_column(nullable=False)

    parent_node_id: Mapped[int] = mapped_column(nullable=False)

    child_node_id: Mapped[int] = mapped_column(nullable=False)

    __table_args__: tuple[SchemaItem, ...] = (
        ForeignKeyConstraint(["parent_key_id", "parent_node_id"], ["key.id", "key.node_id"]),
        ForeignKeyConstraint(["child_key_id", "child_node_id"], ["key.id", "key.node_id"]),
        ForeignKeyConstraint(
            ["parent_node_id", "child_node_id", "alias"],
            ["node_edge.parent_node_id", "node_edge.child_node_id", "node_edge.alias"],
        ),
    )


class Changeset(Base):
    __tablename__: str = "changeset"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    created_by: Mapped[str] = mapped_column(ForeignKey("app_user.cern_login"), nullable=False)

    committed_with_roles: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__: tuple[SchemaItem, ...] = (
        CheckConstraint(
            "(committed_at IS NULL) = (committed_with_roles IS NULL)", name="commit_complete"
        ),
        Index(
            "uq_changeset_created_by_open",
            "created_by",
            unique=True,
            postgresql_where=text("committed_at IS NULL"),
        ),
    )


class StagedEdit(Base):
    __tablename__: str = "staged_edit"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    changeset_id: Mapped[int] = mapped_column(
        ForeignKey("changeset.id", ondelete="CASCADE"), nullable=False
    )

    mode_id: Mapped[int] = mapped_column(ForeignKey("mode.id"), nullable=False)

    base_key_id: Mapped[int | None] = mapped_column(nullable=True)

    copied_from_key_id: Mapped[int | None] = mapped_column(
        ForeignKey("key.id", use_alter=True), nullable=True
    )

    expected_version: Mapped[int] = mapped_column(nullable=False)

    proposed_payload: Mapped[str | None] = mapped_column(Text, nullable=True)

    proposed_children: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)

    comment: Mapped[str] = mapped_column(Text, nullable=False)

    validation_status: Mapped[str] = mapped_column(String(255), nullable=False)

    __table_args__: tuple[SchemaItem, ...] = (
        ForeignKeyConstraint(["base_key_id", "mode_id"], ["key.id", "key.mode_id"], use_alter=True),
        CheckConstraint(
            "validation_status IN ('skipped', 'passed', 'failed')", name="validation_status_enum"
        ),
        CheckConstraint(
            "proposed_payload IS NOT NULL OR proposed_children IS NOT NULL",
            name="proposes_something",
        ),
        CheckConstraint("expected_version > 0", name="expected_version_positive"),
    )


class StagedArchival(Base):
    __tablename__: str = "staged_archival"

    changeset_id: Mapped[int] = mapped_column(
        ForeignKey("changeset.id", ondelete="CASCADE"), primary_key=True
    )

    mode_id: Mapped[int] = mapped_column(ForeignKey("mode.id"), primary_key=True)

    archived: Mapped[bool] = mapped_column(nullable=False)


class AppUser(Base):
    __tablename__: str = "app_user"

    cern_login: Mapped[str] = mapped_column(String(64), primary_key=True)

    display_name: Mapped[str] = mapped_column(String(64), nullable=False)


class Role(Base):
    __tablename__: str = "role"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)


class RoleSubsystem(Base):
    __tablename__: str = "role_subsystem"

    role_id: Mapped[int] = mapped_column(ForeignKey("role.id"), primary_key=True)

    subsystem_id: Mapped[int] = mapped_column(ForeignKey("subsystem.id"), primary_key=True)
