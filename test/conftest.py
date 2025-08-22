import pytest


def make_region(start: int = 0, end: int = 1) -> dict:
    """Return a simple segment-based region object for tests."""
    return {"segment": {"startIndex": start, "endIndex": end}}


@pytest.fixture
def region() -> dict:
    """Default region representing the first character."""
    return make_region()
