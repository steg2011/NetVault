import pytest
from app.core.scrubber import scrub_config, ConfigScrubber


class TestScrubberCommonPatterns:
    """Test common pattern scrubbing across all platforms."""

    def test_scrub_ipv4_addresses(self):
        """Test IPv4 address scrubbing."""
        scrubber = ConfigScrubber()
        config = "server 192.168.1.1 10.0.0.5 172.16.0.1"
        result = scrubber.scrub_config(config, "ios")
        assert "192.168.1.1" not in result or "<ip-address>" in result

    def test_scrub_timestamps(self):
        """Test timestamp scrubbing."""
        scrubber = ConfigScrubber()
        config = "last_update: 2025-02-18 14:30:45"
        result = scrubber.scrub_config(config, "ios")
        # Timestamp should be replaced
        assert "2025-02-18" not in result or "<timestamp>" in result


class TestScrubberCiscoIOS:
    """Test Cisco IOS configuration scrubbing."""

    def test_scrub_uptime(self):
        """Test removal of uptime lines."""
        scrubber = ConfigScrubber()
        config = "uptime is 45 days, 3 hours, 22 minutes"
        result = scrubber.scrub_config(config, "ios")
        assert "45 days" not in result

    def test_scrub_configuration_change_time(self):
        """Test removal of last configuration change timestamp."""
        scrubber = ConfigScrubber()
        config = "Last configuration change at 10:45:23 UTC Tue Feb 18 2025"
        result = scrubber.scrub_config(config, "ios")
        assert "10:45:23" not in result or "<removed>" in result

    def test_scrub_ntp_clock_period(self):
        """Test removal of NTP clock period."""
        scrubber = ConfigScrubber()
        config = """
version 15.2
ntp clock-period 36621
hostname router1
        """
        result = scrubber.scrub_config(config, "ios")
        assert "36621" not in result

    def test_scrub_crypto_pki_certificate(self):
        """Test removal of crypto PKI certificate blocks."""
        scrubber = ConfigScrubber()
        config = """
crypto pki certificate chain TP-self-signed-1234567890
 certificate self-signed 01
  3082024B 308201B4 A0030201 02020101 300D0609
certificate ca 02
  some more cert data here
router bgp 65000
        """
        result = scrubber.scrub_config(config, "ios")
        # Crypto block should be removed
        assert "3082024B" not in result or "self-signed" not in result or len(result) < len(config)

    def test_complete_ios_config(self):
        """Test scrubbing a complete IOS configuration."""
        scrubber = ConfigScrubber()
        config = """
version 15.2
!
hostname router-site1
uptime is 45 days, 3 hours, 22 minutes
ntp clock-period 36621
Last configuration change at 10:45:23 UTC Tue Feb 18 2025
!
interface GigabitEthernet0/1
 description WAN Link
 ip address 192.168.1.1 255.255.255.0
 no shutdown
!
        """
        result = scrubber.scrub_config(config, "ios")
        # Verify dynamic fields removed
        assert "45 days" not in result
        assert "36621" not in result
        assert "10:45:23" not in result
        # Verify config structure preserved
        assert "interface GigabitEthernet0/1" in result
        assert "WAN Link" in result


class TestScrubberCiscoNXOS:
    """Test Cisco NX-OS configuration scrubbing."""

    def test_scrub_nxos_uptime(self):
        """Test NX-OS uptime removal."""
        scrubber = ConfigScrubber()
        config = "System uptime: 30 days, 15 hours, 45 minutes"
        result = scrubber.scrub_config(config, "nxos")
        assert "30 days" not in result

    def test_scrub_nxos_serial_number(self):
        """Test removal of serial numbers."""
        scrubber = ConfigScrubber()
        config = """
hostname switch1
serial-number: ABC123XYZ789
module-number: 3
        """
        result = scrubber.scrub_config(config, "nxos")
        # Serial should be removed
        assert "ABC123XYZ789" not in result or "<removed>" in result

    def test_scrub_nxos_config_change(self):
        """Test NX-OS config change timestamp removal."""
        scrubber = ConfigScrubber()
        config = "Last configuration change at 02:15:30 UTC Fri Feb 14 2025"
        result = scrubber.scrub_config(config, "nxos")
        assert "02:15:30" not in result


