import os
import time
import json
import logging
from typing import List, Dict, Any, Optional, Tuple, Type
from pydantic import BaseModel
from google import genai
from google.genai import types
from google.genai import errors as genai_errors

from app.schemas import (
    CanonicalStage,
    BatchRepoStatusResponse,
    ProjectEnhancementPlan,
    CrossPortfolioStrategy,
)
from app.db import log_api_usage

logger = logging.getLogger("gemini_service")
logging.basicConfig(level=logging.INFO)

# Priority waterfall fallback chain
CASCADE_MODELS = [
    "gemini-3.8-flash",       # Tier 1: Primary high-reasoning engine
    "gemini-3.5-flash",       # Tier 2: High-speed fallback
    "gemini-3.1-flash-lite",  # Tier 3: Resilient backup
    "gemini-flash-latest"     # Tier 4: Low-latency emergency fallback
]

class GeminiFreeTierEngine:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.models = CASCADE_MODELS
        self._client: Optional[genai.Client] = None
        self._last_call_time = 0.0
        # 4.0s minimum gap between calls to stay comfortably within 15 RPM
        self._min_interval_seconds = 4.0

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            if self.api_key:
                self._client = genai.Client(api_key=self.api_key)
            else:
                self._client = genai.Client()
        return self._client

    def _pace_request(self):
        """Enforce rate-limiting interval between outgoing API calls."""
        now = time.time()
        elapsed = now - self._last_call_time
        if elapsed < self._min_interval_seconds:
            sleep_needed = self._min_interval_seconds - elapsed
            logger.info(f"Rate-limit pacing: sleeping {sleep_needed:.2f}s...")
            time.sleep(sleep_needed)
        self._last_call_time = time.time()

    def generate_structured(
        self,
        prompt: str,
        response_schema: Type[BaseModel],
        operation_type: str = "structured_call",
        system_instruction: Optional[str] = None,
    ) -> BaseModel:
        """
        Execute structured prompt generation across waterfall models with automatic fallback,
        rate-limit pacing, and SQLite telemetry logging.
        """
        last_error = None

        for idx, model_id in enumerate(self.models):
            try:
                self._pace_request()
                logger.info(f"Invoking {model_id} (Tier {idx + 1}) for '{operation_type}'...")

                config_kwargs: Dict[str, Any] = {
                    "response_mime_type": "application/json",
                    "response_schema": response_schema,
                    "temperature": 0.2,
                }
                if system_instruction:
                    config_kwargs["system_instruction"] = system_instruction

                response = self.client.models.generate_content(
                    model=model_id,
                    contents=prompt,
                    config=types.GenerateContentConfig(**config_kwargs)
                )

                prompt_tokens = 0
                candidates_tokens = 0
                if hasattr(response, "usage_metadata") and response.usage_metadata:
                    prompt_tokens = getattr(response.usage_metadata, "prompt_token_count", 0)
                    candidates_tokens = getattr(response.usage_metadata, "candidates_token_count", 0)

                # Parse result
                parsed_data = None
                if hasattr(response, "parsed") and response.parsed is not None:
                    parsed_data = response.parsed
                else:
                    text_content = response.text or "{}"
                    parsed_data = response_schema.model_validate_json(text_content)

                # Telemetry log
                log_api_usage(
                    model_name=model_id,
                    operation_type=operation_type,
                    prompt_tokens=prompt_tokens,
                    candidates_tokens=candidates_tokens,
                    status="success"
                )

                return parsed_data

            except (genai_errors.APIError, Exception) as err:
                msg = str(err)
                logger.warning(f"Tier {idx + 1} ({model_id}) failed for '{operation_type}': {msg}")
                last_error = err

                # Log failure
                status_label = "rate_limited" if "429" in msg or "quota" in msg.lower() else "failed"
                log_api_usage(
                    model_name=model_id,
                    operation_type=operation_type,
                    prompt_tokens=0,
                    candidates_tokens=0,
                    status=status_label
                )

                # If 503 spike, short backoff and retry once
                if "503" in msg or "demand" in msg.lower():
                    time.sleep(3.0)
                    try:
                        self._pace_request()
                        response = self.client.models.generate_content(
                            model=model_id,
                            contents=prompt,
                            config=types.GenerateContentConfig(
                                response_mime_type="application/json",
                                response_schema=response_schema,
                                temperature=0.2
                            )
                        )
                        parsed = getattr(response, "parsed", None)
                        if parsed is None:
                            parsed = response_schema.model_validate_json(response.text or "{}")
                        return parsed
                    except Exception:
                        pass

                # If last model in chain, raise
                if idx == len(self.models) - 1:
                    raise RuntimeError(f"All Gemini models exhausted for '{operation_type}': {last_error}")

        raise RuntimeError(f"Failed to generate structured response: {last_error}")


# Singleton engine instance
gemini_engine = GeminiFreeTierEngine()


def analyze_repo_batch(batch_items: List[Dict[str, Any]]) -> BatchRepoStatusResponse:
    """
    Batched Cold-Start / Changed Status Extraction (Up to 8 repos per call).
    Classifies repos into canonical lifecycle stages with summaries, blockers, and milestones.
    """
    system_instruction = (
        "You are an expert Lead Software Architect and Portfolio Strategist analyzing GitHub repositories. "
        "Your task is to accurately categorize repositories into canonical lifecycle stages: "
        "'Ideation & Planning', 'MVP In Progress', 'Debugging & Stabilization', 'Ready for Next Stage', or 'Maintenance / Parked'. "
        "Extract technical summaries, identified architectural blockers, and key milestone items based strictly on the provided documentation and file trees."
    )

    batch_payload = []
    for item in batch_items:
        batch_payload.append({
            "name_with_owner": item.get("name_with_owner"),
            "description": item.get("description", ""),
            "directories": item.get("directories", []),
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

    return gemini_engine.generate_structured(
        prompt=prompt,
        response_schema=BatchRepoStatusResponse,
        operation_type="batch_status",
        system_instruction=system_instruction
    )


def generate_repo_enhancements(repo_data: Dict[str, Any]) -> ProjectEnhancementPlan:
    """
    On-Demand Single-Project Deep Dive.
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
        f"OPEN ISSUES: {json.dumps(repo_data.get('open_issues', []))}\n"
        f"HARVESTED DOCUMENTATION:\n{json.dumps(repo_data.get('sanitized_docs', {}), indent=2)}\n\n"
        "OUTPUT REQUIREMENTS:\n"
        "1. 2 to 3 'quick_wins' that can be built in under 2 hours with immediate developer ROI.\n"
        "2. 2 to 3 'next_milestones' advancing the core product to its next major capability.\n"
        "3. Every item MUST have a comprehensive, copy-ready 'antigravity_prompt' that a developer can paste directly into Antigravity."
    )

    return gemini_engine.generate_structured(
        prompt=prompt,
        response_schema=ProjectEnhancementPlan,
        operation_type="deep_dive",
        system_instruction=system_instruction
    )


def generate_cross_portfolio_strategy(all_repos: List[Dict[str, Any]]) -> CrossPortfolioStrategy:
    """
    Single-Call Cross-Portfolio Strategist.
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

    return gemini_engine.generate_structured(
        prompt=prompt,
        response_schema=CrossPortfolioStrategy,
        operation_type="portfolio_brainstorm",
        system_instruction=system_instruction
    )
