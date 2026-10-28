# 07_COSEC_RFID_FACE_INTEGRATION.md — Matrix COSEC Protocol Reference

**Checkpoint:** Stage 2 & 5 — COSEC Device API Verification & RFID/Face Path  
**Lead Owner:** Pritesh Patra (RFID / COSEC / Access Flow)  
**Reference Document:** *Matrix COSEC Devices API User Guide (Version 26, Matrix Comsec Pvt. Ltd.)*  
**Status:** **VERIFIED SPECIFICATION & IMPLEMENTED**

---

## 1. Matrix COSEC Architecture & Model Support

HIAS communicates with Matrix COSEC physical hardware via standard HTTP CGI commands over TCP port 80.
Supported Matrix terminal devices deployed across campus gates:
- **Matrix COSEC ARGO FACE / ARGO FACE200T** (Primary Biometric Face + RFID Gates)
- **Matrix COSEC PATH CONTROLLER** (Auxiliary RFID Gates)
- **Matrix COSEC DIRECT DOOR V3 / V4** (Perimeter Turnstiles)

### Protocol Conventions
- **Base Request Syntax:**
  `http://<deviceIP:deviceport>/device.cgi/<request-type>?action=<action>&<argument>=<value>...`
- **Authentication:** HTTP Basic Authentication (`admin` / device password).
- **Format:** Supports plain text key-value pairs or structured XML responses.
- **Line Endings:** `<CR><LF>` per HTTP standard.

---

## 2. API Endpoint Implementations

### 2.1 User Configuration API (`/device.cgi/users`)
Configures or retrieves user identity parameters on the terminal:
- **Set User Command:**
  ```http
  GET /device.cgi/users?action=set&user-id=S2501&ref-user-id=1007&name=Pritesh+Patra&user-active=1&card1=4455667788&enable-fr=1 HTTP/1.1
  Host: 192.168.1.100
  Authorization: Basic YWRtaW46cGFzc3dvcmQxMjM=
  ```
  *Parameters:*
  - `user-id`: Alphanumeric canonical ID (max 15 chars).
  - `ref-user-id`: Numeric reference ID (1 to 50,000, 8 digits max) used for fast event indexing.
  - `name`: ASCII string (max 15 chars).
  - `card1`: 64-bit unsigned integer represented as string (max 18446744073709551615).
  - `enable-fr`: `1` to enable Face Recognition, `0` to disable.
- **Expected Success Response:**
  ```http
  HTTP/1.1 200 OK
  Content-Type: text/plain

  Response-Code=0
  ```

### 2.2 Credential Configuration API (`/device.cgi/credential`)
- **Set RFID Card Credential:**
  ```http
  GET /device.cgi/credential?action=set&type=2&user-id=S2501&card1=4455667788 HTTP/1.1
  Host: 192.168.1.100
  ```
  - `type=2`: Specifies RFID Card credential.
- **Set Face Image Credential (ARGO FACE):**
  ```http
  POST /device.cgi/credential?action=set&type=6&user-id=S2501 HTTP/1.1
  Host: 192.168.1.100
  Content-Type: image/jpeg
  Content-Length: 42150

  <Binary JPEG Image Payload (Max 200 KB)>
  ```
  - `type=6`: Specifies Face Image. Terminal extracts 3D face template locally.
- **Delete User Credentials:**
  ```http
  GET /device.cgi/credential?action=delete&user-id=S2501&type=0 HTTP/1.1
  ```
  - `type=0`: Deletes all credentials (cards, face, PIN) for the user.

### 2.3 Gate Control Commands (`/device.cgi/command`)
- **Open Door Pulse:**
  ```http
  GET /device.cgi/command?action=opendoor&extra-info1=HIAS HTTP/1.1
  Host: 192.168.1.100
  ```
  - Energizes door lock relay for configured pulse time (default 1.5–3.0 seconds).
- **Get Event Count:**
  ```http
  GET /device.cgi/command?action=geteventcount&format=xml HTTP/1.1
  ```
  - Returns current rollover count and sequence number stored on the device.

---

## 3. Event Ingestion & Bitmask Decoding

Events are retrieved from the terminal via:
```http
GET /device.cgi/events?action=getevent&roll-over-count=0&seq-number=101&no-of-events=20&format=xml HTTP/1.1
```

### Official XML Response Format
```xml
<COSEC_API>
  <Events>
    <roll-over-count>0</roll-over-count>
    <seq-No>102</seq-No>
    <date>28/10/2026</date>
    <time>10:35:10</time>
    <event-id>101</event-id>
    <detail-1>1007</detail-1>
    <detail-3>258</detail-3>
    <detail-4>0</detail-4>
    <detail-5>0</detail-5>
  </Events>
</COSEC_API>
```

### Field 3 Detail (User Events) Bitmask Table
The Matrix COSEC protocol packs credential method and direction into a 16-bit integer in `detail-3`:

| Bit | Field Name | Significance | Example Value |
|:---:|------------|--------------|:-------------:|
| **Bit 0** | Entry / Exit | `0 = Entry (IN)`, `1 = Exit (OUT)` | 0 (IN), 1 (OUT) |
| **Bit 4** | PIN | User entered PIN | 1 |
| **Bit 5** | Card | Card credential presented | 2 |
| **Bit 6** | Finger | Fingerprint scanned | 4 |
| **Bit 10** | Face | Face recognition match | 64 |
| **Bit 12** | Card 1 | Primary Card credential | 258 (Bit 5 + Bit 12) |
| **Bit 13** | Card 2 | Secondary Card credential | 514 (Bit 5 + Bit 13) |

### Python Decoder (`COSECAdapter._decode_detail3`)
```python
def _decode_detail3(self, val: int) -> tuple[Method, Direction]:
    direction = Direction.OUT if (val & 0x01) else Direction.IN
    if val & (1 << 10):  # Bit 10 = Face
        return Method.FACE, direction
    elif val & ((1 << 5) | (1 << 12) | (1 << 13)):  # Card bits
        return Method.RFID, direction
    elif val & (1 << 6):  # Finger
        return Method.RFID, direction
    return Method.RFID, direction
```
*Validation:* Value `258` decodes to `Method.RFID` and `Direction.IN`; value `64` decodes to `Method.FACE` and `Direction.IN`. Both verified in `test_parser.py`.

---

## 4. Matrix COSEC Response Code Table

| Code | Description | HIAS Engine Handling |
|:---:|-------------|----------------------|
| **0** | Successful | Sync marked `SYNCED`; gate unlocked. |
| **1** | Invalid Login Credentials | Logged as authentication fault; check COSEC admin password. |
| **4** | Maximum users configured | Triggers alarm: Hardware capacity exceeded (50,000 max). |
| **8** | Card ID exists | Catches duplicate card assignment; sync aborted. |
| **9** | Face template already exists | Handled gracefully without error. |
| **10** | No Record Found | Logged as empty event poll. |
| **13** | User ID not found | Re-queues `push_user()` before credential push. |
| **16** | Device Busy | Sync worker retries with exponential backoff. |
| **36** | Face Not Detected | Enrollment photo failed face detection; user re-prompted. |
| **37** | User Conflict | Face image matches an already-enrolled resident. |
