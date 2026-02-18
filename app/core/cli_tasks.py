"""
Nornir task for CLI-based device backup (Cisco IOS/NX-OS, Arista EOS, Dell OS10).

Nornir tasks MUST be synchronous — Nornir runs them in a ThreadPoolExecutor.
We call Netmiko directly rather than via task.run(netmiko_send_command) to
keep the MultiResult structure simple: one Result per host, no sub-results.
"""
import hashlib
import logging

from netmiko import ConnectHandler
from nornir.core.task import Result, Task

logger = logging.getLogger(__name__)

_CONFIG_COMMANDS: dict[str, str] = {
    "cisco_ios": "show running-config",
    "cisco_nxos": "show running-config",
    "arista_eos": "show running-config",
    "dell_os10": "show running-configuration",
}


def _config_command(netmiko_platform: str) -> str:
    return _CONFIG_COMMANDS.get(netmiko_platform, "show running-config")


def backup_config_cli(task: Task) -> Result:
    """
    Connect to a device via SSH, retrieve the running configuration, and
    return it in the Result.  Raises on any error so Nornir marks the host
    as failed and stores the exception for later processing.
    """
    host = task.host
    device_id: int = host.data["device_id"]
    platform: str = host.data["platform"]
    netmiko_platform: str = host.platform  # already mapped in the inventory

    logger.info("Connecting to %s (%s) …", host.name, netmiko_platform)

    conn_params = {
        "device_type": netmiko_platform,
        "host": host.hostname,
        "username": host.username,
        "password": host.password,
        "port": host.port or 22,
        "timeout": 60,
        "session_timeout": 120,
        "global_delay_factor": 2,
    }

    with ConnectHandler(**conn_params) as conn:
        command = _config_command(netmiko_platform)
        config_text: str = conn.send_command(command, read_timeout=120)

    config_hash = hashlib.sha256(config_text.encode()).hexdigest()
    logger.info(
        "Backup OK  %s — %d bytes  sha256=%s…",
        host.name,
        len(config_text),
        config_hash[:12],
    )

    return Result(
        host=host,
        result={
            "config": config_text,
            "hash": config_hash,
            "device_id": device_id,
            "platform": platform,
            "hostname": host.name,
        },
    )
