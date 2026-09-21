import asyncio
import logging
import smtplib
from email.message import EmailMessage

from app.config import settings

log = logging.getLogger("access")


def send(to: list[str], subject: str, html: str) -> None:
    if not settings.smtp_host or not to:
        return
    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    msg.set_content("This email requires an HTML-capable client to view.")
    msg.add_alternative(html, subtype="html")
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
        smtp.send_message(msg)


async def _send_one(to: list[str], subject: str, html: str) -> None:
    """Best-effort: a commit is already durable by the time this runs."""
    try:
        await asyncio.to_thread(send, to, subject, html)
    except Exception:
        log.exception("commit notification email failed")


async def send_all(mails: list[tuple[list[str], str, str]]) -> None:
    await asyncio.gather(*(_send_one(*mail) for mail in mails))
