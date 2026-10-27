from gateway_harness.catalog import CatalogModel, Needs, candidates_for, load_catalog


def test_candidates_filtering_and_order():
    catalog = [
        CatalogModel(
            "gpt-4o",
            "openai/gpt-4o",
            in_price=2.5,
            out_price=10.0,
            max_input_tokens=128000,
            supports_tools=True,
            supports_vision=True,
            supports_response_schema=True,
        ),
        CatalogModel(
            "gpt-4o-mini",
            "openai/gpt-4o-mini",
            in_price=0.15,
            out_price=0.6,
            max_input_tokens=128000,
            supports_tools=True,
            supports_vision=True,
            supports_response_schema=True,
        ),
        CatalogModel(
            "cheap-tiny",
            "local/tiny",
            in_price=0.05,
            out_price=0.1,
            max_input_tokens=2048,
            supports_tools=False,
            supports_vision=False,
            supports_response_schema=False,
        ),
        CatalogModel(
            "expensive-o1",
            "openai/o1",
            in_price=15.0,
            out_price=60.0,
            max_input_tokens=128000,
            supports_tools=True,
            supports_vision=True,
            supports_response_schema=True,
        ),
    ]

    # Needs tools and 4000 prompt tokens
    needs = Needs(p99_prompt_tokens=4000, needs_tools=True, needs_vision=False, needs_response_schema=False)
    candidates = candidates_for("gpt-4o", needs, catalog)

    # cheap-tiny rejected (no tools, and max_input 2048 < 4800)
    # expensive-o1 rejected (more expensive)
    # gpt-4o-mini accepted!
    assert len(candidates) == 1
    assert candidates[0].name == "gpt-4o-mini"


def test_load_catalog_yaml(tmp_path):
    config_file = tmp_path / "litellm.yaml"
    config_file.write_text(
        """
model_list:
  - model_name: gpt-4o
    litellm_params:
      model: gpt-4o
  - model_name: gpt-4o-mini
    litellm_params:
      model: gpt-4o-mini
"""
    )
    cat = load_catalog(config_file)
    assert len(cat) == 2
    assert cat[0].name == "gpt-4o"
    assert cat[1].name == "gpt-4o-mini"
