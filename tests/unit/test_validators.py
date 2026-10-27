from gateway_harness.probe.validators import validate


def test_validator_empty():
    assert "empty" in validate({}, "baseline text", "")
    assert "empty" in validate({}, "baseline text", "   \n\t  ")


def test_validator_truncated():
    errs = validate({}, "baseline text", "partial text", finish_reason="length")
    assert "truncated" in errs


def test_validator_refusal():
    errs = validate({}, "baseline text", "I cannot fulfill this request as an AI assistant.")
    assert "refusal" in errs


def test_validator_json_valid_and_schema():
    req = {
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "schema": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
                    "required": ["name", "age"],
                }
            },
        }
    }
    # 1. Invalid JSON syntax
    errs1 = validate(req, '{"name": "Alice", "age": 30}', "not a json object")
    assert "json_invalid" in errs1

    # 2. Valid JSON but violates schema
    errs2 = validate(req, '{"name": "Alice", "age": 30}', '{"name": "Alice"}')
    assert "schema_invalid" in errs2

    # 3. Valid JSON adhering to schema
    errs3 = validate(req, '{"name": "Alice", "age": 30}', '{"name": "Bob", "age": 25}')
    assert len(errs3) == 0


def test_validator_json_keys_mismatch():
    base = '{"id": 1, "title": "news", "tags": ["a"]}'
    # Candidate missing "tags"
    cand = '{"id": 1, "title": "news"}'
    errs = validate({}, base, cand)
    assert "json_keys_mismatch" in errs

    # Candidate with same keys
    cand_ok = '{"id": 2, "title": "sports", "tags": []}'
    assert len(validate({}, base, cand_ok)) == 0


def test_validator_length_ratio():
    base = "A" * 300
    # Too short: 50 / 300 = 0.166 < 0.3
    cand_short = "A" * 50
    assert "length_ratio" in validate({}, base, cand_short)

    # Too long: 1000 / 300 = 3.33 > 3.0
    cand_long = "A" * 1000
    assert "length_ratio" in validate({}, base, cand_long)

    # Within bounds: 200 / 300 = 0.66
    cand_ok = "A" * 200
    assert "length_ratio" not in validate({}, base, cand_ok)


def test_validator_language_mismatch():
    # Cyrillic text
    base_cyrillic = "Это подробный отчет о работе сервера и анализе сетевых пакетов."
    # Candidate answered entirely in English
    cand_english = "This is a detailed server report and network packet analysis."

    errs = validate({}, base_cyrillic, cand_english)
    assert "language_mismatch" in errs


def test_validator_all_pass():
    base = "The quick brown fox jumps over the lazy dog."
    cand = "A fast brown fox leapt over a sleepy dog."
    errs = validate({}, base, cand, finish_reason="stop")
    assert len(errs) == 0
