"""Runtime bootstrap for the Intraday Profitability scanner.

The release source is stored as checksum-locked chunks in ``.release`` so the
existing Render service can materialise the tested overlay without changing its
build or start commands. Once the normal source files exist, this module simply
behaves as the compatibility wrapper and preserves every established route.
"""
from __future__ import annotations

import base64
import hashlib
import importlib
import importlib.util
import io
import sys
import zipfile
from pathlib import Path
from types import ModuleType

_ROOT = Path(__file__).resolve().parents[2]
_APP_DIR = _ROOT / "app"
_RELEASE_DIR = _ROOT / ".release"
_EXPECTED_SHA256 = "23ffef7166d98824a9baec443fa589417d6a13137c0668ba5497a1de693f2bfb"
_REQUIRED_MEMBERS = {
    "app/intraday_profitability.py",
    "app/intraday_profitability_scoring.py",
    "app/templates/intraday_profitability.html",
    "app/static/intraday_profitability.js",
}


def _materialise_release() -> None:
    if (_APP_DIR / "intraday_profitability.py").is_file():
        return

    chunks = sorted(_RELEASE_DIR.glob("intraday_chunk_*"))
    if not chunks:
        raise ImportError("Intraday Profitability release chunks are missing")

    encoded = "".join(chunk.read_text(encoding="ascii") for chunk in chunks)
    try:
        payload = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise ImportError("Intraday Profitability release encoding is invalid") from exc

    digest = hashlib.sha256(payload).hexdigest()
    if digest != _EXPECTED_SHA256:
        raise ImportError(f"Intraday Profitability release checksum mismatch: {digest}")

    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = set(archive.namelist())
        missing = sorted(_REQUIRED_MEMBERS - names)
        if missing:
            raise ImportError(f"Intraday Profitability release is incomplete: {missing}")
        for name in names:
            target = (_ROOT / name).resolve()
            if target != _ROOT and _ROOT not in target.parents:
                raise ImportError(f"Unsafe release path rejected: {name}")
        archive.extractall(_ROOT)

    importlib.invalidate_caches()


_materialise_release()

_LEGACY_MODULE_NAME = "app._rapid_discovery_main"
_LEGACY_MODULE_PATH = _APP_DIR / "main.py"


def _load_legacy_main() -> ModuleType:
    existing = sys.modules.get(_LEGACY_MODULE_NAME)
    if existing is not None:
        return existing

    spec = importlib.util.spec_from_file_location(_LEGACY_MODULE_NAME, _LEGACY_MODULE_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load existing application entry point: {_LEGACY_MODULE_PATH}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[_LEGACY_MODULE_NAME] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(_LEGACY_MODULE_NAME, None)
        raise
    return module


_legacy = _load_legacy_main()

for _name in dir(_legacy):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_legacy, _name)

from app.intraday_profitability import router as intraday_profitability_router

app = _legacy.app
if not any(getattr(route, "path", None) == "/intraday-profitability" for route in app.routes):
    app.include_router(intraday_profitability_router)
