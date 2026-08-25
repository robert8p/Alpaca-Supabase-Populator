"""Process-local bootstrap isolation for the separate Reversion Guard service.

The repository's historical ``app`` package intentionally imports the full scanner
runtime whenever it is imported outside pytest.  The Guard service only needs its
own pure modules and consumes the production scanner over HTTP, so loading Alpaca
and database runtime configuration would be both unnecessary and an architectural
regression.

Render sets ``APP_BOOTSTRAP_MODE=reversion_guard`` and adds the repository root to
``PYTHONPATH`` for the separate service only.  In that process, this lightweight
sentinel activates the package's existing test/isolation path before ``app`` is
imported.  The normal web and worker services are unchanged because they do not set
the mode variable.
"""

from __future__ import annotations

import os
import sys
import types


if os.getenv("APP_BOOTSTRAP_MODE", "").strip().lower() == "reversion_guard":
    sys.modules.setdefault("pytest", types.ModuleType("pytest"))
