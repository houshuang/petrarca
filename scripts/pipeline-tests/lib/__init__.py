"""Pipeline testing framework library."""

import os
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

# Load .env from project root if it exists
_env_file = PROJECT_DIR / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = value
