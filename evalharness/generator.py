"""Synthetic traffic generator producing realistic prompts for 6 workload archetypes."""

import random
from typing import Any

TEMPLATES = {
    "classification": [
        "Classify the sentiment of this review as positive, neutral, or negative: '{text}'",
        "Categorize this support ticket priority (low, medium, high, urgent): '{text}'",
        "Detect the intent behind this user query: '{text}'",
    ],
    "extraction": [
        "Extract the customer name, order number, and refund amount from: '{text}'. Format as JSON.",
        "Parse the date, meeting title, and attendees from: '{text}'. Return JSON object.",
        "Extract key entities and their tags from this paragraph: '{text}'.",
    ],
    "summarization": [
        "Summarize the following incident report into a concise paragraph: '{text}'",
        "Provide a 3-bullet point executive digest of this document: '{text}'",
        "Write a TL;DR summary for this email thread: '{text}'",
    ],
    "translation": [
        "Translate the following text into Spanish: '{text}'",
        "Translate this product description into French: '{text}'",
        "Translate this support message into German: '{text}'",
    ],
    "qa_rag": [
        (
            "Based on the following document context, answer the user question:\n"
            "Context: '{text}'\nQuestion: What was the root cause?"
        ),
        "According to the provided knowledge base article: '{text}'\nQuestion: How do I reset my API key?",
    ],
    "generation": [
        "Draft a friendly follow-up email to a prospective enterprise customer regarding: '{text}'",
        "Generate a creative product announcement post about: '{text}'",
    ],
}

FILLERS = [
    "Our team observed a latency spike in the European cluster at 14:30 UTC.",
    "Customer requested a full refund for damaged order #98231 totaling $84.50.",
    "The new feature release introduces multi-region database failover capabilities.",
    "Quarterly financial projections show a 14% increase in recurring SaaS subscription revenue.",
    "The client inquiry is asking for volume discount tiers on annual billing agreements.",
]


def generate_request(
    archetype_name: str | None = None,
    model: str = "gpt-4o",
    seed: int | None = None,
) -> dict[str, Any]:
    """Generate a single chat completion payload for a given or random archetype."""
    rng = random.Random(seed)
    chosen_arch = archetype_name if archetype_name in TEMPLATES else rng.choice(list(TEMPLATES.keys()))
    tpl = rng.choice(TEMPLATES[chosen_arch])
    filler = rng.choice(FILLERS)
    prompt = tpl.format(text=filler)

    return {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": f"You are an expert AI assistant specializing in {chosen_arch}.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }


def generate_batch(count: int = 50, seed: int = 42) -> list[dict[str, Any]]:
    """Generate a batch of varied synthetic requests."""
    rng = random.Random(seed)
    return [generate_request(model="gpt-4o", seed=rng.randint(1, 100000)) for _ in range(count)]
