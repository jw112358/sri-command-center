"""app/config.py — settings loaded from .env via pydantic-settings"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Google Drive
    google_service_account_file: str = "./credentials/sri-service-account.json"
    drive_root_folder_id: str = ""
    drive_signals_folder_name: str = "signals"
    drive_poll_interval: int = 30

    # GitHub
    github_token: str = ""
    github_repos: str = ""          # raw comma-separated string
    github_org: str = "sri-intel"

    # Server
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    # Comma-separated allowed origins. In production add your Render frontend URL:
    # e.g. "https://sri-command-center.onrender.com,http://localhost:5173"
    cors_origins: str = "http://localhost:5173,http://localhost:4173,https://sri-command-center.onrender.com"

    # Cache
    cache_ttl: int = 60

    # Legal Agent OS
    legal_enabled: bool = True
    legal_state_db: str = "./data/legal-os-state.db"
    legal_max_active_matters: int = 4
    legal_api_token: str = ""
    legal_gmail_enabled: bool = False
    legal_gmail_shadow_mode: bool = True
    legal_gmail_poll_interval: int = 60
    legal_gmail_intake_label: str = "LegalOS/Intake"
    legal_gmail_processed_label: str = "LegalOS/Processed"
    legal_gmail_needs_review_label: str = "LegalOS/NeedsReview"
    legal_gmail_error_label: str = "LegalOS/Error"
    legal_operator_email: str = "jeff@sri-intel.com"
    legal_drive_matters_folder_id: str = ""
    legal_attachment_max_bytes: int = 25_000_000

    # ── derived helpers ──────────────────────────────────────────────────────
    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def github_repos_list(self) -> List[str]:
        return [r.strip() for r in self.github_repos.split(",") if r.strip()]

    @property
    def drive_enabled(self) -> bool:
        return bool(self.drive_root_folder_id)

    @property
    def github_enabled(self) -> bool:
        return bool(self.github_token)


settings = Settings()
