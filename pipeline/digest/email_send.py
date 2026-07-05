from __future__ import annotations

import logging
import smtplib
from email.mime.text import MIMEText

from pipeline.config import EmailConfig

logger = logging.getLogger(__name__)


def send_digest_email(email_cfg: EmailConfig, digest_date: str, markdown_body: str) -> None:
    if not email_cfg.enabled:
        logger.info("Email disabled (EMAIL_ENABLED=false), skipping send")
        return
    if not email_cfg.to_addrs:
        logger.warning("No EMAIL_TO recipients configured, skipping send")
        return
    if not email_cfg.username or not email_cfg.password:
        logger.warning("SMTP_USERNAME/SMTP_PASSWORD not set, skipping send")
        return

    msg = MIMEText(markdown_body, "plain", "utf-8")
    msg["Subject"] = f"{email_cfg.subject_prefix} {digest_date}"
    msg["From"] = email_cfg.username
    msg["To"] = ", ".join(email_cfg.to_addrs)

    with smtplib.SMTP(email_cfg.smtp_host, email_cfg.smtp_port, timeout=30) as server:
        if email_cfg.use_tls:
            server.starttls()
        server.login(email_cfg.username, email_cfg.password)
        server.sendmail(email_cfg.username, email_cfg.to_addrs, msg.as_string())

    logger.info("Digest email sent to %s", ", ".join(email_cfg.to_addrs))
