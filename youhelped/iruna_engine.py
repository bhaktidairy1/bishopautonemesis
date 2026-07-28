import socket, time, binascii, requests
from urllib.parse import urlparse

class IrunaEngine:
    def __init__(self, state):
        self.state = state
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.session = requests.Session() # Crucial for Cookie persistence
        self.host = "202.239.51.41"
        self.port = 30001
        self.char_id = ""

    def get_token(self, mage_url):
        print("[*] Accessing Login Portal...")
        # Get cookies from the login redirect
        self.session.get(mage_url, allow_redirects=True)
        base = f"{urlparse(mage_url).scheme}://{urlparse(mage_url).netloc}"
        # Fetch token using the established session cookies
        resp = self.session.get(f"{base}/authcreate")
        token = resp.text.strip()
        print(f"[+] Token Obtained: {token[:10]}...")
        return token.encode().hex()

    def send_hex(self, hex_str, label=None):
        raw = binascii.unhexlify(hex_str.replace(" ", ""))
        self.sock.sendall(raw)
        if label: print(f"→ {label}: {hex_str}")

    def recv_hex(self, label=None, size=4096):
        try:
            data = self.sock.recv(size)
            if not data: return ""
            h = binascii.hexlify(data).decode()
            if label: print(f"← {label}: {h[:80]}...")
            return h
        except: return ""

    def full_login_handshake(self, mage_url):
        """The 17-step character selection & world entry sequence."""
        token_hex = self.get_token(mage_url)
        self.sock.settimeout(5.0)
        self.sock.connect((self.host, self.port))

        # 1-3. Login Init
        self.send_hex("0002fff3", "Init Packet")
        self.recv_hex("Init Header")
        
        login_token_pkt = "0020" + token_hex + "0000"
        payload = b"\xFF\x02" + binascii.unhexlify(login_token_pkt)
        self.sock.sendall(len(payload).to_bytes(2, "big") + payload)
        
        ack = self.recv_hex("Login ACK")
        if not ack.startswith("00000003ff0200"):
            print("[-] Login Refused by Server")
            return False

        # 4. FF03 Packet - Character ID Extraction
        ff03_data = self.recv_hex("Char Info Cluster")
        idx = ff03_data.find("ff030100000001")
        if idx != -1:
            self.char_id = ff03_data[idx + 14 : idx + 22]
            print(f"[+] Char ID Parsed: {self.char_id}")
            self.state.char_id_hex = self.char_id
        
        # 4-6. Character & World Setup
        self.send_hex("0002f032", "Char Select"); self.recv_hex()
        self.send_hex("00060001" + self.char_id, "Enter World"); self.recv_hex()
        self.send_hex("000623f3" + self.char_id, "Post-Map Check"); self.recv_hex()

        # 7. Movement Handshake (The 4 Steps)
        for step in ["00023300", "00023303", "00023300", "00023303"]:
            self.send_hex(step, "Move Sync")
        self.recv_hex("Pre-Move Sync")
        self.send_hex("00026002", "Movement Ready"); self.recv_hex("Move Sync ACK")

        # 8-11. Presence & Map Loading (Step 9/10)
        self.send_hex("001bb300" + ("0" * 48), "Presence Start")
        self.send_hex("0002013a", "Map Sync Begin")
        # Default entry to Miscern Plains (Map 300)
        self.send_hex("000e01100000012c0000470000001000", "Load Miscern Plains")
        self.recv_hex("Position ACK")
        self.send_hex("0002013a", "Resend Position"); self.recv_hex()

        # 11-13. Bulk Action & Motion
        self.send_hex("000f3002", "Bulk Header")
        self.send_hex("11000000000000000000003e1c00023209", "Bulk Data")
        self.send_hex("0002016000028100000281100002830000028200", "Motion Trigger")
        self.recv_hex("Motion ACK")

        # 14-17. Visuals & Final Sync
        self.send_hex("0003840400", "Visuals Setup")
        self.send_hex("00025003", "World Ticks Start")
        self.send_hex("001bb300" + ("0" * 54), "World Persistence")
        self.recv_hex("Final Server Update")
        
        print("[!] Engine Logic Established. Bot is Live.")
        return True

    def warp_handshake(self, target_map, portal_id, x, y):
        """The 3002 Sandwich Warp (Universal Handshake)."""
        print(f"[*] Warping to Map {target_map} via Portal {portal_id}")
        # Departure
        self.send_hex(f"000f300211000000{portal_id.zfill(2)}000000000000{self.state.current_map_hex}", "3002 EXIT")
        # Transition Load
        self.send_hex("0003300601", "3006 SYNC START")
        # The 110 Prediction (with correct 0000 padding)
        self.send_hex(f"000e01100000{target_map}0000{x}0000{y}00", "110 POSITION")
        # Arrival
        self.send_hex("0003300600", "3006 SYNC END")
        self.send_hex(f"000f30021100000000000000000000{target_map}", "3002 ENTRY")
        
        self.state.current_map_hex = target_map
        self.state.last_map_coords = f"{x}00{y}00"