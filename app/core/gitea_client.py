"""
Async Gitea API client.

Responsibilities
────────────────
• ensure_repo(site_code, repo_name) — create an org-level repo if absent (idempotent)
• commit_config(repo, device_hostname, config_text, commit_message)
  — create or update {hostname}.txt in the repo via the Contents API
• get_diff(repo, device_hostname)
  — retrieve unified diff between the two most recent commits for the file
"""
import logging
from base64 import b64encode
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class GiteaClient:
    """Async wrapper around the Gitea v1 REST API."""

    def __init__(self, base_url: str, token: str, org: str = "agncf") -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.org = org
        self._headers = {
            "Authorization": f"token {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # ── Repository management ──────────────────────────────────────────────────

    async def ensure_repo(self, site_code: str, repo_name: str) -> str:
        """
        Ensure {org}/{repo_name} exists.  Creates the repo if absent.
        Returns the full repo name ("{org}/{repo_name}").
        """
        repo_full = f"{self.org}/{repo_name}"

        async with httpx.AsyncClient(timeout=30) as client:
            # Check existence
            resp = await client.get(
                f"{self.base_url}/api/v1/repos/{repo_full}",
                headers=self._headers,
            )
            if resp.status_code == 200:
                logger.debug("Repo %s already exists", repo_full)
                return repo_full

            # Create org if it doesn't exist yet (admin API)
            org_check = await client.get(
                f"{self.base_url}/api/v1/orgs/{self.org}",
                headers=self._headers,
            )
            if org_check.status_code == 404:
                create_org = await client.post(
                    f"{self.base_url}/api/v1/admin/orgs",
                    headers=self._headers,
                    json={
                        "username": self.org,
                        "visibility": "private",
                    },
                    timeout=30,
                )
                if create_org.status_code not in (200, 201):
                    logger.warning(
                        "Could not create org %s (may require admin token): %s",
                        self.org,
                        create_org.text,
                    )

            # Create the repository under the organisation
            create_resp = await client.post(
                f"{self.base_url}/api/v1/orgs/{self.org}/repos",
                headers=self._headers,
                json={
                    "name": repo_name,
                    "description": f"Config backups — site {site_code}",
                    "private": True,
                    "auto_init": True,
                    "default_branch": "main",
                },
                timeout=30,
            )
            if create_resp.status_code in (200, 201):
                logger.info("Created repo %s", repo_full)
                return repo_full

            raise RuntimeError(
                f"Could not create repo {repo_full}: HTTP {create_resp.status_code} — {create_resp.text}"
            )

    # ── File commit ────────────────────────────────────────────────────────────

    async def commit_config(
        self,
        repo: str,
        device_hostname: str,
        config_text: str,
        commit_message: str,
    ) -> str:
        """
        Create or update {device_hostname}.txt in *repo* via the Contents API.

        Returns the commit SHA (empty string if the API does not return one).
        """
        file_path = f"{device_hostname}.txt"
        encoded_content = b64encode(config_text.encode()).decode()

        async with httpx.AsyncClient(timeout=30) as client:
            url = f"{self.base_url}/api/v1/repos/{repo}/contents/{file_path}"

            # Retrieve current file SHA for update requests
            current_sha: Optional[str] = None
            get_resp = await client.get(url, headers=self._headers)
            if get_resp.status_code == 200:
                current_sha = get_resp.json().get("sha")

            payload: dict = {
                "content": encoded_content,
                "message": commit_message,
                "branch": "main",
            }
            if current_sha:
                payload["sha"] = current_sha

            put_resp = await client.put(url, headers=self._headers, json=payload, timeout=60)

        if put_resp.status_code in (200, 201):
            commit_sha: str = put_resp.json().get("commit", {}).get("sha", "")
            logger.info("Committed %s → %s  sha=%s…", file_path, repo, commit_sha[:12])
            return commit_sha

        raise RuntimeError(
            f"Commit failed for {file_path} in {repo}: HTTP {put_resp.status_code} — {put_resp.text}"
        )

    # ── Diff retrieval ─────────────────────────────────────────────────────────

    async def get_diff(self, repo: str, device_hostname: str) -> str:
        """
        Return the unified diff between the two most recent commits that
        touched {device_hostname}.txt.

        Returns a human-readable message string if fewer than 2 commits exist.
        """
        file_path = f"{device_hostname}.txt"

        async with httpx.AsyncClient(timeout=30) as client:
            commits_resp = await client.get(
                f"{self.base_url}/api/v1/repos/{repo}/commits",
                headers=self._headers,
                params={"path": file_path, "limit": 2},
                timeout=30,
            )

        if commits_resp.status_code != 200:
            return f"Could not retrieve commits for {file_path}: HTTP {commits_resp.status_code}"

        commits = commits_resp.json()
        if len(commits) < 2:
            return f"Only {len(commits)} commit(s) found for {file_path} — no diff available yet."

        previous_sha = commits[1]["sha"]
        latest_sha = commits[0]["sha"]

        async with httpx.AsyncClient(timeout=30) as client:
            diff_resp = await client.get(
                f"{self.base_url}/api/v1/repos/{repo}/compare/{previous_sha}...{latest_sha}",
                headers=self._headers,
                timeout=30,
            )

        if diff_resp.status_code != 200:
            return f"Diff API returned HTTP {diff_resp.status_code}"

        diff_data = diff_resp.json()
        files = diff_data.get("files", [])
        if not files:
            return "No file changes in this diff."

        # Find the specific file in the diff result
        for file_info in files:
            if device_hostname in file_info.get("filename", ""):
                patch = file_info.get("patch", "")
                return patch or "File changed but patch is empty."

        return "No changes found for this device in the diff."
