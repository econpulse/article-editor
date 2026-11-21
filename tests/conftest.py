"""
Pytest-Konfiguration: Isoliert alle Tests auf eine temporäre SQLite-Datenbank,
damit `data/local_dev_cms.db` nicht durch Testläufe mit Hunderten Test-Artikeln verschmutzt wird.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

_TEST_DB_DIR: Path | None = None


def pytest_configure(config) -> None:
    global _TEST_DB_DIR
    _TEST_DB_DIR = Path(tempfile.mkdtemp(prefix="lukb_pytest_db_"))
    db_file = _TEST_DB_DIR / "test_cms.db"
    os.environ["LOCAL_FALLBACK_SQLITE_PATH"] = str(db_file)


def pytest_sessionfinish(session, exitstatus) -> None:
    if _TEST_DB_DIR and _TEST_DB_DIR.exists():
        try:
            from database.connection import engine

            engine.dispose()
        except Exception:
            pass
        shutil.rmtree(_TEST_DB_DIR, ignore_errors=True)
