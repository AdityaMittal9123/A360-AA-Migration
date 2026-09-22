"""ORM models. One Project per uploaded A360 export; Bots belong to a Project;
ActionGroups hold the target classification (suggested + approved); Artifacts hold generated code."""
from datetime import datetime
from sqlalchemy import String, Integer, Float, Text, ForeignKey, DateTime, JSON, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    source_file: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(30), default="parsed")   # parsed | understood | converted
    task_bots: Mapped[int] = mapped_column(Integer, default=0)
    active_actions: Mapped[int] = mapped_column(Integer, default=0)
    disabled_actions: Mapped[int] = mapped_column(Integer, default=0)
    roots: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    bots: Mapped[list["Bot"]] = relationship(back_populates="project", cascade="all, delete-orphan", order_by="Bot.id")
    runs: Mapped[list["RunLog"]] = relationship(back_populates="project", cascade="all, delete-orphan", order_by="RunLog.id")


class Bot(Base):
    __tablename__ = "bots"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(String(300))
    file: Mapped[str] = mapped_column(String(400))
    active_actions: Mapped[int] = mapped_column(Integer)
    disabled_actions: Mapped[int] = mapped_column(Integer)
    max_nesting_depth: Mapped[int] = mapped_column(Integer)
    complexity_score: Mapped[float] = mapped_column(Float)
    complexity: Mapped[str] = mapped_column(String(10))
    variables: Mapped[list] = mapped_column(JSON, default=list)
    packages: Mapped[dict] = mapped_column(JSON, default=dict)
    calls: Mapped[list] = mapped_column(JSON, default=list)
    called_by: Mapped[list] = mapped_column(JSON, default=list)
    vault_references: Mapped[list] = mapped_column(JSON, default=list)
    global_value_references: Mapped[list] = mapped_column(JSON, default=list)
    actions: Mapped[list] = mapped_column(JSON, default=list)        # full normalised action list
    narrative: Mapped[str | None] = mapped_column(Text, nullable=True)
    narrative_source: Mapped[str | None] = mapped_column(String(200), nullable=True)  # model profile label | rules
    classify_source: Mapped[str | None] = mapped_column(String(200), nullable=True)   # model profile label | rules
    recommended_target: Mapped[str | None] = mapped_column(String(40), nullable=True)
    project: Mapped["Project"] = relationship(back_populates="bots")
    groups: Mapped[list["ActionGroup"]] = relationship(back_populates="bot", cascade="all, delete-orphan", order_by="ActionGroup.id")
    artifacts: Mapped[list["Artifact"]] = relationship(back_populates="bot", cascade="all, delete-orphan")


class ActionGroup(Base):
    __tablename__ = "action_groups"
    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"))
    package: Mapped[str] = mapped_column(String(100))
    count: Mapped[int] = mapped_column(Integer)
    commands: Mapped[str] = mapped_column(String(400))
    suggested_target: Mapped[str] = mapped_column(String(20))
    target: Mapped[str] = mapped_column(String(20))              # approved (editable)
    reason: Mapped[str] = mapped_column(String(300))
    bot: Mapped["Bot"] = relationship(back_populates="groups")


class Artifact(Base):
    __tablename__ = "artifacts"
    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"))
    kind: Mapped[str] = mapped_column(String(20))                # cloud | robin
    filename: Mapped[str] = mapped_column(String(300))
    content: Mapped[str] = mapped_column(Text)
    gap_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    bot: Mapped["Bot"] = relationship(back_populates="artifacts")


class Config(Base):
    """Single-row key/value store for schemas, mapping table and LLM settings."""
    __tablename__ = "config"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict | list | str] = mapped_column(JSON)


class RunLog(Base):
    __tablename__ = "run_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    stage: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    project: Mapped["Project"] = relationship(back_populates="runs")


class LLMCall(Base):
    """Audit trail for every model call (Bring Your Own LLM). Bodies stored only if governance.logPrompts is on."""
    __tablename__ = "llm_calls"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    bot_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    task: Mapped[str] = mapped_column(String(20))                 # understand | classify | gapfill | test
    profile_id: Mapped[str] = mapped_column(String(80))
    profile_label: Mapped[str] = mapped_column(String(200))
    provider: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(10))               # ok | error | blocked
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    request: Mapped[str | None] = mapped_column(Text, nullable=True)
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
