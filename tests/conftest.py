"""
Pytest configuration and fixtures.
"""

import os
import sys
from pathlib import Path

import pytest

# Add src to path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

# Set test environment
os.environ["APP_ENV"] = "test"
os.environ["TG_API_ID"] = "123456"
os.environ["TG_API_HASH"] = "test_hash"
os.environ["TG_PHONE"] = "+1234567890"
os.environ["CONTROL_BOT_TOKEN"] = "bot:test_token"
os.environ["OWNER_TELEGRAM_ID"] = "123456"
os.environ["DATABASE_URL"] = "sqlite:///./test_data/test.db"


@pytest.fixture(autouse=True)
def setup_test_environment(tmp_path):
    """Setup test environment for each test."""
    # Create test data directory
    test_data = tmp_path / "test_data"
    test_data.mkdir(parents=True, exist_ok=True)

    # Set test database path
    os.environ["DATABASE_URL"] = f"sqlite:///{test_data}/test.db"

    yield

    # Cleanup
    os.environ.pop("DATABASE_URL", None)
