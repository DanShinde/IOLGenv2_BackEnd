"""Glue between Django (settings, request/response) and the framework-agnostic engine/
ported from the source EFS Test Case Generator (testvault/engine/)."""
import shutil
from pathlib import Path

from django.conf import settings

from .engine.test_case_engine import TestCaseEngine
from .engine.dataclasses import Section

_BUNDLED_DATA_DIR = Path(__file__).resolve().parent / "engine" / "data"
_engine = None


def get_data_dir() -> Path:
    data_dir = Path(getattr(settings, "TESTVAULT_DATA_DIR", settings.BASE_DIR / "testvault_data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    # Seed from the bundled defaults on first run so test_groups.json / equipment.json /
    # global_test_cases.json / custom_test_cases.json exist in the writable location.
    for f in _BUNDLED_DATA_DIR.glob("*.json"):
        dest = data_dir / f.name
        if not dest.exists():
            shutil.copy(f, dest)
    return data_dir


def get_engine() -> TestCaseEngine:
    global _engine
    if _engine is None:
        _engine = TestCaseEngine(data_dir=get_data_dir())
    return _engine


def compute_project_stats(sections_data: list) -> dict:
    """Tally Pass/Fail/Pending across all generated (non-custom-excluded) test cases in a
    project's sections, for the dashboard's completion metrics."""
    engine = get_engine()
    total = passed = failed = 0
    for sec in sections_data:
        section = Section.from_dict(sec)
        for tc in engine.generate_test_cases(section):
            total += 1
            if tc.result == "Pass":
                passed += 1
            elif tc.result == "Fail":
                failed += 1
    return {
        "total_test_cases": total,
        "passed": passed,
        "failed": failed,
        "pending": total - passed - failed,
        "completion_percentage": round((passed + failed) / total * 100) if total else 0,
        "pass_percentage": round(passed / total * 100) if total else 0,
    }
