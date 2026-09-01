from __future__ import annotations

import asyncio
import os
import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from zoneinfo import ZoneInfo

from swe_job_radar.models import Classification, ClassificationResult, Job, Priority
from swe_job_radar.notifications.base import Notifier

EASTERN = ZoneInfo("America/New_York")


def format_subject(job: Job, result: ClassificationResult, priority: Priority) -> str:
    if result.classification is Classification.RELEVANT_BUT_AMBIGUOUS:
        return f"⚠️ [REVIEW] {job.company} — {job.title}"
    if result.classification is Classification.INTERN_2027:
        label = "SUMMER 2027 INTERN"
    else:
        label = "NEW GRAD 2027 SWE" if priority is Priority.QUANT else "NEW GRAD 2027"
    icon = {Priority.CRITICAL: "🚨", Priority.HIGH: "🔥", Priority.QUANT: "📈"}[priority]
    return f"{icon} [{label}] {job.company} — {job.title}"


def format_body(job: Job, result: ClassificationResult, priority: Priority) -> str:
    detected = job.first_seen_at.astimezone(EASTERN).strftime("%Y-%m-%d %H:%M:%S %Z")
    apply_url = job.apply_url or job.job_url
    return "\n".join(
        (
            "NEW SWE ROLE DETECTED",
            "",
            "APPLY:",
            apply_url,
            "",
            "Company:",
            job.company,
            "",
            "Priority:",
            priority.value.upper(),
            "",
            "Role:",
            job.title,
            "",
            "Classification:",
            result.classification.value,
            "",
            "Location:",
            job.location or "Not specified",
            "",
            "First detected:",
            detected,
            "",
            "Reason:",
            result.reason,
            "",
            "OFFICIAL POSTING:",
            job.job_url,
            "",
            "Detected by SWE Job Radar.",
        )
    )


@dataclass(frozen=True, slots=True)
class EmailSettings:
    sender: str
    recipient: str
    host: str
    port: int
    username: str | None
    password: str | None
    starttls: bool = True

    @classmethod
    def from_env(cls) -> EmailSettings | None:
        required = (os.getenv("EMAIL_FROM"), os.getenv("EMAIL_TO"), os.getenv("SMTP_HOST"))
        if not all(required):
            return None
        return cls(
            sender=required[0] or "",
            recipient=required[1] or "",
            host=required[2] or "",
            port=int(os.getenv("SMTP_PORT", "587")),
            username=os.getenv("SMTP_USERNAME"),
            password=os.getenv("SMTP_PASSWORD"),
            starttls=os.getenv("SMTP_STARTTLS", "true").casefold() in {"1", "true", "yes"},
        )


class EmailNotifier(Notifier):
    def __init__(self, settings: EmailSettings) -> None:
        self.settings = settings

    async def send(
        self,
        job: Job,
        result: ClassificationResult,
        priority: Priority,
        *,
        idempotency_key: str,
    ) -> None:
        message = EmailMessage()
        message["From"] = self.settings.sender
        message["To"] = self.settings.recipient
        message["Subject"] = format_subject(job, result, priority)
        message["Message-ID"] = f"<{idempotency_key}@swe-job-radar.local>"
        message["Date"] = datetime.now().astimezone()
        message.set_content(format_body(job, result, priority))
        await asyncio.to_thread(self._send_sync, message)

    async def send_operational(self, subject: str, body: str, *, idempotency_key: str) -> None:
        message = EmailMessage()
        message["From"] = self.settings.sender
        message["To"] = self.settings.recipient
        message["Subject"] = f"🛠️ [RADAR HEALTH] {subject}"
        message["Message-ID"] = f"<{idempotency_key}@swe-job-radar.local>"
        message["Date"] = datetime.now().astimezone()
        message.set_content(body)
        await asyncio.to_thread(self._send_sync, message)

    def _send_sync(self, message: EmailMessage) -> None:
        with smtplib.SMTP(self.settings.host, self.settings.port, timeout=30) as smtp:
            smtp.ehlo()
            if self.settings.starttls:
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
            if self.settings.username:
                smtp.login(self.settings.username, self.settings.password or "")
            smtp.send_message(message)
