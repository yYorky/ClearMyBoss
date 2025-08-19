import pytest

def make_region(n: int = 1, l: int = 1) -> dict:
    """Return a simple line-based region object for tests."""
    return {"line": {"n": n, "l": l}}

@pytest.fixture
def region() -> dict:
    """Default region representing the first line."""
    return make_region()