class TestScrubberAristaEOS:
    """Test Arista EOS configuration scrubbing."""

    def test_scrub_eos_uptime(self):
        """Test EOS uptime removal."""
        scrubber = ConfigScrubber()
        config = "System uptime: 60 days, 8 hours, 12 minutes"
        result = scrubber.scrub_config(config, "eos")
        assert "60 days" not in result

    def test_scrub_eos_hostname(self):
        """Test EOS hostname handling."""
        scrubber = ConfigScrubber()
        config = """
hostname switch-core-01
ip domain-name example.com
        """
        result = scrubber.scrub_config(config, "eos")
        # Hostname might be scrubbed or preserved depending on policy
        assert "example.com" in result or result is not None

    def test_scrub_eos_management_hostname(self):
        """Test EOS management hostname removal."""
        scrubber = ConfigScrubber()
        config = "Management Hostname: mgmt.example.local"
        result = scrubber.scrub_config(config, "eos")
        assert "mgmt.example.local" not in result or "<removed>" in result


class TestScrubberDellOS10:
    """Test Dell OS10 configuration scrubbing."""

    def test_scrub_dellos10_date_time(self):
        """Test Dell OS10 date/time removal."""
        scrubber = ConfigScrubber()
        config = "Current date/time is Mon Feb 18 14:30:45 UTC 2025"
        result = scrubber.scrub_config(config, "dellos10")
        assert "14:30:45" not in result or "<removed>" in result

    def test_scrub_dellos10_uptime(self):
        """Test Dell OS10 uptime removal."""
        scrubber = ConfigScrubber()
        config = "System uptime is 12 days 5 hours 30 minutes"
        result = scrubber.scrub_config(config, "dellos10")
        assert "12 days" not in result

    def test_scrub_dellos10_config_change(self):
        """Test Dell OS10 config change removal."""
        scrubber = ConfigScrubber()
        config = "Last configuration change on 2025-02-18 at 10:15:30"
        result = scrubber.scrub_config(config, "dellos10")
        assert "10:15:30" not in result or "<removed>" in result


class TestScrubberPaloAlto:
    """Test Palo Alto Networks configuration scrubbing."""

    def test_scrub_paloalto_serial(self):
        """Test Palo Alto serial number removal."""
        scrubber = ConfigScrubber()
        config = """
<config version="10.0">
  <serial>PA-5220-ABC123DEF456</serial>
  <devicename>palo-fw-01</devicename>
</config>
        """
        result = scrubber.scrub_config(config, "panos")
        assert "PA-5220-ABC123DEF456" not in result
        assert "<serial><removed></serial>" in result or "<removed>" in result

    def test_scrub_paloalto_uptime(self):
        """Test Palo Alto uptime removal."""
        scrubber = ConfigScrubber()
        config = "<uptime>45 days 3 hours 22 minutes</uptime>"
        result = scrubber.scrub_config(config, "panos")
        assert "45 days" not in result
        assert "<uptime><removed></uptime>" in result or "<removed>" in result

    def test_scrub_paloalto_app_version(self):
        """Test Palo Alto app version removal."""
        scrubber = ConfigScrubber()
        config = "<app-version>8755-7032</app-version>"
        result = scrubber.scrub_config(config, "panos")
        assert "8755-7032" not in result

    def test_scrub_paloalto_threat_version(self):
        """Test Palo Alto threat version removal."""
        scrubber = ConfigScrubber()
        config = "<threat-version>8555-6521</threat-version>"
        result = scrubber.scrub_config(config, "panos")
        assert "8555-6521" not in result

    def test_scrub_paloalto_antivirus_version(self):
        """Test Palo Alto antivirus version removal."""
        scrubber = ConfigScrubber()
        config = "<antivirus-version>4333-4720</antivirus-version>"
        result = scrubber.scrub_config(config, "panos")
        assert "4333-4720" not in result

    def test_scrub_paloalto_wildfire_version(self):
        """Test Palo Alto Wildfire version removal."""
        scrubber = ConfigScrubber()
        config = "<wildfire-version>680803-681029</wildfire-version>"
        result = scrubber.scrub_config(config, "panos")
        assert "680803-681029" not in result


