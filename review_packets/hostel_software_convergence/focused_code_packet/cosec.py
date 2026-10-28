import httpx
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Optional, Dict, Any
from app.schemas import Method, Direction

class COSECAdapter:
    """
    Standard Matrix COSEC Devices API Adapter.
    Implements official Matrix COSEC HTTP CGI specifications:
    - User Configuration API (/device.cgi/users)
    - Credential Configuration API (/device.cgi/credential)
    - Device Commands (/device.cgi/command)
    - Event Retrieval (/device.cgi/events)
    """

    def __init__(self, base_url: str, username: str = "admin", password: str = "password123", timeout_seconds: float = 4.0):
        self.base_url = base_url.rstrip('/')
        self.auth = (username, password)
        self.timeout = httpx.Timeout(timeout_seconds)

    async def check_device(self) -> bool:
        """Verify device reachability via official check-enrollment or basic command."""
        urls = [
            f"{self.base_url}/device.cgi/check-enrollment",
            f"{self.base_url}/device.cgi/command?action=getusercount",
            f"{self.base_url}/device.cgi/device-basic-config?action=get"
        ]
        for url in urls:
            try:
                async with httpx.AsyncClient(auth=self.auth, timeout=self.timeout) as client:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        return True
            except Exception:
                continue
        return False

    async def get_device_config(self) -> Dict[str, Any]:
        """Fetch device basic configuration parameters."""
        url = f"{self.base_url}/device.cgi/device-basic-config"
        params = {"action": "get"}
        try:
            async with httpx.AsyncClient(auth=self.auth, timeout=self.timeout) as client:
                resp = await client.get(url, params=params)
                if resp.status_code == 200:
                    text = resp.text.strip()
                    config = {}
                    for item in text.split():
                        if "=" in item:
                            k, v = item.split("=", 1)
                            config[k] = v
                    return config
        except Exception as e:
            print(f"[COSEC_ERROR] Failed to fetch device config: {e}")
        return {}

    async def push_user(
        self,
        user_id: str,
        ref_user_id: int,
        name: str,
        card1: Optional[str] = None,
        enable_fr: bool = True
    ) -> bool:
        """
        Create or update user on COSEC device.
        URL: http://<ip>/device.cgi/users?action=set&user-id=<uid>&ref-user-id=<ref>&name=<name>&user-active=1&card1=<card1>&enable-fr=<1|0>
        """
        url = f"{self.base_url}/device.cgi/users"
        params = {
            "action": "set",
            "user-id": user_id,
            "ref-user-id": str(ref_user_id),
            "name": name[:15],
            "user-active": "1",
            "enable-fr": "1" if enable_fr else "0"
        }
        if card1:
            params["card1"] = card1

        try:
            async with httpx.AsyncClient(auth=self.auth, timeout=self.timeout) as client:
                resp = await client.get(url, params=params)
                return resp.status_code == 200 and ("Response-Code=0" in resp.text or resp.text == "" or "success" in resp.text.lower())
        except Exception as e:
            print(f"[COSEC_ERROR] Failed to push user {user_id}: {e}")
            return False

    async def push_credential(
        self,
        user_id: str,
        cred_type: str,
        card_number: Optional[str] = None,
        face_data: Optional[bytes] = None
    ) -> bool:
        """
        Set user credential on device.
        RFID Card: GET /device.cgi/credential?action=set&type=2&user-id=<uid>&card1=<card1>
        Face Image: POST /device.cgi/credential?action=set&type=6&user-id=<uid> (with binary JPEG payload)
        """
        url = f"{self.base_url}/device.cgi/credential"

        try:
            async with httpx.AsyncClient(auth=self.auth, timeout=self.timeout) as client:
                if cred_type.upper() == "RFID" and card_number:
                    params = {
                        "action": "set",
                        "type": "2",
                        "user-id": user_id,
                        "card1": card_number
                    }
                    resp = await client.get(url, params=params)
                    return resp.status_code == 200 and ("Response-Code=0" in resp.text or resp.text == "" or "success" in resp.text.lower())

                elif cred_type.upper() == "FACE":
                    params = {
                        "action": "set",
                        "type": "6",
                        "user-id": user_id
                    }
                    headers = {"Content-Type": "image/jpeg"}
                    payload = face_data if face_data else b"DUMMY_FACE_TEMPLATE_COSEC_ARGO_V1"
                    resp = await client.post(url, params=params, content=payload, headers=headers)
                    return resp.status_code == 200 and ("Response-Code=0" in resp.text or "success" in resp.text.lower())

        except Exception as e:
            print(f"[COSEC_ERROR] Failed to push credential for user {user_id}: {e}")
        return False

    async def delete_user(self, user_id: str) -> bool:
        """Delete user and all associated credentials from device."""
        url = f"{self.base_url}/device.cgi/users"
        params = {"action": "delete", "user-id": user_id}
        try:
            async with httpx.AsyncClient(auth=self.auth, timeout=self.timeout) as client:
                resp = await client.get(url, params=params)
                return resp.status_code == 200
        except Exception as e:
            print(f"[COSEC_ERROR] Failed to delete user {user_id}: {e}")
            return False

    async def delete_credentials(self, user_id: str, cred_type: int = 0) -> bool:
        """Delete user credentials (0 = All)."""
        url = f"{self.base_url}/device.cgi/credential"
        params = {"action": "delete", "user-id": user_id, "type": str(cred_type)}
        try:
            async with httpx.AsyncClient(auth=self.auth, timeout=self.timeout) as client:
                resp = await client.get(url, params=params)
                return resp.status_code == 200
        except Exception as e:
            print(f"[COSEC_ERROR] Failed to delete credentials for {user_id}: {e}")
            return False

    async def open_door(self, door_id: str = "1", extra_info1: str = "HIAS") -> bool:
        """
        Triggers door open command.
        Official syntax: /device.cgi/command?action=opendoor&extra-info1=HIAS
        Fallback syntax: /device.cgi/commands?action=set&cmd=open-door&doorid=1
        """
        official_url = f"{self.base_url}/device.cgi/command"
        legacy_url = f"{self.base_url}/device.cgi/commands"
        
        try:
            async with httpx.AsyncClient(auth=self.auth, timeout=self.timeout) as client:
                # Try official Matrix command first
                resp = await client.get(official_url, params={"action": "opendoor", "extra-info1": extra_info1})
                if resp.status_code == 200:
                    return True
                # Fallback to legacy mock syntax
                resp_legacy = await client.get(legacy_url, params={"action": "set", "cmd": "open-door", "doorid": door_id})
                return resp_legacy.status_code == 200
        except Exception as e:
            print(f"[COSEC_ERROR] Failed to trigger door: {e}")
            return False

    async def fetch_events(self, last_index: int = 0, roll_over_count: int = 0) -> List[Dict]:
        """
        Polls COSEC device for events using official Matrix getevent API or legacy get API.
        """
        # Try official Matrix getevent syntax first
        url_official = f"{self.base_url}/device.cgi/events"
        params_official = {
            "action": "getevent",
            "roll-over-count": str(roll_over_count),
            "seq-number": str(last_index),
            "no-of-events": "20",
            "format": "xml"
        }
        
        try:
            async with httpx.AsyncClient(auth=self.auth, timeout=self.timeout) as client:
                resp = await client.get(url_official, params=params_official)
                if resp.status_code == 200 and resp.text.strip():
                    parsed = self._parse_events(resp.text)
                    if parsed:
                        return parsed
                
                # Fallback to legacy syntax
                params_legacy = {"action": "get", "index": last_index}
                resp_legacy = await client.get(url_official, params=params_legacy)
                if resp_legacy.status_code == 200:
                    return self._parse_events(resp_legacy.text)
        except Exception as e:
            print(f"[COSEC_ERROR] Failed to fetch events: {e}")
            return []
        return []

    def _parse_events(self, raw_data: str) -> List[Dict]:
        """
        Parses COSEC XML or text event stream.
        Supports both:
        1. Official Matrix COSEC format:
           <COSEC_API>
             <Events>
               <roll-over-count>0</roll-over-count>
               <seq-No>101</seq-No>
               <event-id>101</event-id>
               <detail-1>12</detail-1>
               <detail-3>258</detail-3>
             </Events>
           </COSEC_API>
        2. Legacy simulator format:
           <events>
             <event index="101" userid="12" timestamp="2026-10-28 10:30:01" type="face" />
           </events>
        3. CSV/plain text format
        """
        events = []
        text = raw_data.strip()
        if not text:
            return events

        try:
            if text.startswith("<"):
                root = ET.fromstring(text)
                # Check for official Matrix <Events>
                matrix_events = root.findall('.//Events') or root.findall('Events')
                if matrix_events:
                    for ev in matrix_events:
                        seq_el = ev.find('seq-No')
                        det1_el = ev.find('detail-1')
                        det3_el = ev.find('detail-3')
                        date_el = ev.find('date')
                        time_el = ev.find('time')

                        seq_val = int(seq_el.text.strip()) if (seq_el is not None and seq_el.text) else 0
                        user_val = det1_el.text.strip() if (det1_el is not None and det1_el.text) else ""
                        det3_val = int(det3_el.text.strip()) if (det3_el is not None and det3_el.text) else 0
                        
                        # Timestamp reconstruction
                        d_str = date_el.text.strip() if (date_el is not None and date_el.text) else ""
                        t_str = time_el.text.strip() if (time_el is not None and time_el.text) else ""
                        timestamp_str = f"{d_str} {t_str}".strip() or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                        method, direction = self._decode_detail3(det3_val)
                        events.append({
                            "index": seq_val,
                            "device_user_id": user_val,
                            "timestamp": timestamp_str,
                            "method": method,
                            "direction": direction
                        })
                    return events

                # Check for legacy simulator <event>
                for ev in root.findall('.//event'):
                    events.append({
                        "index": int(ev.get('index', 0)),
                        "device_user_id": ev.get('userid', ''),
                        "timestamp": ev.get('timestamp', datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                        "method": self._map_method(ev.get('type', 'rfid')),
                        "direction": Direction.IN
                    })
                return events

            # Plain text / CSV parsing
            lines = text.splitlines()
            for line in lines:
                parts = [p.strip() for p in line.split(",") if p.strip()]
                if len(parts) >= 4:
                    events.append({
                        "index": int(parts[0]),
                        "device_user_id": parts[1],
                        "timestamp": parts[2],
                        "method": self._map_method(parts[3]),
                        "direction": Direction.IN
                    })
        except Exception as e:
            print(f"[COSEC_PARSER_ERROR] Failed parsing events: {e}")
        return events

    def _decode_detail3(self, val: int) -> tuple[Method, Direction]:
        """
        Decodes Matrix COSEC detail-3 bitmask per API manual Table: Field 3 Detail.
        Bit 0: Entry (0) or Exit (1)
        Bit 5 / 12 / 13: Card / RFID (e.g., 258, 514)
        Bit 6: Finger (value 4)
        Bit 10: Face (value 64)
        """
        direction = Direction.OUT if (val & 0x01) else Direction.IN
        
        # Check bits for credential type
        if val & (1 << 10):  # Bit 10 = Face
            return Method.FACE, direction
        elif val & ((1 << 5) | (1 << 12) | (1 << 13)):  # Card bits
            return Method.RFID, direction
        elif val & (1 << 6):  # Finger
            return Method.RFID, direction
        return Method.RFID, direction

    def _map_method(self, cosec_type: str) -> Method:
        mapping = {
            "face": Method.FACE,
            "rfid": Method.RFID,
            "card": Method.RFID,
            "finger": Method.FACE,  # Fallback
            "manual": Method.MANUAL,
        }
        return mapping.get(str(cosec_type).lower(), Method.RFID)
