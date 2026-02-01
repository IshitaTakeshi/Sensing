"""Tests for NMEA checksum validation."""

from sensing import validate_checksum

GGA_VALID = "$GNGGA,123519.00,4807.038,N,01131.000,E,1,08,0.9,545.4,M,47.0,M,,*7F"
VTG_VALID = "$GNVTG,054.7,T,034.4,M,005.5,N,010.2,K,A*3B"


class TestValidateChecksum:
    """Tests for validate_checksum function."""

    def test_valid_gga_checksum(self):
        assert validate_checksum(GGA_VALID) is True

    def test_valid_checksum_with_newline(self):
        assert validate_checksum(GGA_VALID + "\r\n") is True

    def test_invalid_checksum(self):
        sentence = GGA_VALID[:-2] + "FF"
        assert validate_checksum(sentence) is False

    def test_missing_dollar_sign(self):
        assert validate_checksum(GGA_VALID[1:]) is False

    def test_missing_asterisk(self):
        sentence = GGA_VALID.replace("*", "")
        assert validate_checksum(sentence) is False

    def test_empty_string(self):
        assert validate_checksum("") is False

    def test_truncated_checksum(self):
        assert validate_checksum(GGA_VALID[:-1]) is False

    def test_valid_vtg_checksum(self):
        assert validate_checksum(VTG_VALID) is True
