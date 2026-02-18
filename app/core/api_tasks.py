"""
Async backup tasks for API-driven platforms:
  • Palo Alto Networks (PAN-OS) — XML API
  • Fortinet FortiGate (FortiOS) — REST API

Each function returns a dict compatible with BackupEngine._commit_config.
SSL verification is intentionally disabled for air-gapped self-signed certs.
"""
import hashlib
import logging
import xml.etree.ElementTree as ET
from typing import Any, Dict

import httpx

logger = logging.getLogger(__name__)


async def backup_palo_alto(
    hostname: str,
    ip: str,
    username: str,
    password: str,
    device_id: int,
    timeout: int = 60,
) -> Dict[str, Any]:
    """
    Backup a Palo Alto Networks firewall via the XML API.

    Steps:
      1. POST /api/?type=keygen  → obtain an API key
      2. GET  /api/?type=export&category=configuration  → full running config XML
    """
    api_url = f"https://{ip}/api/"

    async with httpx.AsyncClient(verify=False, timeout=timeout) as client:
        # Step 1: obtain API key
        key_resp = await client.get(
            api_url,
            params={"type": "keygen", "user": username, "passwd": password},
        )
        key_resp.raise_for_status()

        root = ET.fromstring(key_resp.text)
        key_elem = root.find(".//key")
        if key_elem is None or not key_elem.text:
            raise RuntimeError(f"PAN-OS keygen returned no key for {hostname}")

        api_key = key_elem.text

        # Step 2: export running configuration
        cfg_resp = await client.get(
            api_url,
            params={"type": "export", "category": "configuration", "key": api_key},
        )
        cfg_resp.raise_for_status()

    config_text = cfg_resp.text
    config_hash = hashlib.sha256(config_text.encode()).hexdigest()
    logger.info("Backup OK  %s (panos) — %d bytes", hostname, len(config_text))

    return {
        "config": config_text,
        "hash": config_hash,
        "device_id": device_id,
        "hostname": hostname,
        "platform": "panos",
    }


async def backup_fortinet(
    hostname: str,
    ip: str,
    username: str,
    password: str,
    device_id: int,
    timeout: int = 60,
) -> Dict[str, Any]:
    """
    Backup a Fortinet FortiGate appliance via the REST API.

    Steps:
      1. POST /logincheck  → obtain session cookie
      2. GET  /api/v2/monitor/system/config/backup?scope=global  → config file
      3. POST /logout
    """
    base = f"https://{ip}"

    async with httpx.AsyncClient(verify=False, timeout=timeout) as client:
        # Step 1: authenticate
        login_resp = await client.post(
            f"{base}/logincheck",
            data={"username": username, "secretkey": password},
        )
        login_resp.raise_for_status()

        # Fortinet uses a CSRF token returned in a cookie
        csrf_token = client.cookies.get("ccsrftoken", "").strip('"')
        if not csrf_token:
            # Fallback: some versions use a header-based token from the body
            csrf_token = ""

        headers: Dict[str, str] = {}
        if csrf_token:
            headers["X-CSRFTOKEN"] = csrf_token

        # Step 2: download config backup
        cfg_resp = await client.get(
            f"{base}/api/v2/monitor/system/config/backup",
            params={"scope": "global"},
            headers=headers,
        )
        cfg_resp.raise_for_status()

        # Step 3: logout (best-effort)
        try:
            await client.post(f"{base}/logout", headers=headers)
        except Exception:
            pass

    config_text = cfg_resp.text
    config_hash = hashlib.sha256(config_text.encode()).hexdigest()
    logger.info("Backup OK  %s (fortios) — %d bytes", hostname, len(config_text))

    return {
        "config": config_text,
        "hash": config_hash,
        "device_id": device_id,
        "hostname": hostname,
        "platform": "fortios",
    }
