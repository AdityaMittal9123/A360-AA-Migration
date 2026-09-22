"""Pydantic response/request models."""
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict


class GroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    package: str
    count: int
    commands: str
    suggested_target: str
    target: str
    reason: str


class ArtifactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kind: str
    filename: str
    gap_count: int
    created_at: datetime


class BotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    file: str
    active_actions: int
    disabled_actions: int
    max_nesting_depth: int
    complexity_score: float
    complexity: str
    variables: list
    packages: dict
    calls: list
    called_by: list
    vault_references: list
    global_value_references: list
    narrative: Optional[str] = None
    narrative_source: Optional[str] = None
    classify_source: Optional[str] = None
    recommended_target: Optional[str] = None
    groups: list[GroupOut] = []
    artifacts: list[ArtifactOut] = []


class RunLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    stage: str
    message: str
    created_at: datetime


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    source_file: str
    status: str
    task_bots: int
    active_actions: int
    disabled_actions: int
    roots: list
    created_at: datetime
    bots: list[BotOut] = []
    runs: list[RunLogOut] = []


class ProjectSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    source_file: str
    status: str
    task_bots: int
    active_actions: int
    created_at: datetime


class TargetUpdate(BaseModel):
    target: str


class ConfigIn(BaseModel):
    llm: dict[str, Any]          # {profiles[], activeProfile, projectBots}
    env_prefix: str
    cloud_schema: str
    connection_refs: dict[str, str]
    robin_map: dict[str, str]
    pad_sample: str
