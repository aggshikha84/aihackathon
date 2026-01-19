from pydantic import BaseModel, Field
from typing import Literal, List, Optional

class EvidenceItem(BaseModel):
    type: Literal["log", "kb"]
    snippet: str
    source: str

class PlanStep(BaseModel):
    title: str
    command: str
    purpose: str
    expected: str
    risk: Literal["low", "med", "medium", "high"] = "low"

class InfoRequest(BaseModel):
    title: str
    command: str
    why: str

class AnalysisResponse(BaseModel):
    status: Literal["final", "need_more_info"]
    root_cause: str
    confidence: Literal["high", "medium", "low"]
    reasoning_summary: str
    evidence: List[EvidenceItem] = Field(default_factory=list)
    plan_steps: List[PlanStep] = Field(default_factory=list)
    info_requests: List[InfoRequest] = Field(default_factory=list)
