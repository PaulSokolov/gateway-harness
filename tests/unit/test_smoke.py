import litellm

import gateway_harness


def test_imports():
    assert gateway_harness.__version__ == "0.1.0"
    assert litellm.__name__ == "litellm"
