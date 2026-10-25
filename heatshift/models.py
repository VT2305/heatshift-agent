from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field


class Intensity(str, Enum):
    LIGHT = "light"
    MODERATE = "moderate"
    HEAVY = "heavy"


class Environment(str, Enum):
    INDOOR = "indoor"
    SHADED = "shaded"
    OUTDOOR = "outdoor"


class Worker(BaseModel):
    worker_id: str
    name: str
    team: str
    skills: list[str]
    acclimatisation_status: Literal["acclimatised", "acclimatising"]
    fit_for_outdoor_work: bool = True
    current_zone: str
    shift_start: str = "08:00"
    shift_end: str = "17:00"
    outdoor_minutes_since_recovery: int = 0
    last_recovery_end: str | None = None
    status: Literal["available", "unavailable"] = "available"


class Task(BaseModel):
    task_id: str
    name: str
    zone: str
    environment: Environment
    intensity: Intensity
    duration_minutes: int
    workers_required: int
    required_skills: list[str]
    earliest_start: str
    deadline: str
    fixed: bool = False
    dependencies: list[str] = Field(default_factory=list)
    priority: int = 3


class HeatReading(BaseModel):
    timestamp: datetime
    source: Literal["NEA_WBGT", "CACHED_NEA_WBGT", "SIMULATED"]
    station_id: str = "demo"
    wbgt_c: float
    heat_band: str
    air_temperature_c: float | None = None
    is_simulated_forecast: bool = False


class PlanItem(BaseModel):
    task_id: str
    start: str
    end: str
    worker_ids: list[str]
    note: str | None = None


class RequiredBreak(BaseModel):
    worker_ids: list[str]
    start: str
    minutes: int
    reason: str


class PlanMetrics(BaseModel):
    delay_minutes: int = 0
    tasks_moved: int = 0
    worker_reassignments: int = 0
    overtime_minutes: int = 0
    exposure_proxy_before: float = 0
    exposure_proxy_after: float = 0
    exposure_proxy_reduction_pct: float = 0
    compliance: bool = False


class WorkPlan(BaseModel):
    plan_id: str
    version: int
    generated_at: datetime
    trigger: str
    status: Literal[
        "current",
        "pending_supervisor_approval",
        "approved",
        "rejected",
    ]
    items: list[PlanItem]
    required_breaks: list[RequiredBreak] = Field(default_factory=list)
    metrics: PlanMetrics = Field(default_factory=PlanMetrics)
    explanation: str = ""


class SiteState(BaseModel):
    site_id: str
    workers: list[Worker]
    tasks: list[Task]
    current_plan: WorkPlan
    heat_series: list[HeatReading]
    rest_zone_capacity: int = 12


class SafetyConstraint(BaseModel):
    rule_id: str
    description: str
    hard: bool = True
    rest_minutes_per_hour: int = 0
    hydration_ml_per_hour: int = 0
    applies: bool = True
    source_version: str


class ValidationIssue(BaseModel):
    code: str
    message: str
    severity: Literal["error", "warning"] = "error"


class ValidationResult(BaseModel):
    valid: bool
    checks: int
    issues: list[ValidationIssue] = Field(default_factory=list)


class ImpactMetrics(BaseModel):
    delay_minutes: int
    tasks_moved: int
    worker_reassignments: int
    overtime_minutes: int
    exposure_proxy_before: float
    exposure_proxy_after: float
    exposure_proxy_reduction_pct: float
    compliance: bool


class DecisionCertificate(BaseModel):
    decision_id: str
    trigger: str
    affected_tasks: list[str]
    rule_refs: list[str]
    validation: ValidationResult
    impact: ImpactMetrics
    data_provenance: str
    ruleset_version: str
    human_approval: Literal["PENDING", "APPROVED", "REJECTED"]
    tool_timeline: list[dict]


class SupervisorDecision(BaseModel):
    decision_id: str
    status: Literal[
        "MONITOR",
        "CHANGE_RECOMMENDED",
        "BLOCKED_MISSING_DATA",
        "NO_FEASIBLE_PLAN",
    ]
    trigger: str
    affected_tasks: list[str] = Field(default_factory=list)
    rule_refs: list[str] = Field(default_factory=list)
    impact: ImpactMetrics | None = None
    confidence: Literal["HIGH", "MEDIUM", "LOW"] = "HIGH"
    data_quality: Literal["LIVE", "CACHED", "SIMULATED"] = "SIMULATED"
    requires_approval: bool = True
    supervisor_message: str
    proposed_plan: WorkPlan | None = None
    certificate: DecisionCertificate | None = None
