"""Pipeline testing framework library."""

import sys
from pathlib import Path

# Add scripts/ to path so we can import build_articles, validate_articles, etc.
TESTS_DIR = Path(__file__).parent.parent
SCRIPTS_DIR = TESTS_DIR.parent
PROJECT_DIR = SCRIPTS_DIR.parent

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

FIXTURES_DIR = TESTS_DIR / "fixtures"
SESSIONS_DIR = TESTS_DIR / "sessions"
