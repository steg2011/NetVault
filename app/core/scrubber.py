"""
Platform-aware configuration scrubbing engine.

scrub_config(raw, platform) strips dynamic / volatile fields from a device
configuration before it is committed to Gitea.  This prevents noisy diffs
caused by counters, timestamps, certificates, and ephemeral UUIDs.

Stripped per platform
─────────────────────
IOS/NX-OS    uptime, last-config-change, ntp clock-period, crypto PKI cert blocks
EOS          uptime, last-config-change, management hostname
Dell OS10    date/time, uptime, last-config-change
PAN-OS       serial, uptime, app/threat/antivirus/wildfire version tags
FortiOS      uuid=, timestamp=, lastupdate=, build=

Common (all) NTP timestamps embedded in config lines (ISO-8601 style)
"""
import re
from typing import Dict, List, Tuple

# Each entry is (regex_pattern, replacement_string).
# re.MULTILINE is always applied; re.DOTALL only where noted.
PatternList = List[Tuple[str, str]]

_PATTERNS: Dict[str, PatternList] = {
    "ios": [
        # Use [^\n]+ so these never swallow past the end of the line,
        # even when re.DOTALL is active for the crypto block below.
        (r"uptime is [^\n]+",                             "uptime is <removed>"),
        (r"Last configuration change at [^\n]+",          "Last configuration change at <removed>"),
        (r"ntp clock-period \d+",                         "ntp clock-period <removed>"),
        (r"Current configuration : \d+ bytes",            "Current configuration : <removed> bytes"),
        # Multi-line crypto PKI certificate block — requires re.DOTALL.
        (
            r"^crypto pki certificate .+?(?=\n\S|\Z)",
            "<crypto-pki-cert-block-removed>",
        ),
    ],
    "nxos": [
        (r"System uptime:[^\n]+",                         "System uptime: <removed>"),
        (r"Last configuration change at [^\n]+",          "Last configuration change at <removed>"),
        (r"serial-number: \S+",                           "serial-number: <removed>"),
        (r"module-number: \d+",                           "module-number: <removed>"),
        (
            r"^crypto pki certificate .+?(?=\n\S|\Z)",
            "<crypto-pki-cert-block-removed>",
        ),
    ],
    "eos": [
        (r"System uptime:[^\n]+",                         "System uptime: <removed>"),
        (r"Last configuration change at [^\n]+",          "Last configuration change at <removed>"),
        (r"Management Hostname:[^\n]+",                   "Management Hostname: <removed>"),
    ],
    "dellos10": [
        (r"Current date/time is[^\n]+",                   "Current date/time is <removed>"),
        (r"System uptime is [^\n]+",                      "System uptime is <removed>"),
        (r"Last configuration change on [^\n]+",          "Last configuration change on <removed>"),
    ],
    "panos": [
        (r"<serial>.*?</serial>",                         "<serial><removed></serial>"),
        (r"<uptime>.*?</uptime>",                         "<uptime><removed></uptime>"),
        (r"<time>.*?</time>",                             "<time><removed></time>"),
        (r"<app-version>.*?</app-version>",               "<app-version><removed></app-version>"),
        (r"<threat-version>.*?</threat-version>",         "<threat-version><removed></threat-version>"),
        (r"<antivirus-version>.*?</antivirus-version>",   "<antivirus-version><removed></antivirus-version>"),
        (r"<wildfire-version>.*?</wildfire-version>",     "<wildfire-version><removed></wildfire-version>"),
    ],
    "fortios": [
        (r'uuid\s*=\s*"[^"]*"',                          'uuid = "<removed>"'),
        (r"timestamp\s*=\s*\d+",                          "timestamp = <removed>"),
        (r"lastupdate\s*=\s*\d+",                         "lastupdate = <removed>"),
        (r"build\s*=\s*\d+",                              "build = <removed>"),
    ],
    # Applied to every platform after platform-specific patterns.
    "_common": [
        # ISO-8601-style timestamps — [^\n]* ensures we never cross a line boundary
        (r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?",
         "<timestamp>"),
    ],
}

# Platforms whose certificate blocks span multiple lines
_DOTALL_PLATFORMS = {"ios", "nxos"}


def scrub_config(raw: str, platform: str) -> str:
    """
    Remove dynamic fields from *raw* config text for *platform*.

    Args:
        raw:      Raw configuration text as returned by the device.
        platform: Platform identifier matching PlatformEnum values
                  (ios, nxos, eos, dellos10, panos, fortios).

    Returns:
        Scrubbed configuration text, stripped of leading/trailing whitespace.
    """
    if not raw:
        return raw

    scrubbed = raw
    flags_base = re.MULTILINE
    flags_dotall = re.MULTILINE | re.DOTALL

    # Platform-specific patterns
    for pattern, replacement in _PATTERNS.get(platform, []):
        flags = flags_dotall if platform in _DOTALL_PLATFORMS else flags_base
        scrubbed = re.sub(pattern, replacement, scrubbed, flags=flags)

    # Common patterns applied to every platform
    for pattern, replacement in _PATTERNS["_common"]:
        scrubbed = re.sub(pattern, replacement, scrubbed, flags=flags_base)

    return scrubbed.strip()


class ConfigScrubber:
    """
    Thin class wrapper around scrub_config for backwards compatibility
    and test usage.
    """

    def scrub_config(self, raw_config: str, platform: str) -> str:
        return scrub_config(raw_config, platform)
