from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from swe_job_radar.classification import RuleBasedClassifier
from swe_job_radar.config import Settings, load_companies, load_settings
from swe_job_radar.database import Database
from swe_job_radar.http import HttpClient
from swe_job_radar.logging import configure_logging
from swe_job_radar.notifications.email import EmailNotifier, EmailSettings
from swe_job_radar.polling import Monitor, PollTarget
from swe_job_radar.scrapers.registry import create_scraper


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="swe-job-radar")
    parser.add_argument("--companies", type=Path, default=Path("config/companies.yaml"))
    parser.add_argument("--settings", type=Path, default=Path("config/settings.yaml"))
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("baseline", help="store current jobs without sending notifications")
    subparsers.add_parser("run", help="continuously monitor enabled companies")
    subparsers.add_parser("check-once", help="run one complete polling cycle")
    validate = subparsers.add_parser("validate", help="live-test without database or email")
    validate_group = validate.add_mutually_exclusive_group(required=True)
    validate_group.add_argument("slug", nargs="?")
    validate_group.add_argument("--all", action="store_true")
    subparsers.add_parser("status", help="display configured and observed scraper health")
    return parser


def _http(settings: Settings) -> HttpClient:
    return HttpClient(
        user_agent=settings.user_agent,
        timeout_seconds=settings.request_timeout_seconds,
        max_retries=settings.max_retries,
        per_domain_concurrency=settings.per_domain_concurrency,
    )


async def _build_monitor(args: argparse.Namespace) -> tuple[Monitor, HttpClient]:
    companies = load_companies(args.companies)
    settings = load_settings(args.settings)
    http = _http(settings)
    targets = [
        PollTarget(config, create_scraper(config, http))
        for config in companies.values()
        if config.enabled and config.status == "supported"
    ]
    email_settings = EmailSettings.from_env()
    notifier = EmailNotifier(email_settings) if email_settings else None
    monitor = Monitor(
        targets=targets,
        database=Database(settings.database_path),
        classifier=RuleBasedClassifier(),
        notifier=notifier,
        concurrency=settings.concurrency,
        repost_after_days=settings.repost_after_days,
    )
    return monitor, http


async def _monitor_command(args: argparse.Namespace) -> int:
    monitor, http = await _build_monitor(args)
    try:
        if args.command == "baseline":
            succeeded = await monitor.check_once(force_baseline=True)
            if succeeded:
                print("Baseline complete. No job notifications were sent.")
                return 0
            print("Baseline incomplete: one or more sources failed; no notifications were sent.")
            return 1
        elif args.command == "check-once":
            return 0 if await monitor.check_once() else 1
        elif args.command == "run":
            await monitor.run_forever()
        return 0
    finally:
        await http.aclose()


async def _validate(args: argparse.Namespace) -> int:
    companies = load_companies(args.companies)
    settings = load_settings(args.settings)
    if args.all:
        selected = list(companies.values())
    else:
        config = companies.get(args.slug)
        if config is None:
            print(f"Unknown company slug: {args.slug}", file=sys.stderr)
            return 2
        selected = [config]
    unsupported = [config for config in selected if not config.scraper]
    for config in unsupported:
        print(f"UNSUPPORTED {config.slug}: {config.notes}")
    selected = [config for config in selected if config.scraper]

    semaphore = asyncio.Semaphore(settings.concurrency)
    failures = 0
    async with _http(settings) as http:

        async def validate_one(config: object) -> None:
            nonlocal failures
            async with semaphore:
                try:
                    jobs = await create_scraper(config, http).fetch_jobs()
                    if not jobs:
                        raise ValueError("returned zero jobs")
                except Exception as exc:
                    failures += 1
                    print(f"BROKEN {config.slug}: {type(exc).__name__}: {exc}")
                    return
                print(f"OK {config.slug}: {len(jobs)} normalized jobs")
                for job in jobs[:3]:
                    print(
                        json.dumps(
                            {
                                "external_id": job.external_id,
                                "title": job.title,
                                "location": job.location,
                                "job_url": job.job_url,
                            },
                            ensure_ascii=False,
                        )
                    )

        await asyncio.gather(*(validate_one(config) for config in selected))
    return 1 if failures else 0


def _status(args: argparse.Namespace) -> None:
    companies = load_companies(args.companies)
    settings = load_settings(args.settings)
    states = {row["company"]: row for row in Database(settings.database_path).scraper_status()}
    headers = ("SLUG", "PRIORITY", "SUPPORT", "LAST SUCCESS", "FAILURES", "LAST COUNT")
    print(
        f"{headers[0]:<24} {headers[1]:<9} {headers[2]:<11} "
        f"{headers[3]:<27} {headers[4]:<8} {headers[5]}"
    )
    for config in companies.values():
        state = states.get(config.name, {})
        print(
            f"{config.slug:<24} {config.priority.value:<9} {config.status:<11} "
            f"{str(state.get('last_success_at') or '-'):<27} "
            f"{str(state.get('consecutive_failures') or 0):<8} "
            f"{state.get('last_job_count') if state else '-'}"
        )


def main() -> None:
    configure_logging()
    args = build_parser().parse_args()
    if args.command in {"baseline", "run", "check-once"}:
        try:
            raise SystemExit(asyncio.run(_monitor_command(args)))
        except KeyboardInterrupt:
            pass
    elif args.command == "validate":
        raise SystemExit(asyncio.run(_validate(args)))
    elif args.command == "status":
        _status(args)
