"""
Scheduler for automatic scraping runs.

Runs the full scrape flow at configured hours (default: 08:00, 20:00).

Start:
    python run.py scheduler
"""

import asyncio
import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from config import SCHEDULE_HOURS

logger = logging.getLogger(__name__)


def run_scheduled_scrape():
    """Wrapper to run async run_scrape in sync context."""
    logger.info("Scheduled scrape starting...")
    from scraper.runner import run_scrape
    asyncio.run(run_scrape())
    logger.info("Scheduled scrape completed.")


def start_scheduler():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    scheduler = BlockingScheduler()

    for hour in SCHEDULE_HOURS:
        scheduler.add_job(
            run_scheduled_scrape,
            trigger=CronTrigger(hour=hour, minute=0),
            id=f"scrape_{hour:02d}",
            name=f"Scrape at {hour:02d}:00",
            misfire_grace_time=3600,
        )
        logger.info("Scheduled scrape at %02d:00 daily", hour)

    logger.info("Scheduler started. Press Ctrl+C to stop.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")
