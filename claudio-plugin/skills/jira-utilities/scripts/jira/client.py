"""Shared Jira REST API client.

Handles authentication for both Jira Cloud (Basic auth) and
Jira Data Center (Bearer token / PAT).

Auth modes (set via JIRA_AUTH_TYPE env var, default: "cloud"):
    cloud      - Basic auth: JIRA_EMAIL + JIRA_TOKEN
    datacenter - Bearer token: JIRA_TOKEN only

Required environment variables:
    JIRA_BASE_URL  - Jira instance URL (e.g., https://yourorg.atlassian.net)
    JIRA_TOKEN     - API token (Cloud) or Personal Access Token (Data Center)
    JIRA_EMAIL     - Atlassian account email (Cloud only, not needed for datacenter)

Exit Codes (for scripts using this client):
    0: Success
    1: Invalid parameters
    2: API error
    3: Not found
    4: Authentication error
"""

import os
import sys
from urllib.parse import urlparse

import requests


def to_adf(text: str) -> dict:
    """Wrap a plain text string in the minimal Atlassian Document Format (ADF).

    Jira REST API v3 requires the description field to be ADF, not a plain string.
    """
    return {
        "version": 1,
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": text}],
            }
        ],
    }


class JiraClient:
    """Jira REST API v3 client with Cloud and Data Center auth support."""

    def __init__(
        self,
        base_url: str = None,
        token: str = None,
        email: str = None,
        auth_type: str = None,
    ):
        """Initialize Jira client.

        Args:
            base_url: Jira instance URL (or from env JIRA_BASE_URL)
            token: Jira API token or PAT (or from env JIRA_TOKEN)
            email: User email for Cloud auth (or from env JIRA_EMAIL)
            auth_type: "cloud" or "datacenter" (or from env JIRA_AUTH_TYPE, default: "cloud")

        Raises:
            ValueError: If required credentials are missing
        """
        raw_url = base_url or os.environ.get("JIRA_BASE_URL")
        if not raw_url:
            raise ValueError("JIRA_BASE_URL must be set")
        parsed = urlparse(raw_url)
        if parsed.scheme != "https":
            raise ValueError(
                f"JIRA_BASE_URL must use HTTPS (got {parsed.scheme!r}). "
                "Sending credentials over plain HTTP is not allowed."
            )
        self.base_url = raw_url.rstrip("/")

        resolved_token = token or os.environ.get("JIRA_TOKEN")
        if not resolved_token:
            raise ValueError("JIRA_TOKEN must be set")

        self.auth_type = auth_type or os.getenv("JIRA_AUTH_TYPE", "cloud")
        _VALID_AUTH_TYPES = ("cloud", "datacenter")
        if self.auth_type not in _VALID_AUTH_TYPES:
            raise ValueError(
                f"JIRA_AUTH_TYPE must be one of {_VALID_AUTH_TYPES}, got {self.auth_type!r}"
            )

        self.session = requests.Session()
        self.session.verify = True  # explicit; do not allow env vars to downgrade this
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
        })

        if self.auth_type == "cloud":
            resolved_email = email or os.environ.get("JIRA_EMAIL")
            if not resolved_email:
                raise ValueError("JIRA_EMAIL must be set for Cloud auth")
            self.session.auth = (resolved_email, resolved_token)
        else:
            self.session.headers["Authorization"] = f"Bearer {resolved_token}"

    def get(self, path: str, **kwargs) -> dict:
        """Make a GET request to the Jira API.

        Args:
            path: API path (e.g., "/rest/api/2/issue/PROJ-1")
            **kwargs: Extra args passed to requests.get

        Returns:
            Parsed JSON response

        Raises:
            ValueError: On authentication failure (401/403)
            LookupError: On not found (404)
            RuntimeError: On other API errors
        """
        try:
            resp = self.session.get(
                f"{self.base_url}{path}", timeout=30, **kwargs
            )
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Jira API request failed: {e}") from e

        self._raise_for_status(resp)
        return resp.json()

    def post(self, path: str, **kwargs) -> dict:
        """Make a POST request to the Jira API.

        Args:
            path: API path
            **kwargs: Extra args passed to requests.post

        Returns:
            Parsed JSON response

        Raises:
            ValueError: On authentication failure
            RuntimeError: On API errors
        """
        try:
            resp = self.session.post(
                f"{self.base_url}{path}", timeout=30, **kwargs
            )
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Jira API request failed: {e}") from e

        self._raise_for_status(resp)
        # 204 No Content is valid for some POST responses
        if resp.status_code == 204 or not resp.content:
            return {}
        return resp.json()

    def put(self, path: str, **kwargs) -> dict:
        """Make a PUT request to the Jira API.

        Args:
            path: API path
            **kwargs: Extra args passed to requests.put

        Returns:
            Parsed JSON response (empty dict for 204 No Content)

        Raises:
            ValueError: On authentication failure
            LookupError: On not found
            RuntimeError: On API errors
        """
        try:
            resp = self.session.put(
                f"{self.base_url}{path}", timeout=30, **kwargs
            )
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Jira API request failed: {e}") from e

        self._raise_for_status(resp)
        if resp.status_code == 204 or not resp.content:
            return {}
        return resp.json()

    def _raise_for_status(self, resp: requests.Response) -> None:
        """Raise typed exceptions based on HTTP status code.

        Args:
            resp: HTTP response object

        Raises:
            ValueError: On 401/403 (authentication/authorization failure)
            LookupError: On 404 (not found)
            RuntimeError: On other 4xx/5xx errors
        """
        if resp.status_code in (401, 403):
            raise ValueError(
                f"Authentication failed (HTTP {resp.status_code}): "
                "check JIRA_TOKEN and JIRA_EMAIL"
            )
        if resp.status_code == 404:
            raise LookupError(f"Resource not found: {resp.url}")
        if resp.status_code >= 400:
            _MAX_ERROR_DETAIL = 500
            try:
                body = resp.json()
                messages = body.get("errorMessages", [])
                errors = body.get("errors", {})
                detail = "; ".join(messages) or str(errors) or (resp.text or "")
            except Exception:
                detail = resp.text or ""
            if len(detail) > _MAX_ERROR_DETAIL:
                detail = detail[:_MAX_ERROR_DETAIL] + "... [truncated]"
            raise RuntimeError(
                f"Jira API error (HTTP {resp.status_code}): {detail}"
            )
