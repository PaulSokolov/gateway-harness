from pathlib import Path


def test_no_enterprise_imports():
    """Security and compliance test: ensure zero imports from litellm_enterprise or enterprise/ modules."""
    src_dir = Path(__file__).resolve().parent.parent.parent / "src"
    assert src_dir.is_dir()

    forbidden = ["litellm_enterprise", "from enterprise", "import enterprise"]
    violations = []

    for py_file in src_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        for bad in forbidden:
            if bad in content:
                violations.append(f"{py_file.name}: contains '{bad}'")

    assert not violations, f"Enterprise imports found in appliance source: {violations}"
