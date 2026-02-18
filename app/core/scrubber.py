import re
from typing import Dict, List, Callable


class ConfigScrubber:
    """Platform-aware configuration scrubbing engine."""

    def __init__(self):
        self.patterns = self._build_patterns()

    def _build_patterns(self) -> Dict[str, List[tuple[str, str]]]:
        """Build regex patterns for each platform."""
        return {
            "ios": [
                (r"uptime is .+", "uptime is <removed>"),
                (r"Last configuration change at .+", "Last configuration change at <removed>"),
                (r"ntp clock-period \d+", "ntp clock-period <removed>"),
                (r"crypto pki certificate.*?^(?=\S)", "<crypto-cert-removed>"),
                (r"Current configuration : .+", "Current configuration : <removed>"),
                (r"router rip\n.*?(?=^[a-z])", "router rip\n<rip-config-removed>"),
            ],
            "nxos": [
                (r"System uptime:.+", "System uptime: <removed>"),
                (r"Last configuration change at .+", "Last configuration change at <removed>"),
                (r"crypto pki certificate.*?^(?=\S)", "<crypto-cert-removed>"),
                (r"module-number: \d+", "module-number: <removed>"),
                (r"serial-number: \S+", "serial-number: <removed>"),
            ],
            "eos": [
                (r"System uptime:.+", "System uptime: <removed>"),
                (r"Last configuration change at .+", "Last configuration change at <removed>"),
                (r"hostname \S+", "hostname <removed>"),
                (r"Management Hostname:.+", "Management Hostname: <removed>"),
            ],
            "dellos10": [
                (r"Current date/time is.+", "Current date/time is <removed>"),
                (r"System uptime is .+", "System uptime is <removed>"),
                (r"Last configuration change on .+", "Last configuration change on <removed>"),
            ],
            "panos": [
                (r"<serial>.*?</serial>", "<serial><removed></serial>"),
                (r"<uptime>.*?</uptime>", "<uptime><removed></uptime>"),
                (r"<time>.*?</time>", "<time><removed></time>"),
                (r"<app-version>.*?</app-version>", "<app-version><removed></app-version>"),
                (r"<threat-version>.*?</threat-version>", "<threat-version><removed></threat-version>"),
                (r"<antivirus-version>.*?</antivirus-version>", "<antivirus-version><removed></antivirus-version>"),
                (r"<wildfire-version>.*?</wildfire-version>", "<wildfire-version><removed></wildfire-version>"),
            ],
            "fortios": [
                (r"uuid = \"[^\"]+\"", "uuid = \"<removed>\""),
                (r"timestamp = \d+", "timestamp = <removed>"),
                (r"lastupdate = \d+", "lastupdate = <removed>"),
                (r"build = \d+", "build = <removed>"),
            ],
            "common": [
                (r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}", "<timestamp>"),
                (r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", "<ip-address>"),
            ],
        }

    def scrub_config(self, raw_config: str, platform: str) -> str:
        """
        Scrub dynamic/sensitive fields from network configuration.

        Args:
            raw_config: Raw configuration text
            platform: Platform type (ios, nxos, eos, dellos10, panos, fortios)

        Returns:
            Scrubbed configuration text
        """
        scrubbed = raw_config

        # Apply platform-specific patterns
        if platform in self.patterns:
            for pattern, replacement in self.patterns[platform]:
                scrubbed = re.sub(pattern, replacement, scrubbed, flags=re.MULTILINE | re.DOTALL)

        # Apply common patterns
        for pattern, replacement in self.patterns.get("common", []):
            if not self._pattern_already_processed(pattern, platform):
                scrubbed = re.sub(pattern, replacement, scrubbed, flags=re.MULTILINE)

        return scrubbed.strip()

    def _pattern_already_processed(self, pattern: str, platform: str) -> bool:
        """Check if a pattern was already processed in platform-specific rules."""
        if platform not in self.patterns:
            return False

        for plat_pattern, _ in self.patterns[platform]:
            if plat_pattern == pattern:
                return True

        return False


def scrub_config(raw: str, platform: str) -> str:
    """
    Public function to scrub configuration.

    Args:
        raw: Raw configuration text
        platform: Platform identifier

    Returns:
        Scrubbed configuration text
    """
    scrubber = ConfigScrubber()
    return scrubber.scrub_config(raw, platform)
