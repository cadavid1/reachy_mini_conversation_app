"""Reachy Mini Conversation App package init.

Loads a package-local .env at import time so downstream modules (config.py
in particular) see the right env vars no matter where the process is
launched from. Necessary because upstream config.py uses
`find_dotenv(usecwd=True)` — which fails when the dashboard launches us
from its own CWD — and tools are initialized from config values before
main.run() ever loads the per-instance .env.

override=False so explicit shell-level env vars still win over .env.
"""

from pathlib import Path

try:
    from dotenv import load_dotenv

    _pkg_env = Path(__file__).parent / ".env"
    if _pkg_env.is_file():
        load_dotenv(dotenv_path=str(_pkg_env), override=False)
except ImportError:
    # python-dotenv missing; main.py will surface a clearer error later if needed.
    pass
