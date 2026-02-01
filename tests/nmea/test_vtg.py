"""Tests for VTG sentence parsing."""

import pytest

from sensing import parse_vtg


class TestParseVTG:
    """Tests for parse_vtg function."""

    def test_valid_vtg_autonomous(self):
        sentence = "$GNVTG,054.7,T,034.4,M,005.5,N,010.2,K,A*3B"
        result = parse_vtg(sentence)
        assert result is not None
        assert result.track_true_deg == pytest.approx(54.7)
        assert result.speed_knots == pytest.approx(5.5)
        assert result.speed_kmh == pytest.approx(10.2)
        assert result.speed_mps == pytest.approx(10.2 / 3.6)
        assert result.mode == "A"
        assert result.valid is True

    def test_vtg_differential_mode(self):
        result = parse_vtg("$GNVTG,054.7,T,034.4,M,005.5,N,010.2,K,D*3E")
        assert result is not None and result.mode == "D" and result.valid

    def test_vtg_not_valid_mode(self):
        result = parse_vtg("$GNVTG,054.7,T,034.4,M,005.5,N,010.2,K,N*34")
        assert result is not None and result.mode == "N" and not result.valid

    def test_vtg_stationary_empty_track(self):
        result = parse_vtg("$GNVTG,,T,,M,0.0,N,0.0,K,A*3D")
        assert result is not None
        assert result.track_true_deg is None
        assert result.speed_knots == pytest.approx(0.0)
        assert result.speed_kmh == pytest.approx(0.0)
        assert result.speed_mps == pytest.approx(0.0)
        assert result.mode == "A" and result.valid

    def test_vtg_all_empty_fields(self):
        result = parse_vtg("$GNVTG,,T,,M,,N,,K,N*32")
        assert result is not None
        assert result.track_true_deg is None
        assert result.speed_knots is None
        assert result.speed_kmh is None
        assert result.speed_mps is None
        assert result.mode == "N" and not result.valid

    def test_vtg_no_mode_indicator(self):
        result = parse_vtg("$GNVTG,054.7,T,034.4,M,005.5,N,010.2,K*56")
        assert result is not None and result.mode is None and not result.valid

    def test_vtg_invalid_checksum(self):
        assert parse_vtg("$GNVTG,054.7,T,034.4,M,005.5,N,010.2,K,A*FF") is None

    def test_vtg_malformed_too_few_fields(self):
        assert parse_vtg("$GNVTG,054.7,T*12") is None

    def test_vtg_wrong_sentence_type(self):
        sentence = "$GNGGA,123519.00,4807.038,N,01131.000,E,1,08,0.9,545.4,M,47.0,M,,*7F"
        assert parse_vtg(sentence) is None

    def test_vtg_invalid_prefix(self):
        assert parse_vtg("$XXVTG,054.7,T,034.4,M,005.5,N,010.2,K,A*32") is None

    def test_vtg_multi_constellation_prefixes(self):
        prefixes = [("GP", "25"), ("GN", "3B"), ("GL", "39"),
                    ("GA", "34"), ("GB", "37"), ("GQ", "24")]
        for prefix, cs in prefixes:
            s = f"${prefix}VTG,054.7,T,034.4,M,005.5,N,010.2,K,A*{cs}"
            assert parse_vtg(s) is not None, f"Failed: {prefix}"

    def test_vtg_speed_mps_computed_correctly(self):
        result = parse_vtg("$GNVTG,000.0,T,000.0,M,000.0,N,036.0,K,A*38")
        assert result is not None
        assert result.speed_kmh == pytest.approx(36.0)
        assert result.speed_mps == pytest.approx(10.0)

    def test_vtg_speed_mps_none_when_kmh_empty(self):
        result = parse_vtg("$GNVTG,054.7,T,034.4,M,005.5,N,,K,A*16")
        assert result is not None and result.speed_mps is None

    def test_vtg_with_crlf(self):
        assert parse_vtg("$GNVTG,054.7,T,034.4,M,005.5,N,010.2,K,A*3B\r\n") is not None

    def test_zedf9p_vtg_moving(self):
        result = parse_vtg("$GNVTG,325.5,T,337.8,M,0.5,N,0.9,K,D*3A")
        assert result is not None and result.mode == "D"
