"""
Unit tests for app/core/scrubber.py.

Covers all six supported platforms with at least one test each, plus edge-case
and cross-platform tests.  No network or DB access required.
"""
import pytest
from app.core.scrubber import ConfigScrubber, scrub_config


# ── Common / cross-platform ────────────────────────────────────────────────────

class TestCommonPatterns:
    def test_iso_timestamp_replaced(self):
        config = "! Generated 2025-02-18T14:30:45"
        result = scrub_config(config, "ios")
        assert "2025-02-18T14:30:45" not in result
        assert "<timestamp>" in result

    def test_iso_timestamp_with_tz_offset_replaced(self):
        config = "! Saved at 2025-02-18 14:30:45+00:00"
        result = scrub_config(config, "nxos")
        assert "2025-02-18 14:30:45" not in result

    def test_empty_config_returns_empty(self):
        assert scrub_config("", "ios") == ""

    def test_unknown_platform_applies_common_only(self):
        """An unrecognised platform should still apply common patterns."""
        config = "timestamp 2025-01-01T00:00:00"
        result = scrub_config(config, "unknown_platform")
        # The ISO timestamp should be replaced by the common pattern
        assert "2025-01-01T00:00:00" not in result

    def test_static_config_preserved(self):
        config = "interface Ethernet0\n description Core uplink\n bandwidth 1000000"
        result = scrub_config(config, "ios")
        assert "Ethernet0" in result
        assert "Core uplink" in result
        assert "bandwidth 1000000" in result

    def test_multiline_structure_preserved(self):
        config = (
            "hostname router-01\n"
            "uptime is 5 days, 1 hour\n"
            "interface Loopback0\n"
            " ip address 10.0.0.1 255.255.255.255\n"
        )
        result = scrub_config(config, "ios")
        assert "router-01" in result
        assert "Loopback0" in result
        assert "5 days" not in result


# ── Cisco IOS ──────────────────────────────────────────────────────────────────

class TestCiscoIOS:
    def test_uptime_removed(self):
        result = scrub_config("uptime is 45 days, 3 hours, 22 minutes", "ios")
        assert "45 days" not in result
        assert "<removed>" in result

    def test_last_config_change_removed(self):
        result = scrub_config(
            "Last configuration change at 10:45:23 UTC Tue Feb 18 2025", "ios"
        )
        assert "10:45:23 UTC" not in result

    def test_ntp_clock_period_removed(self):
        config = "version 15.2\nntp clock-period 36621\nhostname r1"
        result = scrub_config(config, "ios")
        assert "36621" not in result
        assert "hostname r1" in result

    def test_current_configuration_size_removed(self):
        config = "Current configuration : 12345 bytes"
        result = scrub_config(config, "ios")
        assert "12345" not in result

    def test_crypto_pki_cert_block_removed(self):
        config = (
            "crypto pki certificate chain TP-self-signed-1234567890\n"
            " certificate self-signed 01\n"
            "  3082024B 308201B4 A0030201 02020101 300D0609\n"
            "  some more hex data\n"
            "router bgp 65000\n"
        )
        result = scrub_config(config, "ios")
        assert "3082024B" not in result
        assert "router bgp 65000" in result

    def test_static_acl_preserved(self):
        config = "ip access-list extended PERMIT_ALL\n permit ip any any\n deny ip any any log"
        result = scrub_config(config, "ios")
        assert "PERMIT_ALL" in result
        assert "permit ip any any" in result


# ── Cisco NX-OS ───────────────────────────────────────────────────────────────

class TestCiscoNXOS:
    def test_system_uptime_removed(self):
        result = scrub_config("System uptime: 30 days, 15 hours, 45 minutes", "nxos")
        assert "30 days" not in result

    def test_last_config_change_removed(self):
        result = scrub_config(
            "Last configuration change at 02:15:30 UTC Fri Feb 14 2025", "nxos"
        )
        assert "02:15:30" not in result

    def test_serial_number_removed(self):
        config = "serial-number: ABC123XYZ789"
        result = scrub_config(config, "nxos")
        assert "ABC123XYZ789" not in result
        assert "<removed>" in result

    def test_module_number_removed(self):
        result = scrub_config("module-number: 3", "nxos")
        assert "module-number: 3" not in result

    def test_hostname_preserved(self):
        result = scrub_config("hostname nxos-spine-01", "nxos")
        assert "nxos-spine-01" in result


# ── Arista EOS ────────────────────────────────────────────────────────────────

