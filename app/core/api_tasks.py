import logging
import hashlib
import httpx
import xml.etree.ElementTree as ET
from typing import Dict, Any, Tuple
from urllib.parse import urljoin

logger = logging.getLogger(__name__)


async def backup_palo_alto(
    hostname: str,
    ip: str,
    username: str,
    password: str,
    device_id: int,
    timeout: int = 30
) -> Dict[str, Any]:
    """
    Backup Palo Alto Networks configuration via XML API.

    Returns:
        Dictionary with config, hash, device_id, hostname, platform
    """
    try:
        async with httpx.AsyncClient(verify=False, timeout=timeout) as client:
            # Get API key
            api_url = f"https://{ip}/api/"
            key_params = {
                "type": "keygen",
                "user": username,
                "passwd": password,
            }

            key_response = await client.get(
                api_url,
                params=key_params,
                verify=False
            )

            if key_response.status_code != 200:
                raise Exception(f"Failed to get API key: {key_response.text}")

            # Parse API key from XML response
            root = ET.fromstring(key_response.text)
            api_key_elem = root.find(".//key")
            if api_key_elem is None or not api_key_elem.text:
                raise Exception("No API key in response")

            api_key = api_key_elem.text

            # Get running config
            config_params = {
                "type": "export",
                "category": "configuration",
                "key": api_key,
            }

            config_response = await client.get(
                api_url,
                params=config_params,
                verify=False
            )

            if config_response.status_code != 200:
                raise Exception(f"Failed to get config: {config_response.text}")

            config_text = config_response.text
            config_hash = hashlib.sha256(config_text.encode()).hexdigest()

            logger.info(f"Backed up Palo Alto {hostname}: {len(config_text)} bytes, hash={config_hash[:8]}")

            return {
                "config": config_text,
                "hash": config_hash,
                "device_id": device_id,
                "hostname": hostname,
                "platform": "panos",
            }

    except Exception as e:
        logger.error(f"Failed to backup Palo Alto {hostname}: {str(e)}")
        raise


async def backup_fortinet(
    hostname: str,
    ip: str,
    username: str,
    password: str,
    device_id: int,
    timeout: int = 30
) -> Dict[str, Any]:
    """
    Backup Fortinet FortiGate configuration via REST API.

    Returns:
        Dictionary with config, hash, device_id, hostname, platform
    """
    try:
        async with httpx.AsyncClient(verify=False, timeout=timeout) as client:
            # Authenticate and get token
            auth_url = f"https://{ip}/api/v2/auth/login"
            auth_data = {
                "username": username,
                "password": password,
            }

            auth_response = await client.post(
                auth_url,
                data=auth_data,
                verify=False
            )

            if auth_response.status_code != 200:
                raise Exception(f"Authentication failed: {auth_response.text}")

            auth_result = auth_response.json()
            token = auth_result.get("access_token")
            if not token:
                raise Exception("No access token in auth response")

            # Get running config
            config_url = f"https://{ip}/api/v2/monitor/system/config/backup"
            headers = {
                "Authorization": f"Bearer {token}",
            }

            config_response = await client.get(
                config_url,
                headers=headers,
                verify=False
            )

            if config_response.status_code != 200:
                raise Exception(f"Failed to get config: {config_response.text}")

            config_text = config_response.text
            config_hash = hashlib.sha256(config_text.encode()).hexdigest()

            logger.info(f"Backed up Fortinet {hostname}: {len(config_text)} bytes, hash={config_hash[:8]}")

            return {
                "config": config_text,
                "hash": config_hash,
                "device_id": device_id,
                "hostname": hostname,
                "platform": "fortios",
            }

    except Exception as e:
        logger.error(f"Failed to backup Fortinet {hostname}: {str(e)}")
        raise
