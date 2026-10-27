import time

import pytest

from gateway_harness.scrub import scrub_obj, scrub_text

PARAMETRIZED_CASES = [
    # Emails
    ("Contact user@example.com for info", "Contact <EMAIL> for info"),
    ("Multiple: test.user+tag@domain.co.uk and a@b.org", "Multiple: <EMAIL> and <EMAIL>"),
    # Phones
    ("Call +1 (555) 234-5678 today", "Call <PHONE> today"),
    ("Mobile 555-123-4567 is here", "Mobile <PHONE> is here"),
    ("Direct: +44 20 7946 0958", "Direct: <PHONE>"),
    # Secrets
    ("API key sk-proj-1234567890abcdef1234567890", "API key <SECRET>"),
    ("Anthropic sk-ant-api03-1234567890abcdef1234567890", "Anthropic <SECRET>"),
    ("AWS Key AKIAIOSFODNN7EXAMPLE is active", "AWS Key <SECRET> is active"),
    ("GitHub ghp_123456789012345678901234567890123456", "GitHub <SECRET>"),
    ("Slack xoxb-123456789012-1234567890123-456789abcdef", "Slack <SECRET>"),
    ("Bearer token=supersecretkey1234", "Bearer token: <SECRET>"),
    ("api_key: 'very_secret_pass_123'", "api_key: <SECRET>"),
    ('password = "my_super_secret_99"', "password: <SECRET>"),
    # JWT
    (
        "Token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozG4B1sW7FvH6wZ5Xy8k",
        "Token: <JWT>",
    ),
    # IP Addresses
    ("Server running on 192.168.1.1:8000", "Server running on <IP>:8000"),
    ("Public IP: 8.8.8.8", "Public IP: <IP>"),
    ("IPv6: 2001:0db8:85a3:0000:0000:8a2e:0370:7334", "IPv6: <IP>"),
    # Credit card (Luhn valid vs invalid)
    ("Card 4111 1111 1111 1111 is valid", "Card <CARD> is valid"),  # Luhn valid
    # IBAN
    ("IBAN GB82WEST12345698765432 is valid", "IBAN <IBAN> is valid"),
    # False-positive guards (plain numbers, dates, version strings should NOT be scrubbed as card/secret)
    ("Version 1.108.0 release notes", "Version 1.108.0 release notes"),
    ("Date: 2026-10-26T20:30:00Z", "Date: 2026-10-26T20:30:00Z"),
    ("Small numbers: 123 456 789", "Small numbers: 123 456 789"),
    ("Order ID: 987654321012 (invalid luhn)", "Order ID: 987654321012 (invalid luhn)"),
    ("Price: $19.99 for 2 items", "Price: $19.99 for 2 items"),
    ("Dimensions: 1920x1080 resolution", "Dimensions: 1920x1080 resolution"),
    ("Code 404 Not Found", "Code 404 Not Found"),
]


@pytest.mark.parametrize("inp, expected", PARAMETRIZED_CASES)
def test_scrub_text_parametrized(inp, expected):
    assert scrub_text(inp) == expected


def test_scrub_obj():
    data = {
        "email_key": "user@test.com",
        "nested": {
            "token": "sk-1234567890abcdef1234567890",
            "count": 42,
            "ip_list": ["10.0.0.1", "127.0.0.1"],
        },
    }
    scrubbed = scrub_obj(data)
    # Keys must be preserved untouched!
    assert "email_key" in scrubbed
    assert scrubbed["email_key"] == "<EMAIL>"
    assert scrubbed["nested"]["token"] == "<SECRET>"
    assert scrubbed["nested"]["count"] == 42
    assert scrubbed["nested"]["ip_list"] == ["<IP>", "<IP>"]


def test_scrub_benchmark():
    # 10 KB sample text
    base_paragraph = (
        "User Alice user@example.com connected from 192.168.1.50 using key sk-12345678901234567890abcdef. "
        "Processed order 123456 on 2026-10-26 for version 1.108.0. Total price was $150.00. "
    )
    ten_kb_text = base_paragraph * 56  # exactly > 10,000 chars
    assert len(ten_kb_text) >= 10000

    durations = []
    for _ in range(50):
        t0 = time.perf_counter()
        scrub_text(ten_kb_text)
        t1 = time.perf_counter()
        durations.append(t1 - t0)

    durations.sort()
    median_ms = durations[len(durations) // 2] * 1000
    # Must scrub 10 KB in < 2ms median
    assert median_ms < 2.0, f"Scrubbing took {median_ms:.3f}ms, expected < 2.0ms"
