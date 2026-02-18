import logging
import httpx
import json
from typing import Optional
from base64 import b64encode

logger = logging.getLogger(__name__)


class GiteaClient:
    """Async Gitea API client for config management."""

    def __init__(self, base_url: str, token: str, org: str = "agncf"):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.org = org
        self.headers = {
            "Authorization": f"token {token}",
            "Content-Type": "application/json",
        }

    async def ensure_repo(self, site_code: str, repo_name: str) -> str:
        """
        Ensure a repository exists for a site. Creates if not present (idempotent).

        Args:
            site_code: Site identifier
            repo_name: Repository name

        Returns:
            Repository full name (org/repo)
        """
        repo_full_name = f"{self.org}/{repo_name}"

        async with httpx.AsyncClient() as client:
            # Check if repo exists
            check_url = f"{self.base_url}/api/v1/repos/{repo_full_name}"
            try:
                response = await client.get(check_url, headers=self.headers)
                if response.status_code == 200:
                    logger.debug(f"Repository {repo_full_name} already exists")
                    return repo_full_name
            except Exception as e:
                logger.debug(f"Repository check failed: {str(e)}")

            # Create org if needed
            org_url = f"{self.base_url}/api/v1/orgs/{self.org}"
            try:
                response = await client.get(org_url, headers=self.headers)
                if response.status_code != 200:
                    create_org_url = f"{self.base_url}/api/v1/admin/orgs"
                    org_payload = {"username": self.org}
                    try:
                        await client.post(
                            create_org_url,
                            headers=self.headers,
                            json=org_payload,
                            timeout=30
                        )
                        logger.info(f"Created organization: {self.org}")
                    except Exception as e:
                        logger.warning(f"Failed to create org (may already exist): {str(e)}")
            except Exception as e:
                logger.warning(f"Organization check failed: {str(e)}")

            # Create repo
            create_url = f"{self.base_url}/api/v1/admin/users/{self.org}/repos"
            repo_payload = {
                "name": repo_name,
                "description": f"Configuration backup for {site_code}",
                "private": True,
                "auto_init": True,
            }

            try:
                response = await client.post(
                    create_url,
                    headers=self.headers,
                    json=repo_payload,
                    timeout=30
                )
                if response.status_code in (201, 200):
                    logger.info(f"Created repository: {repo_full_name}")
                    return repo_full_name
                else:
                    logger.error(f"Failed to create repo: {response.text}")
                    raise Exception(f"HTTP {response.status_code}: {response.text}")
            except Exception as e:
                logger.error(f"Repository creation failed: {str(e)}")
                raise

    async def commit_config(
        self,
        repo: str,
        device_hostname: str,
        config_text: str,
        commit_message: str
    ) -> str:
        """
        Commit configuration file to repository.

        Args:
            repo: Repository name (with org prefix)
            device_hostname: Device hostname for filename
            config_text: Configuration content
            commit_message: Commit message

        Returns:
            Commit SHA
        """
        filename = f"{device_hostname}.txt"
        file_path = filename

        # Encode content in base64 for API
        encoded_content = b64encode(config_text.encode()).decode()

        async with httpx.AsyncClient() as client:
            # Get current commit SHA (to pass parent)
            get_url = f"{self.base_url}/api/v1/repos/{repo}/contents/{file_path}"
            sha = None

            try:
                response = await client.get(get_url, headers=self.headers)
                if response.status_code == 200:
                    sha = response.json().get("sha")
            except Exception as e:
                logger.debug(f"Could not retrieve existing file: {str(e)}")

            # Commit file
            commit_url = f"{self.base_url}/api/v1/repos/{repo}/contents/{file_path}"
            payload = {
                "content": encoded_content,
                "message": commit_message,
                "branch": "main",
            }

            if sha:
                payload["sha"] = sha

            try:
                response = await client.put(
                    commit_url,
                    headers=self.headers,
                    json=payload,
                    timeout=30
                )

                if response.status_code in (200, 201):
                    result = response.json()
                    commit_sha = result.get("commit", {}).get("sha", "")
                    logger.info(f"Committed {file_path} to {repo}: {commit_sha[:8]}")
                    return commit_sha
                else:
                    logger.error(f"Commit failed: {response.text}")
                    raise Exception(f"HTTP {response.status_code}: {response.text}")
            except Exception as e:
                logger.error(f"File commit failed: {str(e)}")
                raise

    async def get_diff(self, repo: str, device_hostname: str) -> str:
        """
        Retrieve unified diff between latest two commits for a device config.

        Args:
            repo: Repository name (with org prefix)
            device_hostname: Device hostname

        Returns:
            Unified diff string
        """
        filename = f"{device_hostname}.txt"

        async with httpx.AsyncClient() as client:
            # Get commits for this file
            commits_url = f"{self.base_url}/api/v1/repos/{repo}/commits"
            params = {"path": filename}

            try:
                response = await client.get(commits_url, headers=self.headers, params=params, timeout=30)

                if response.status_code != 200:
                    return f"No commits found for {filename}"

                commits = response.json()
                if len(commits) < 2:
                    return f"Insufficient commits to generate diff for {filename}"

                latest_sha = commits[0]["sha"]
                previous_sha = commits[1]["sha"]

                # Get diff between commits
                diff_url = f"{self.base_url}/api/v1/repos/{repo}/compare/{previous_sha}...{latest_sha}"

                diff_response = await client.get(diff_url, headers=self.headers, timeout=30)

                if diff_response.status_code == 200:
                    diff_data = diff_response.json()
                    files = diff_data.get("files", [])

                    if files:
                        diff_text = files[0].get("patch", "")
                        logger.info(f"Retrieved diff for {filename}")
                        return diff_text or "No differences found"
                    else:
                        return "No file differences in this commit"

                else:
                    logger.error(f"Diff retrieval failed: {diff_response.text}")
                    return f"Error retrieving diff: {diff_response.status_code}"

            except Exception as e:
                logger.error(f"Diff retrieval failed: {str(e)}")
                return f"Error retrieving diff: {str(e)}"
