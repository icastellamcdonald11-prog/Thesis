"""Load sources.yaml + config/settings.yaml and merge in secrets from the environment."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@dataclass
class EmailConfig:
    enabled: bool
    smtp_host: str
    smtp_port: int
    use_tls: bool
    subject_prefix: str
    username: str | None
    password: str | None
    to_addrs: list[str]


@dataclass
class Settings:
    raw: dict = field(repr=False)
    timezone: str
    acquisition: dict
    detail_summary: dict
    triage: dict
    cluster: dict
    diffcheck: dict
    translate: dict
    digest: dict
    email: EmailConfig
    db_path: Path
    feedback_csv: Path
    anthropic_api_key: str | None

    @classmethod
    def load(cls, settings_path: Path | None = None) -> "Settings":
        settings_path = settings_path or (REPO_ROOT / "config" / "settings.yaml")
        raw = _load_yaml(settings_path)

        email_raw = raw.get("email", {})
        to_addrs_env = os.environ.get("EMAIL_TO", "")
        to_addrs = [a.strip() for a in to_addrs_env.split(",") if a.strip()]

        email = EmailConfig(
            enabled=os.environ.get("EMAIL_ENABLED", "true").lower() != "false",
            smtp_host=email_raw.get("smtp_host", "localhost"),
            smtp_port=int(email_raw.get("smtp_port", 587)),
            use_tls=bool(email_raw.get("use_tls", True)),
            subject_prefix=email_raw.get("subject_prefix", "[Digest]"),
            username=os.environ.get("SMTP_USERNAME"),
            password=os.environ.get("SMTP_PASSWORD"),
            to_addrs=to_addrs,
        )

        storage = raw.get("storage", {})

        return cls(
            raw=raw,
            timezone=raw.get("timezone", "UTC"),
            acquisition=raw.get("acquisition", {}),
            detail_summary=raw.get("detail_summary", {}),
            triage=raw.get("triage", {}),
            cluster=raw.get("cluster", {}),
            diffcheck=raw.get("diffcheck", {}),
            translate=raw.get("translate", {}),
            digest=raw.get("digest", {}),
            email=email,
            db_path=REPO_ROOT / storage.get("db_path", "data/pitch_discovery.db"),
            feedback_csv=REPO_ROOT / storage.get("feedback_csv", "feedback.csv"),
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
        )


def api_key_problem(key: str | None) -> str | None:
    """Returns a human-readable problem description if the Anthropic API key is
    unusable, or None if it looks fine. Catches paste accidents (truncation
    ellipses, arrows, whitespace) before they surface as deep httpx tracebacks."""
    if not key:
        return "ANTHROPIC_API_KEY is not set"
    bad = sorted({c for c in key if not c.isascii() or c.isspace()})
    if bad:
        return (
            f"ANTHROPIC_API_KEY contains invalid character(s) {bad!r} — it was "
            "probably copied from a truncated display. Re-copy the raw key from "
            "console.anthropic.com and update the GitHub Actions secret."
        )
    if not key.startswith("sk-ant-"):
        return "ANTHROPIC_API_KEY does not start with 'sk-ant-' — is it the right value?"
    return None


def load_sources(sources_path: Path | None = None) -> list[dict[str, Any]]:
    sources_path = sources_path or (REPO_ROOT / "sources.yaml")
    raw = _load_yaml(sources_path)
    return raw.get("sources", [])


def enabled_sources(sources_path: Path | None = None) -> list[dict[str, Any]]:
    return [s for s in load_sources(sources_path) if s.get("enabled", True)]
