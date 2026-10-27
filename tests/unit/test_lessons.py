from unittest.mock import AsyncMock, MagicMock

import pytest

from gateway_harness.contracts import Scaffold
from gateway_harness.proposer.lessons import archetype, record_lesson, top_lessons


def test_archetype_keywords():
    assert archetype("You are an intent classifier for support tickets.") == "classification"
    assert archetype("Extract all named entities and convert to json.") == "extraction"
    assert archetype("Summarize the meeting notes into a brief digest.") == "summarization"
    assert archetype("Translate the following speech to spanish.") == "translation"
    assert archetype("Based on the provided document, answer the question.") == "qa_rag"
    assert archetype("Write a creative draft of a poem.") == "generation"
    assert archetype("Random arbitrary instruction with no keywords.") == "other"


@pytest.mark.asyncio
async def test_record_and_retrieve_lessons():
    pool = MagicMock()
    conn = AsyncMock()
    acquire_ctx = AsyncMock()
    acquire_ctx.__aenter__.return_value = conn
    acquire_ctx.__aexit__.return_value = None
    pool.acquire.return_value = acquire_ctx

    # Test record_lesson
    scaffold = Scaffold(system_addendum="Be concise.", params={"temperature": 0.2})
    les_id = await record_lesson(
        archetype_name="summarization",
        cue="Candidate response exceeded length limit",
        lesson_text="Adding concision instruction keeps tokens under budget",
        evidence={"length_ratio": 2.5},
        scaffold=scaffold,
        pool=pool,
    )
    assert les_id.startswith("les_")
    assert any("INSERT INTO gh_lessons" in str(call) for call in conn.execute.call_args_list)

    # Test top_lessons
    conn.fetch.return_value = [
        {
            "id": les_id,
            "archetype": "summarization",
            "cue": "too long",
            "lesson": "be brief",
            "evidence": {},
            "scaffold": '{"system_addendum": "Be brief"}',
        }
    ]
    lessons = await top_lessons("summarization", k=3, pool=pool)
    assert len(lessons) == 1
    assert lessons[0]["id"] == les_id
    assert lessons[0]["scaffold"]["system_addendum"] == "Be brief"
