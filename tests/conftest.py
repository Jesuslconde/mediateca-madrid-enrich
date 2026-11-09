from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

FIXTURES = ROOT / "fixtures"


@pytest.fixture
def dvd_fixture() -> Path:
    return FIXTURES / "detail_dvd.html"


@pytest.fixture
def bluray_fixture() -> Path:
    return FIXTURES / "detail_bluray.html"
