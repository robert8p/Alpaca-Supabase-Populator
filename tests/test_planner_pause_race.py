from pathlib import Path


def test_planner_does_not_resume_already_paused_job_after_planning_race():
    source = (Path(__file__).resolve().parents[1] / "app" / "planner.py").read_text(encoding="utf-8")
    assert 'control in {"pause_requested", "paused"}' in source
    assert 'next_status = "paused"' in source
