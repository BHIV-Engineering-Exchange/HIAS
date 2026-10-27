"""
Unit tests for app/adapters/cosec.py — COSECAdapter parser logic.
"""
import pytest
from app.adapters.cosec import COSECAdapter
from app.schemas import Method


@pytest.fixture
def adapter():
    return COSECAdapter("http://localhost:8080", "admin", "password")


class TestParseXmlEvents:
    def test_parse_valid_xml_events(self, adapter):
        xml_data = """
        <events>
            <event index="105" userid="12" timestamp="2023-10-27 12:00:00" type="face" />
            <event index="106" userid="101" timestamp="2023-10-27 12:05:00" type="rfid" />
        </events>
        """
        events = adapter._parse_events(xml_data)
        assert len(events) == 2
        assert events[0]["index"] == 105
        assert events[0]["device_user_id"] == "12"
        assert events[0]["method"] == Method.FACE
        assert events[1]["index"] == 106
        assert events[1]["method"] == Method.RFID

    def test_parse_malformed_xml_returns_empty(self, adapter):
        malformed = "<events><event index='101' userid='12'"
        events = adapter._parse_events(malformed)
        assert events == []

    def test_parse_empty_xml_events_tag(self, adapter):
        xml_data = "<events></events>"
        events = adapter._parse_events(xml_data)
        assert events == []

    def test_parse_partial_xml_missing_index_defaults_zero(self, adapter):
        xml_data = """
        <events>
            <event userid="12" timestamp="2023-10-27 12:00:00" type="rfid" />
        </events>
        """
        events = adapter._parse_events(xml_data)
        assert len(events) == 1
        assert events[0]["index"] == 0


class TestParseCsvEvents:
    def test_parse_valid_csv(self, adapter):
        csv_data = "101,12,2023-10-27 10:00:00,face\n102,15,2023-10-27 10:01:00,rfid"
        events = adapter._parse_events(csv_data)
        assert len(events) == 2
        assert events[0]["index"] == 101
        assert events[0]["device_user_id"] == "12"
        assert events[1]["index"] == 102

    def test_parse_csv_short_line_skipped(self, adapter):
        csv_data = "101,12\n102,15,2023-10-27 10:01:00,rfid"
        events = adapter._parse_events(csv_data)
        assert len(events) == 1
        assert events[0]["index"] == 102

    def test_parse_empty_string_returns_empty(self, adapter):
        events = adapter._parse_events("")
        assert events == []


class TestMethodMapping:
    def test_face_maps_to_face(self, adapter):
        assert adapter._map_method("face") == Method.FACE

    def test_rfid_maps_to_rfid(self, adapter):
        assert adapter._map_method("rfid") == Method.RFID

    def test_finger_falls_back_to_face(self, adapter):
        assert adapter._map_method("finger") == Method.FACE

    def test_unknown_type_defaults_to_rfid(self, adapter):
        assert adapter._map_method("unknown_biometric") == Method.RFID

    def test_case_insensitive_mapping(self, adapter):
        assert adapter._map_method("FACE") == Method.FACE
        assert adapter._map_method("RFID") == Method.RFID
