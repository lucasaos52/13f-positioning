import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
FACTORS = HERE.parent
sys.path[:0] = [str(HERE), str(FACTORS), str(FACTORS / "general_plan")]


@pytest.fixture
def local_tmp(request):
    """Workspace-local temp path; the managed Windows temp root is unreadable."""
    path = HERE / "test_tmp" / request.node.name
    path.mkdir(parents=True, exist_ok=True)
    for child in path.glob("*"):
        if child.is_file():
            child.unlink()
    return path