class TestAristaEOS:
    def test_system_uptime_removed(self):
        result = scrub_config("System uptime: 60 days, 8 hours, 12 minutes", "eos")
        assert "60 days" not in result

    def test_last_config_change_removed(self):
        result = scrub_config(
            "Last configuration change at 09:00:00 UTC Mon Jan 01 2025", "eos"
        )
        assert "09:00:00" not in result

    def test_management_hostname_removed(self):
        result = scrub_config("Management Hostname: mgmt.example.local", "eos")
        assert "mgmt.example.local" not in result
        assert "<removed>" in result

    def test_domain_name_preserved(self):
        result = scrub_config("ip domain-name example.com", "eos")
        assert "example.com" in result


# ── Dell OS10 ─────────────────────────────────────────────────────────────────

class TestDellOS10:
    def test_current_datetime_removed(self):
        result = scrub_config(
            "Current date/time is Mon Feb 18 14:30:45 UTC 2025", "dellos10"
        )
        assert "14:30:45" not in result
        assert "<removed>" in result

    def test_system_uptime_removed(self):
        result = scrub_config("System uptime is 12 days 5 hours 30 minutes", "dellos10")
        assert "12 days" not in result

    def test_last_config_change_removed(self):
        result = scrub_config(
            "Last configuration change on 2025-02-18 at 10:15:30", "dellos10"
        )
        assert "10:15:30" not in result

    def test_interface_config_preserved(self):
        config = "interface ethernet 1/1/1\n description Uplink\n no shutdown"
        result = scrub_config(config, "dellos10")
        assert "ethernet 1/1/1" in result
        assert "Uplink" in result


# ── Palo Alto Networks (PAN-OS) ───────────────────────────────────────────────

class TestPaloAlto:
    def test_serial_removed(self):
        config = "<config>\n  <serial>PA-5220-ABC123DEF456</serial>\n</config>"
        result = scrub_config(config, "panos")
        assert "PA-5220-ABC123DEF456" not in result
        assert "<serial><removed></serial>" in result

    def test_uptime_removed(self):
        result = scrub_config("<uptime>45 days 3 hours 22 minutes</uptime>", "panos")
        assert "45 days" not in result
        assert "<uptime><removed></uptime>" in result

    def test_app_version_removed(self):
        result = scrub_config("<app-version>8755-7032</app-version>", "panos")
        assert "8755-7032" not in result

    def test_threat_version_removed(self):
        result = scrub_config("<threat-version>8555-6521</threat-version>", "panos")
        assert "8555-6521" not in result

    def test_antivirus_version_removed(self):
        result = scrub_config("<antivirus-version>4333-4720</antivirus-version>", "panos")
        assert "4333-4720" not in result

    def test_wildfire_version_removed(self):
        result = scrub_config("<wildfire-version>680803-681029</wildfire-version>", "panos")
        assert "680803-681029" not in result

    def test_time_tag_removed(self):
        result = scrub_config("<time>2025/02/18 14:30:45</time>", "panos")
        assert "2025/02/18" not in result

    def test_static_config_preserved(self):
        config = "<address><entry name='web-srv'><ip-netmask>10.0.1.10/32</ip-netmask></entry></address>"
        result = scrub_config(config, "panos")
        assert "web-srv" in result
        assert "10.0.1.10/32" in result


# ── Fortinet FortiOS ──────────────────────────────────────────────────────────

class TestFortinet:
    def test_uuid_removed(self):
        config = 'config system interface\n    edit "port1"\n    set uuid "f47ac10b-58cc-4372-a567-0e02b2c3d479"'
        result = scrub_config(config, "fortios")
        assert "f47ac10b" not in result
        assert '"<removed>"' in result

    def test_timestamp_removed(self):
        result = scrub_config("timestamp = 1645180845", "fortios")
        assert "1645180845" not in result
        assert "<removed>" in result

    def test_lastupdate_removed(self):
        result = scrub_config("lastupdate = 1645180845", "fortios")
        assert "1645180845" not in result

    def test_build_removed(self):
        result = scrub_config("build = 1574", "fortios")
        assert "build = 1574" not in result

    def test_static_policy_preserved(self):
        config = 'config firewall policy\n    edit 1\n    set name "Allow_Internal"\n    set action accept'
        result = scrub_config(config, "fortios")
        assert "Allow_Internal" in result
        assert "accept" in result


# ── Wrapper function ──────────────────────────────────────────────────────────

class TestScrubConfigWrapper:
    def test_module_function_matches_class(self):
        config = "uptime is 10 days, 5 hours"
        assert scrub_config(config, "ios") == ConfigScrubber().scrub_config(config, "ios")

    def test_whitespace_stripped(self):
        config = "\n\n  hostname r1\n\n"
        result = scrub_config(config, "ios")
        assert result == result.strip()
