"""SMTP delivery (stdlib only). Returns status: 'dry_run' | 'sent'."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from rmtask.config import Settings


class Emailer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def configured(self) -> bool:
        return self.settings.email_configured

    def send(self, subject: str, html: str, text: str = "", recipients: str = "") -> str:
        if not self.configured:
            return "dry_run"
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self.settings.email_from
        to = [r.strip() for r in (recipients or " ".join(self.settings.email_to)).split() if r.strip()]
        msg["To"] = ", ".join(to)
        msg.set_content(text or html)
        msg.add_alternative(html, subtype="html")
        if self.settings.smtp_ssl:
            server = smtplib.SMTP_SSL(self.settings.smtp_host, self.settings.smtp_port, timeout=20)
        else:
            server = smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=20)
        try:
            if self.settings.smtp_starttls and not self.settings.smtp_ssl:
                server.starttls()
            if self.settings.smtp_user:
                server.login(self.settings.smtp_user, self.settings.smtp_password)
            server.send_message(msg)
        finally:
            server.quit()
        return "sent"
