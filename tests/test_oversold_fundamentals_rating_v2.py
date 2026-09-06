from pathlib import Path
import json
import shutil
import subprocess

import pytest


SCRIPT = Path("app/static/oversold_fundamentals_rating_v2.js")
LOADER = Path("app/static/oversold_tracking_v3.js")


def test_rating_blends_resilience_damage_and_structural_signals() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "0.65 * resilience + 0.35 * (100 - damage)" in source
    assert "capital_distress" in source
    assert "primary_endpoint_failure" in source
    assert "material_dilution" in source


def test_missing_filing_data_does_not_manufacture_a_strength_rating() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is unavailable for frontend behavior verification")
    harness = r"""
const fs = require('fs');
const vm = require('vm');
const cell = {dataset:{}};
const row = {querySelector: selector => selector === '.or-fundamentals' ? cell : {textContent:'TEST'}};
const context = {
  state:{candidates:[{symbol:'TEST',resilience_score:97,damage_risk:18,catalyst_analysis:{fundamental_trace:{available:false}}}]},
  document:{body:{},querySelectorAll:() => [row]},
  MutationObserver:class {observe(){}},
  queueMicrotask:fn => fn()
};
vm.runInNewContext(fs.readFileSync('app/static/oversold_fundamentals_rating_v2.js','utf8'),context);
process.stdout.write(JSON.stringify({html:cell.innerHTML,title:cell.title}));
"""
    result = subprocess.run([node, "-e", harness], check=True, text=True, capture_output=True)
    rendered = json.loads(result.stdout)
    assert "Unknown" in rendered["html"]
    assert "insufficient evidence" in rendered["html"]
    assert "/100" not in rendered["html"]
    assert "financial strength is unknown" in rendered["title"]


def test_loader_applies_rating_after_day3_ui() -> None:
    source = LOADER.read_text(encoding="utf-8")
    assert "oversold_day3_ui.js" in source
    assert "oversold_fundamentals_rating_v2.js" in source
