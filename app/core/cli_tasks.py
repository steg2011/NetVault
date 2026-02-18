import logging
import hashlib
from nornir.core.task import Task, Result
from nornir_netmiko.tasks import netmiko_send_command

logger = logging.getLogger(__name__)


def get_config_command(device_type: str) -> str:
    """Map device type to config retrieval command."""
    command_map = {
        "cisco_ios": "show running-config",
        "cisco_nxos": "show running-config",
        "arista_eos": "show running-config",
        "dell_os10": "show running-config",
    }
    return command_map.get(device_type, "show running-config")


async def backup_config_cli(task: Task) -> Result:
    """
    Backup configuration from CLI-based devices using Netmiko.

    Expected task inputs:
        - None (uses host data)

    Returns:
        Result with config text in result.result
    """
    device = task.host
    platform = device.platform
    device_id = device.data.get("device_id")

    try:
        command = get_config_command(platform)

        # Execute command via netmiko
        cmd_result = await task.run(
            netmiko_send_command,
            command_string=command,
            use_textfsm=False
        )

        config_text = cmd_result.result
        config_hash = hashlib.sha256(config_text.encode()).hexdigest()

        logger.info(f"Backed up {device.name} ({platform}): {len(config_text)} bytes, hash={config_hash[:8]}")

        return Result(
            host=task.host,
            result={
                "config": config_text,
                "hash": config_hash,
                "device_id": device_id,
                "hostname": device.name,
                "platform": platform,
            },
            changed=False
        )

    except Exception as e:
        logger.error(f"Failed to backup {device.name}: {str(e)}")
        return Result(
            host=task.host,
            failed=True,
            exception=e,
            result={
                "error": str(e),
                "device_id": device_id,
                "hostname": device.name,
            }
        )