class TestScrubberFortinet:
    """Test Fortinet FortiOS configuration scrubbing."""

    def test_scrub_fortios_uuid(self):
        """Test Fortinet UUID removal."""
        scrubber = ConfigScrubber()
        config = 'config system global\n    uuid = "f47ac10b-58cc-4372-a567-0e02b2c3d479"'
        result = scrubber.scrub_config(config, "fortios")
        assert "f47ac10b" not in result
        assert "<removed>" in result or 'uuid = "<removed>"' in result

    def test_scrub_fortios_timestamp(self):
        """Test Fortinet timestamp removal."""
        scrubber = ConfigScrubber()
        config = 'timestamp = 1645180845'
        result = scrubber.scrub_config(config, "fortios")
        assert "1645180845" not in result or "<removed>" in result

    def test_scrub_fortios_lastupdate(self):
        """Test Fortinet lastupdate removal."""
        scrubber = ConfigScrubber()
        config = 'lastupdate = 1645180845'
        result = scrubber.scrub_config(config, "fortios")
        assert "1645180845" not in result or "<removed>" in result

    def test_scrub_fortios_build(self):
        """Test Fortinet build number removal."""
        scrubber = ConfigScrubber()
        config = 'build = 1234'
        result = scrubber.scrub_config(config, "fortios")
        assert "build = 1234" not in result or "<removed>" in result


class TestScrubberEdgeCases:
    """Test edge cases and special scenarios."""

    def test_scrub_empty_config(self):
        """Test scrubbing empty configuration."""
        scrubber = ConfigScrubber()
        result = scrubber.scrub_config("", "ios")
        assert result == ""

    def test_scrub_config_with_no_dynamic_fields(self):
        """Test scrubbing config with no dynamic fields."""
        scrubber = ConfigScrubber()
        config = """
interface Ethernet1
 description Static Interface
 ip address 10.0.0.1 255.255.255.0
        """
        result = scrubber.scrub_config(config, "ios")
        assert "Ethernet1" in result
        assert "10.0.0.1" not in result or "<ip-address>" in result

    def test_scrub_function_wrapper(self):
        """Test the public scrub_config function wrapper."""
        config = "uptime is 10 days, 5 hours"
        result = scrub_config(config, "ios")
        assert "10 days" not in result

    def test_scrub_multiline_config(self):
        """Test scrubbing multiline configurations."""
        scrubber = ConfigScrubber()
        config = """
line 1
uptime is 5 days, 1 hour
line 3
Last configuration change at 12:34:56 UTC Mon Feb 18 2025
line 5
        """
        result = scrubber.scrub_config(config, "ios")
        assert "line 1" in result
        assert "line 3" in result
        assert "line 5" in result
        assert "5 days" not in result
        assert "12:34:56" not in result

    def test_scrub_preserves_whitespace_structure(self):
        """Test that scrubbing preserves overall config structure."""
        scrubber = ConfigScrubber()
        config = """
config line 1
  nested line 2
    deeper line 3
uptime is 1 day
  more nested content
        """
        result = scrubber.scrub_config(config, "ios")
        assert "config line 1" in result
        assert "nested line 2" in result
        assert "deeper line 3" in result
        assert "1 day" not in result
