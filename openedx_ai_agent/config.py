"""Campaign configuration, resolved from environment variables and CLI flags."""

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    """Runtime configuration for a campaign run."""

    org: str = "openedx"
    github_token: str | None = None
    campaign_dir: Path = field(default_factory=lambda: Path("campaign"))

    @classmethod
    def from_env(cls, org: str | None = None, campaign_dir: str | None = None) -> "Config":
        return cls(
            org=org or os.environ.get("OEA_ORG", "openedx"),
            github_token=os.environ.get("GITHUB_TOKEN"),
            campaign_dir=Path(campaign_dir or os.environ.get("OEA_CAMPAIGN_DIR", "campaign")),
        )

    @property
    def github_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.github_token:
            headers["Authorization"] = f"Bearer {self.github_token}"
        return headers
