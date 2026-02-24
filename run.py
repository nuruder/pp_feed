#!/usr/bin/env python3
# Run: source .venv/bin/activate && python run.py <command>
"""
Main entry point for the PadelPoint parser.

Usage:
    python run.py scrape               # Full scrape (categories → products → details → auth prices)
    python run.py auth login           # Login (auto via 2Captcha, fallback to interactive)
    python run.py auth interactive     # Force interactive login
    python run.py auth check           # Check if session is valid
    python run.py api                  # Start the API server
    python run.py export [--output X]  # Export to Excel
    python run.py scheduler            # Start the scheduler daemon
"""

import asyncio
import logging
import sys
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).resolve().parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("pp_parser")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    if command == "scrape":
        from scraper.runner import run_scrape
        asyncio.run(run_scrape())

    elif command == "auth":
        action = sys.argv[2] if len(sys.argv) > 2 else "login"
        from scraper.auth import auto_login, interactive_login, check_session_valid
        if action == "login":
            cookies = asyncio.run(auto_login())
            if not cookies:
                logger.info("Auto-login unavailable. Starting interactive login...")
                cookies = asyncio.run(interactive_login())
            if cookies:
                print(f"Login complete. {len(cookies)} cookies saved.")
            else:
                print("Login failed.")
        elif action == "interactive":
            asyncio.run(interactive_login())
        elif action == "check":
            valid = asyncio.run(check_session_valid())
            print(f"Session valid: {valid}")
        else:
            print(f"Unknown auth action: {action}. Use 'login', 'interactive', or 'check'.")

    elif command == "api":
        import uvicorn
        from config import API_HOST, API_PORT
        uvicorn.run("api.main:app", host=API_HOST, port=API_PORT, reload=True)

    elif command == "export":
        from export.excel import export_to_excel
        output = None
        for i, arg in enumerate(sys.argv):
            if arg == "--output" and i + 1 < len(sys.argv):
                output = sys.argv[i + 1]
        asyncio.run(export_to_excel(output))

    elif command == "scheduler":
        from scheduler import start_scheduler
        start_scheduler()

    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
