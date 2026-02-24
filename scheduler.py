"""
Scheduler for automatic scraping runs.

Runs quick updates at configured hours (default: 08:00, 20:00).
Full scrape runs once a week (Sunday at 03:00).

Start:
    python run.py scheduler
"""

import asyncio
import logging
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from config import SCHEDULE_HOURS

logger = logging.getLogger(__name__)


def run_quick():
    """Wrapper to run async quick_run in sync context."""
    logger.info("Scheduled quick run starting...")
    from scraper.runner import quick_run
    asyncio.run(quick_run())
    logger.info("Scheduled quick run completed.")


def run_full():
    """Wrapper to run async full_run in sync context."""
    logger.info("Scheduled full run starting...")
    from scraper.runner import full_run
    asyncio.run(full_run())
    logger.info("Scheduled full run completed.")


def start_scheduler():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    scheduler = BlockingScheduler()

    # Quick runs at scheduled hours (every day)
    for hour in SCHEDULE_HOURS:
        scheduler.add_job(
            run_quick,
            trigger=CronTrigger(hour=hour, minute=0),
            id=f"quick_run_{hour:02d}",
            name=f"Quick scrape at {hour:02d}:00",
            misfire_grace_time=3600,
        )
        logger.info("Scheduled quick run at %02d:00 daily", hour)

    # Full run: every Sunday at 03:00
    scheduler.add_job(
        run_full,
        trigger=CronTrigger(day_of_week="sun", hour=3, minute=0),
        id="full_run_weekly",
        name="Full scrape on Sunday 03:00",
        misfire_grace_time=7200,
    )
    logger.info("Scheduled full run on Sundays at 03:00")

    logger.info("Scheduler started. Press Ctrl+C to stop.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")
