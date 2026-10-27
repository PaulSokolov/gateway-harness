from evalharness.generator import generate_batch, generate_request


def test_eval_generator():
    req = generate_request(archetype_name="classification", model="gpt-4o", seed=42)
    assert req["model"] == "gpt-4o"
    assert len(req["messages"]) == 2
    assert "classification" in req["messages"][0]["content"]

    batch = generate_batch(count=12, seed=123)
    assert len(batch) == 12
    for b in batch:
        assert b["model"] == "gpt-4o"
        assert len(b["messages"]) == 2
