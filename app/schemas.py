from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class CanonicalStage(str, Enum):
    IDEATION = "Ideation & Planning"
    MVP_IN_PROGRESS = "MVP In Progress"
    DEBUGGING = "Debugging & Stabilization"
    READY_FOR_NEXT = "Ready for Next Stage"
    MAINTENANCE = "Maintenance / Parked"

class DomainTag(str, Enum):
    GENERAL = "General"
    FAMILY = "Family"
    WEALTH = "Wealth"
    HOBBIES = "Hobbies"
    HARDWARE = "Hardware"
    WORK = "Work"
    DEVOPS = "DevOps"

class RepoStatusExtraction(BaseModel):
    name_with_owner: str = Field(description="Full repo identifier (e.g. owner/repo)")
    detected_stage: CanonicalStage = Field(description="Classified canonical lifecycle stage")
    confidence: float = Field(default=0.9, description="Confidence score from 0.0 to 1.0")
    summary: str = Field(description="2-3 sentence technical overview of current progress and active state")
    blockers: List[str] = Field(default_factory=list, description="Identified architectural or progress blockers")
    key_milestones: List[str] = Field(default_factory=list, description="Key completed or upcoming milestones")

class BatchRepoStatusResponse(BaseModel):
    repos: List[RepoStatusExtraction] = Field(description="List of status extractions for each repo in the batch")

class QuickWinItem(BaseModel):
    title: str = Field(description="Actionable task title (< 2 hours)")
    rationale: str = Field(description="Why this delivers immediate high ROI")
    antigravity_prompt: str = Field(description="Complete, copy-ready prompt for Antigravity AI pair programmer")
    est_hours: float = Field(default=1.5, description="Estimated hours to complete")

class MilestoneItem(BaseModel):
    title: str = Field(description="Major feature or architecture milestone")
    rationale: str = Field(description="Strategic importance to next phase")
    antigravity_prompt: str = Field(description="Complete, copy-ready prompt for Antigravity AI pair programmer")

class ProjectEnhancementPlan(BaseModel):
    repo_name: str = Field(description="Repository name")
    quick_wins: List[QuickWinItem] = Field(default_factory=list, description="1-3 quick high-ROI wins")
    next_milestones: List[MilestoneItem] = Field(default_factory=list, description="2-3 next milestone steps")

class SynergyItem(BaseModel):
    title: str = Field(description="Shared component or cross-repo integration opportunity")
    affected_repos: List[str] = Field(description="Names of repositories that benefit")
    rationale: str = Field(description="Architectural rationale and duplication eliminated")
    antigravity_prompt: str = Field(description="Ready prompt to implement the cross-project shared module")

class WeekendFinisherItem(BaseModel):
    repo_name: str = Field(description="Repository close to a clean finish")
    title: str = Field(description="Specific milestone to wrap up")
    rationale: str = Field(description="Why this can be wrapped up quickly for high impact")
    antigravity_prompt: str = Field(description="Antigravity prompt to finish the feature")
    est_hours: float = Field(default=2.0, description="Estimated hours (< 3 hours)")

class RoadmapItem(BaseModel):
    repo_name: str = Field(description="Repository name")
    next_stage: CanonicalStage = Field(description="Recommended target stage")
    rationale: str = Field(description="Strategic next step")
    antigravity_prompt: str = Field(description="Antigravity prompt to initiate next stage")

class CrossPortfolioStrategy(BaseModel):
    synergies: List[SynergyItem] = Field(default_factory=list, description="Shared components across repos")
    weekend_finishers: List[WeekendFinisherItem] = Field(default_factory=list, description="High-completion projects to finish")
    next_stage_roadmap: List[RoadmapItem] = Field(default_factory=list, description="Recommended next stages across portfolio")

# API Request/Response Schemas
class ProjectUpdateSchema(BaseModel):
    override_stage: Optional[str] = None
    domain_tag: Optional[str] = None
    ai_enabled: Optional[bool] = None

class ActionItemUpdateSchema(BaseModel):
    is_completed: Optional[bool] = None
    is_dismissed: Optional[bool] = None

class EnhancementStatusUpdateSchema(BaseModel):
    status: str # 'suggested', 'accepted', 'completed', 'dismissed'
