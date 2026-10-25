import os
import time
import json
import logging
from typing import List, Dict, Any, Optional, Type
from dotenv import load_dotenv
from pydantic import BaseModel
from openai import OpenAI

# Reload .env if modified
load_dotenv(override=True)

from app.schemas import (
    CanonicalStage,
    BatchRepoStatusResponse,
    ProjectEnhancementPlan,
    CrossPortfolioStrategy,
)
from app.db import log_api_usage

logger = logging.getLogger("openrouter_service")
logging.basicConfig(level=logging.INFO)

# Free-tier model waterfall across OpenRouter (strictly ordered)
FREE_TIER_WATERFALL = [
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "nvidia/nemotron-3.5-super-vl:free",
    "thinkingmachines/inkling:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "openrouter/free",
]

DEFAULT_PRIMARY_MODEL = os.environ.get("OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free").strip() or "nvidia/nemotron-3-ultra-550b-a55b:free"

CASCADE_MODELS = [
    DEFAULT_PRIMARY_MODEL,
    *[m for m in FREE_TIER_WATERFALL if m != DEFAULT_PRIMARY_MODEL]
]


class OpenRouterEngine:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "").strip()
        self.models = CASCADE_MODELS
        self._client: Optional[OpenAI] = None
        self._last_call_time = 0.0
        self._min_interval_seconds = 1.0

    @property
    def client(self) -> OpenAI:
        load_dotenv(override=True)
        current_key = self.api_key or os.environ.get("OPENROUTER_API_KEY", "").strip()
        if not current_key or current_key.startswith("sk-or-v1-your_"):
            raise ValueError(
                "OpenRouter API key is not configured. Please set your OPENROUTER_API_KEY in .env"
            )
        if self._client is None or self._client.api_key != current_key:
            self._client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=current_key,
                default_headers={
                    "HTTP-Referer": "http://localhost:8000",
                    "X-Title": "Project Command Center",
                }
            )
        return self._client

    def _pace_request(self):
        """Gentle pacing between outgoing OpenRouter API requests."""
        now = time.time()
        elapsed = now - self._last_call_time
        if elapsed < self._min_interval_seconds:
            time.sleep(self._min_interval_seconds - elapsed)
        self._last_call_time = time.time()

    def generate_structured(
        self,
        prompt: str,
        response_schema: Type[BaseModel],
        operation_type: str = "structured_call",
        system_instruction: Optional[str] = None,
    ) -> BaseModel:
        """
        Execute structured prompt generation across OpenRouter models with waterfall fallback,
        JSON validation, and SQLite telemetry logging.
        """
        last_error = None
        schema_json = json.dumps(response_schema.model_json_schema(), indent=2)

        sys_content = (
            (system_instruction or "You are an expert Lead Software Architect and Portfolio Strategist.")
            + "\n\nCRITICAL OUTPUT REQUIREMENT:\n"
            + "You MUST reply ONLY with valid JSON conforming strictly to this JSON Schema:\n"
            + schema_json
            + "\nDo NOT include markdown backticks or commentary outside the JSON."
        )

        for idx, model_id in enumerate(self.models):
            try:
                self._pace_request()
                logger.info(f"Invoking OpenRouter model '{model_id}' (Tier {idx + 1}) for '{operation_type}'...")

                response = self.client.chat.completions.create(
                    model=model_id,
                    messages=[
                        {"role": "system", "content": sys_content},
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.2,
                )

                msg = response.choices[0].message
                content = (msg.content or "").strip()
                if not content:
                    # Fallback to reasoning field if present on thinking models
                    reasoning = getattr(msg, "reasoning", "") or ""
                    if "{" in reasoning and "}" in reasoning:
                        start = reasoning.find("{")
                        end = reasoning.rfind("}") + 1
                        content = reasoning[start:end].strip()

                # Clean any markdown fences if present
                content_clean = content
                if content_clean.startswith("```json"):
                    content_clean = content_clean[7:]
                if content_clean.startswith("```"):
                    content_clean = content_clean[3:]
                if content_clean.endswith("```"):
                    content_clean = content_clean[:-3]
                content_clean = content_clean.strip()

                # Extract balanced JSON substring if there is surrounding commentary
                if not content_clean.startswith("{") and "{" in content_clean:
                    start = content_clean.find("{")
                    end = content_clean.rfind("}") + 1
                    content_clean = content_clean[start:end].strip()

                parsed_data = response_schema.model_validate_json(content_clean)

                # Usage tokens
                prompt_tokens = 0
                completion_tokens = 0
                if hasattr(response, "usage") and response.usage:
                    prompt_tokens = response.usage.prompt_tokens or 0
                    completion_tokens = response.usage.completion_tokens or 0

                log_api_usage(
                    model_name=model_id,
                    operation_type=operation_type,
                    prompt_tokens=prompt_tokens,
                    candidates_tokens=completion_tokens,
                    status="success"
                )

                return parsed_data

            except Exception as err:
                msg = str(err)
                logger.warning(f"OpenRouter Tier {idx + 1} ({model_id}) failed for '{operation_type}': {msg}")
                last_error = err

                status_label = "rate_limited" if "429" in msg or "quota" in msg.lower() else "failed"
                log_api_usage(
                    model_name=model_id,
                    operation_type=operation_type,
                    prompt_tokens=0,
                    candidates_tokens=0,
                    status=status_label
                )

                # If this was the last model, raise
                if idx == len(self.models) - 1:
                    raise RuntimeError(f"All OpenRouter models exhausted for '{operation_type}': {last_error}")

        raise RuntimeError(f"Failed to generate structured response from OpenRouter: {last_error}")


# Singleton engine instance
ai_engine = OpenRouterEngine()


def analyze_repo_batch(batch_items: List[Dict[str, Any]]) -> BatchRepoStatusResponse:
    """
    Batched Status Extraction across repositories via OpenRouter.
    Classifies repos into canonical lifecycle stages with summaries, blockers, and milestones.
    """
    system_instruction = (
        "You are an expert Lead Software Architect and Portfolio Strategist analyzing GitHub repositories. "
        "Your task is to accurately categorize repositories into canonical lifecycle stages: "
        "'Ideation & Planning', 'MVP In Progress', 'Debugging & Stabilization', 'Ready for Next Stage', or 'Maintenance / Parked'.\n\n"
        "CRITICAL CLASSIFICATION GROUND RULES:\n"
        "1. GROUND IN ACTUAL CODE & COMMITS: If a repository contains substantial source code (e.g. main.py/app.py, dozens of code files, test suites, feeds configuration) or a significant commit history (>= 15 commits), it is a functioning system. If its core platform has been delivered and documented for future evolution (such as Research Aggregator or NewsFeed), classify it as 'Ready for Next Stage'. Never classify an active codebase as 'Ideation & Planning'.\n"
        "2. ACTIVE PROTOTYPES & SPRINTS: If a repository has architecture specs (e.g. SPEC_*.md) with initial active commits/tests underway (like Arcturus), classify as 'MVP In Progress'.\n"
        "3. IDEATION & PLANNING THRESHOLD: Reserve 'Ideation & Planning' exclusively for empty stubs, pure initial scaffolding, or projects with 0-1 commits and no implementation code.\n"
        "4. Extract technical summaries, identified architectural blockers, and key milestone items based on the provided documentation, code files, and git history."
    )

    batch_payload = []
    for item in batch_items:
        batch_payload.append({
            "name_with_owner": item.get("name_with_owner"),
            "description": item.get("description", ""),
            "active_branch": item.get("active_branch", "main"),
            "commit_count": item.get("commit_count", 1),
            "root_files": item.get("root_files", []),
            "directories": item.get("directories", []),
            "metrics": item.get("metrics", {}),
            "open_issues": item.get("open_issues", []),
            "completion_pct": item.get("completion_pct", 0.0),
            "sanitized_docs": item.get("sanitized_docs", {}),
        })

    prompt = (
        "Analyze the following batch of software repositories. For each repository, provide:\n"
        "1. Canonical lifecycle stage ('Ideation & Planning', 'MVP In Progress', 'Debugging & Stabilization', 'Ready for Next Stage', or 'Maintenance / Parked')\n"
        "2. Confidence score (0.0 to 1.0)\n"
        "3. Concise 2-3 sentence technical overview of current progress and active state\n"
        "4. Bulleted architectural blockers or roadblocks\n"
        "5. Key milestones completed or in-progress\n\n"
        f"REPOSITORIES BATCH DATA (JSON):\n{json.dumps(batch_payload, indent=2)}"
    )

    return ai_engine.generate_structured(
        prompt=prompt,
        response_schema=BatchRepoStatusResponse,
        operation_type="batch_status",
        system_instruction=system_instruction
    )


def generate_repo_enhancements(repo_data: Dict[str, Any]) -> ProjectEnhancementPlan:
    """
    On-Demand Single-Project Deep Dive via OpenRouter.
    Generates Quick Wins (< 2 Hours), Next Milestone Architecture, and Copy-Ready Antigravity Prompts.
    """
    system_instruction = (
        "You are Antigravity's Lead Autonomous Pairing Architect. You generate actionable, high-ROI engineering enhancement "
        "plans for software repositories. Every enhancement MUST include a detailed, complete 'antigravity_prompt' written in "
        "first-person direct pair programming instructions with exact files to touch, step-by-step logic, edge cases, and verification commands."
    )

    prompt = (
        f"Generate a deep-dive engineering enhancement plan for repository: {repo_data.get('name_with_owner')}\n\n"
        f"DESCRIPTION: {repo_data.get('description', '')}\n"
        f"CURRENT STAGE: {repo_data.get('stage', 'MVP In Progress')}\n"
        f"COMPLETION PERCENTAGE: {repo_data.get('completion_pct', 0.0)}%\n"
        f"DIRECTORIES: {json.dumps(repo_data.get('directories', []))}\n"
        f"ROOT FILES: {json.dumps(repo_data.get('root_files', []))}\n"
        f"OPEN ISSUES: {json.dumps(repo_data.get('open_issues', []))}\n"
        f"HARVESTED DOCUMENTATION:\n{json.dumps(repo_data.get('sanitized_docs', {}), indent=2)}\n\n"
        "OUTPUT REQUIREMENTS:\n"
        "1. 2 to 3 'quick_wins' that can be built in under 2 hours with immediate developer ROI.\n"
        "2. 2 to 3 'next_milestones' advancing the core product to its next major capability.\n"
        "3. Every item MUST have a comprehensive, copy-ready 'antigravity_prompt' that a developer can paste directly into Antigravity."
    )

    return ai_engine.generate_structured(
        prompt=prompt,
        response_schema=ProjectEnhancementPlan,
        operation_type="deep_dive",
        system_instruction=system_instruction
    )


def generate_cross_portfolio_strategy(all_repos: List[Dict[str, Any]]) -> CrossPortfolioStrategy:
    """
    Single-Call Cross-Portfolio Strategist via OpenRouter.
    Identifies cross-project synergies/shared modules, weekend finishers (< 2 hours), and next-stage roadmaps.
    """
    system_instruction = (
        "You are the Chief Technology Officer and Cross-Portfolio Architect for a developer's suite of applications. "
        "Your task is to analyze the entire repository portfolio at once, finding cross-cutting synergies, shared library "
        "extractions, quick weekend finish lines, and prioritized next milestones. All implementation prompts must be ready for Antigravity."
    )

    summaries = []
    for r in all_repos:
        summaries.append({
            "name": r.get("name_with_owner"),
            "domain": r.get("domain_tag", "General"),
            "stage": r.get("stage", "MVP In Progress"),
            "completion_pct": r.get("completion_pct", 0.0),
            "description": r.get("description", ""),
            "summary": r.get("summary", ""),
            "blockers": r.get("blockers", []),
        })

    prompt = (
        "Analyze the following portfolio of software projects and identify strategic portfolio-wide engineering opportunities:\n\n"
        "1. 'synergies': Find 2-4 reusable components, shared libraries, or integration bridges between 2 or more projects.\n"
        "2. 'weekend_finishers': Identify 2-4 projects with high completion (or high leverage) that can reach a major milestone in < 2.5 hours.\n"
        "3. 'next_stage_roadmap': Outline high-impact next-stage goals for the key projects.\n\n"
        "Provide copy-ready Antigravity prompts for all items.\n\n"
        f"PORTFOLIO DIGEST:\n{json.dumps(summaries, indent=2)}"
    )

    return ai_engine.generate_structured(
        prompt=prompt,
        response_schema=CrossPortfolioStrategy,
        operation_type="portfolio_brainstorm",
        system_instruction=system_instruction
    )


# Alias for convenience
openrouter_service = ai_engine
