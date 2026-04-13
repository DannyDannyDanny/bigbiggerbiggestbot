import sys
from pathlib import Path

import pytest

# Add project root to path so tests can import modules directly
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def tmp_db(monkeypatch, tmp_path):
    """Provide a fresh SQLite database for each test."""
    import db

    db_file = tmp_path / "test_workouts.db"
    monkeypatch.setattr(db, "DB_PATH", db_file)
    db.init_db()
    return db_file
