"""Archetype classification and experience lesson library for scaffolding generation."""

import json
import uuid
from typing import Any

import asyncpg

from gateway_harness.contracts import Scaffold
from gateway_harness.db.pg import get_pool

ARCHETYPE_KEYWORDS = {
    "classification": (
        "classify",
        "categor",
        "sentiment",
        "intent",
        "label",
        "score",
        "detect",
        "tag",
    ),
    "extraction": (
        "extract",
        "parse",
        "entities",
        "fields",
        "convert to json",
        "structured data",
    ),
    "summarization": (
        "summarize",
        "summary",
        "tl;dr",
        "brief",
        "condense",
        "overview",
        "digest",
    ),
    "translation": (
        "translate",
        "translation",
        "to spanish",
        "to french",
        "to german",
        "to russian",
        "to chinese",
        "in language",
    ),
    "qa_rag": (
        "context:",
        "based on the text",
        "based on the provided",
        "according to the document",
        "given the following",
        "answer the question",
    ),
    "generation": (
        "generate",
        "write a",
        "draft",
        "compose",
        "create a",
        "rewrite",
        "story",
    ),
}


def archetype(system_prompt: str, user_prompt: str = "") -> str:
    """Classify prompt into workload archetype based on keyword heuristics."""
    text = f"{system_prompt.lower()} {user_prompt.lower()}"
    for arch, keywords in ARCHETYPE_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return arch
    return "other"


async def record_lesson(
    archetype_name: str,
    cue: str,
    lesson_text: str,
    evidence: dict[str, Any],
    scaffold: Scaffold,
    pool: asyncpg.Pool | None = None,
) -> str:
    """Persist an optimization experience lesson into gh_lessons."""
    lesson_id = f"les_{uuid.uuid4().hex[:12]}"
    p = pool or await get_pool()
    async with p.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO gh_lessons (id, archetype, cue, lesson, evidence, scaffold)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb)
            """,
            lesson_id,
            archetype_name,
            cue,
            lesson_text,
            json.dumps(evidence),
            scaffold.model_dump_json(),
        )
    return lesson_id


async def top_lessons(
    archetype_name: str,
    k: int = 3,
    pool: asyncpg.Pool | None = None,
) -> list[dict[str, Any]]:
    """Retrieve top recent experience lessons for a given archetype."""
    p = pool or await get_pool()
    async with p.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, archetype, cue, lesson, evidence, scaffold
            FROM gh_lessons
            WHERE archetype = $1 OR archetype = 'other'
            ORDER BY created_at DESC
            LIMIT $2
            """,
            archetype_name,
            k,
        )
        results = []
        for r in rows:
            scaffold_data = r["scaffold"]
            if isinstance(scaffold_data, str):
                scaffold_data = json.loads(scaffold_data)
            results.append(
                {
                    "id": r["id"],
                    "archetype": r["archetype"],
                    "cue": r["cue"],
                    "lesson": r["lesson"],
                    "scaffold": scaffold_data,
                }
            )
        return results
