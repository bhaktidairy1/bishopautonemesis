import socket
import threading
import time
import binascii
import requests
import tkinter as tk
from tkinter import ttk
from urllib.parse import urlparse
import traceback

HOST = "202.239.51.41"
PORT = 30001

# === STATE MANAGEMENT ===
class GameState:
    def __init__(self):
        self.stop_event = threading.Event()
        self.monsters = {}         
        self.target_uid = None     
        self.mode = "STANDBY"      
        self.last_map_coords = "82005a00" 
        self.waiting_for_hit = threading.Event()
        self.char_id_hex = ""
        self.damage_log = []
        self.paused = False

state = GameState()

# === LOGIN TOKEN HANDLING ===
session = requests.Session()
mageurl = "https://gae4php82-real.an.r.appspot.com/_ah/login?continue=https://gae4php82-real.an.r.appspot.com/authcreate&auth=g.a0008AjsE7nmtOE_FRrLzq3c0eCenIrHPLtvizyyNSyUpEC01rs3xOPaAL3b6yqU6aCo6AzWVQACgYKAesSARESFQHGX2MivSa5uCui6fUjbNajHhfgERoVAUF8yKoQVfPkaFGTvdLOGFA-XYpY0076"

session.get(mageurl, allow_redirects=True)
base = f"{urlparse(mageurl).scheme}://{urlparse(mageurl).netloc}"
resp_login_token = session.get(f"{base}/authcreate")
login_token = resp_login_token.text.strip()
LOGIN_TOKEN_HEX = login_token.encode().hex()
print("[+] Token:", LOGIN_TOKEN_HEX)

# === PACKET HELPERS ===

def hex_recv(sock, expect_len=4096, label=None) -> bytes:
    data = sock.recv(expect_len)
    if not data:
        raise ConnectionError("Server closed connection")
    h = binascii.hexlify(data).decode()
    if label:
        print(f"← {label} ({len(data)} bytes): {h}")
    else:
        print(f"← Received ({len(data)} bytes): {h}")
    return data

def hex_send(sock, hexstr: str, label=None):
    # Clean spaces so manual typing is easier
    hexstr = hexstr.replace(" ", "")
    raw = binascii.unhexlify(hexstr)
    sock.sendall(raw)
    if label:
        print(f"→ {label}: {hexstr}")
    else:
        print(f"→ Sent: {hexstr}")

# === CORE THREADS ===

# === CORE THREADS ===

def coordinate_sender(sock):
    while not state.stop_event.is_set():
        if state.paused:
            time.sleep(0.5)
            continue
        try:
            # state.last_map_coords is now "3d006f00"
            current_pos = state.last_map_coords
            
            # If targeting a monster, we apply the same 4-char rule
            if state.target_uid and state.target_uid in state.monsters:
                m = state.monsters[state.target_uid]
                # Ensure each coord is 4 chars (2 bytes)
                current_pos = m['x'].zfill(2) + "00" + m['y'].zfill(2) + "00"
            
            # Sends exactly 0006 0101 + 4 bytes of coords
            hex_send(sock, "00060101" + current_pos)
        except: break
        time.sleep(1.0)
def combat_engine(sock):
    while not state.stop_event.is_set():
        if state.mode == "STANDBY":
            state.target_uid = None
            time.sleep(0.5)
            continue
        if state.target_uid and state.target_uid in state.monsters:
            attack_pkt = "000a0241" + state.target_uid + "00000001"
            state.waiting_for_hit.clear()
            hex_send(sock, attack_pkt)
            state.waiting_for_hit.wait(timeout=0.8)
            time.sleep(0.4) 
        elif state.mode == "AUTO":
            for uid, data in state.monsters.items():
                if data['id'] in [0, 1, 2, 8]:
                    state.target_uid = uid
                    break
            time.sleep(0.2)
        else:
            time.sleep(0.5)

def continuous_receiver(sock):
    buffer = b""
    print("[*] Receiver Thread: Online and Listening...")
    while not state.stop_event.is_set():
        try:
            # 1. Check if socket is still alive
            data = sock.recv(4096)
            if not data: 
                print("\n[!!!] SERVER DISCONNECTED: Received empty data. Socket closed by peer.")
                break
            
            buffer += data
            
            # 2. Process Buffer
            while len(buffer) >= 6:
                # Most Iruna packets have a 4-byte length header
                pkt_len = int.from_bytes(buffer[0:4], "big")
                opcode = int.from_bytes(buffer[4:6], "big")
                total_pkt_size = pkt_len + 4
                
                # Safety check: if server sends a junk length header
                if pkt_len > 10000 or pkt_len == 0:
                    print(f"[!] Warning: Suspect Packet Length {pkt_len}. Buffer Dump: {binascii.hexlify(buffer[:20])}")
                    buffer = buffer[1:] # Shift and try to find next header
                    continue

                if len(buffer) < total_pkt_size:
                    break # Wait for more data
                
                raw_packet = buffer[:total_pkt_size]
                opcode_hex = hex(opcode)
                payload = buffer[6:total_pkt_size]
                
                # --- LOG EVERYTHING ---
                print(f"← [RECV] {opcode_hex} | {binascii.hexlify(raw_packet).decode()}")

                # Auto-Sync Logic (Keep this)
                if opcode == 0xb503:
                    try:
                        raw_map = binascii.hexlify(payload[3:5]).decode()
                        raw_x = int.from_bytes(payload[7:9], "big")
                        raw_y = int.from_bytes(payload[11:13], "big")
                        shifted_x = format((raw_x << 8) & 0xFFFF, '04x')
                        shifted_y = format((raw_y << 8) & 0xFFFF, '04x')
                        state.last_map_coords = shifted_x + shifted_y
                        print(f"\n[!] AUTO-SYNC: Map {raw_map} | Coords {shifted_x}{shifted_y}")
                    except Exception as e:
                        print(f"[!] Sync Parse Error: {e}")

                # Monster Spawn Logic
                if opcode == 0x245:
                    uid = binascii.hexlify(payload[0:4]).decode()
                    m_id = int.from_bytes(payload[4:6], "big")
                    state.monsters[uid] = {
                        'id': m_id, 
                        'x': binascii.hexlify(payload[8:10]).decode(), 
                        'y': binascii.hexlify(payload[12:14]).decode()
                    }

                buffer = buffer[total_pkt_size:]

        except socket.timeout:
            continue # Normal if server is quiet
        except Exception as e:
            print(f"\n[CRITICAL] Receiver Thread Crashed!")
            print(traceback.format_exc())
            break
    
    print("[*] Receiver Thread: Offline.")
class App:
    def __init__(self, root, sock):
        self.root = root
        self.sock = sock
        self.root.title("IRUNA COMMANDER")
        
        # Mode Selection
        frame_mode = ttk.LabelFrame(root, text="System Mode")
        frame_mode.pack(padx=10, pady=5, fill="x")
        
        self.mode_var = tk.StringVar(value="STANDBY")
        ttk.Radiobutton(frame_mode, text="Standby", variable=self.mode_var, value="STANDBY", command=self.update_mode).pack(side="left", padx=5)
        ttk.Radiobutton(frame_mode, text="Auto-Colon", variable=self.mode_var, value="AUTO", command=self.update_mode).pack(side="left", padx=5)
        ttk.Radiobutton(frame_mode, text="Manual", variable=self.mode_var, value="MANUAL", command=self.update_mode).pack(side="left", padx=5)

        # --- PAUSE BUTTON ---
        self.pause_btn_text = tk.StringVar(value="PAUSE COORDS")
        self.pause_btn = ttk.Button(frame_mode, textvariable=self.pause_btn_text, command=self.toggle_pause)
        self.pause_btn.pack(side="right", padx=10)

        # Monster List
        frame_list = ttk.LabelFrame(root, text="Radar")
        frame_list.pack(padx=10, pady=5, fill="both", expand=True)
        self.monster_lb = tk.Listbox(frame_list, height=8)
        self.monster_lb.pack(side="left", fill="both", expand=True)
        self.monster_lb.bind('<<ListboxSelect>>', self.on_select_monster)

        # Custom Hex Injector
        frame_hex = ttk.LabelFrame(root, text="Custom Hex Injector")
        frame_hex.pack(padx=10, pady=5, fill="x")
        self.hex_entry = ttk.Entry(frame_hex)
        self.hex_entry.pack(side="left", padx=5, pady=5, fill="x", expand=True)
        ttk.Button(frame_hex, text="Send Hex", command=self.send_custom_hex).pack(side="right", padx=5)

        self.status = tk.StringVar(value="Status: Ready")
        ttk.Label(root, textvariable=self.status).pack(pady=5)

        self.refresh_ui()
    def toggle_pause(self):
        state.paused = not state.paused
        if state.paused:
            self.pause_btn_text.set("RESUME COORDS")
            self.status.set("Coords Paused - Safe to warp.")
        else:
            self.pause_btn_text.set("PAUSE COORDS")
            self.status.set("Coords Resumed.")
    def send_custom_hex(self):
        raw = self.hex_entry.get().strip()
        if not raw: return
        try:
            # Check for even length and valid hex chars
            if all(c in "0123456789abcdefABCDEF " for c in raw) and (len(raw.replace(" ","")) % 2 == 0):
                hex_send(self.sock, raw, "MANUAL INJECT")
                self.status.set(f"Sent: {raw[:10]}...")
                self.hex_entry.delete(0, tk.END)
            else:
                self.status.set("Error: Invalid Hex String")
        except Exception as e:
            self.status.set(f"Error: {e}")
    
    def update_mode(self):
        state.mode = self.mode_var.get()
        self.status.set(f"Status: Mode set to {state.mode}")

    def on_select_monster(self, event):
        if state.mode != "MANUAL": return
        selection = self.monster_lb.curselection()
        if selection:
            text = self.monster_lb.get(selection[0])
            uid = text.split("UID: ")[1].split(" ")[0]
            state.target_uid = uid

    def refresh_ui(self):
        self.monster_lb.delete(0, tk.END)
        for uid, data in list(state.monsters.items()):
            name = "Colon" if data['id'] <= 2 else f"Mob({data['id']})"
            active = " [TARGET]" if uid == state.target_uid else ""
            self.monster_lb.insert(tk.END, f"{name} | UID: {uid}{active}")
        self.root.after(1000, self.refresh_ui)

def main():
# ... [Run your socket connection/login logic here first] ...
    
    token_with_prefix = "0020" + LOGIN_TOKEN_HEX + "0000"

    # 1) Open TCP socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5.0)
    print(f"[+] Connecting to {HOST}:{PORT} …")
    s.connect((HOST, PORT))
    print("[+] Connected.\n")

    # 2) Send “0002fff3” (Init Packet)
    hex_send(s, "0002fff3", "Init Packet")
    #    → server replies the init header
    hex_recv(s, label="Init Header")

    # 3) Send dynamic‐length login: [length][FF02][0020<token>0000]
    raw_token = binascii.unhexlify(token_with_prefix)
    payload = b"\xFF\x02" + raw_token
    login_packet = len(payload).to_bytes(2, "big") + payload
    s.sendall(login_packet)
    print(f"→ Login Packet: {binascii.hexlify(login_packet).decode()}")

    #  → server should reply first with “00000003ff0200”
    data = hex_recv(s, label="Login ACK")
    h = binascii.hexlify(data).decode()
    if not h.startswith("00000003ff0200"):
        print("[-] Unexpected login response:", h)
        s.close()
        return
    print("[+] Login OK.\n")

    #  → immediately after “00000003ff0200” comes the ff03 (+ char-info) packet
    try:
        s.settimeout(0.3)
        extra = hex_recv(s, label="ff03 + char info")
        hexed = binascii.hexlify(extra).decode()
        idx = hexed.find("ff030100000001")
        if idx != -1 and len(hexed) >= idx + 14 + 8:
            char_id_hex = hexed[idx + 14 : idx + 14 + 8]
            print(f"[+] Parsed char_id_hex: {char_id_hex}\n")
        else:
            print("[-] Couldn't locate char_id_hex in the ff03 packet.")
            s.close()
            return
    except socket.timeout:
        print("[-] Timeout waiting for ff03.")
        s.close()
        return
    finally:
        s.settimeout(5.0)

    # ─────────── From here on: replay the “correct” Character/World sequence ───────────
    def send_and_log(pkt_hex, label=None, delay=0.1):
        hex_send(s, pkt_hex, label=label)
        time.sleep(delay)

    # 4) Character Select
    send_and_log("0002f032", "Character Select")
    #    → server: “0000009df032…” (character info)
    hex_recv(s, label="Character Info")

    # 5) Enter World #1: “00060001” + <char_id_hex>
    send_and_log("00060001", "Enter World")
    send_and_log(char_id_hex, "Character ID")

    #    money
    #hex_recv_map_data(s)
    hex_recv(s, label="Character Info")


    # 6) Post‐Map: “000623f3” + <char_id_hex>
    send_and_log("000623f3", "Post-Map")
    send_and_log(char_id_hex, "Character ID Repeat")

    #   money again
    hex_recv(s, label="Character Info")

    # 7) Four movement‐handshake packets + “00026002”
    for step in ["00023300", "00023303", "00023300", "00023303"]:
        send_and_log(step, "Movement Step")
    hex_recv(s, label="Pre-Movement Sync")


    send_and_log("00026002", "Movement Step")
    #    → server: movement sync
    hex_recv(s, label="Movement Sync")

    # 8) Presence start: “001bb300” + 24 zeros
    send_and_log("001bb300", "Presence Start")
    send_and_log("00000000000000000000000000000000000000000000000000", "Zeroes")

    # 9) Begin Sync: “0002013a” then “000e0110000318940000320000001000”
    send_and_log("0002013a", "Map Location Begin")
    send_and_log("000e01100000012c0000470000001000", "Map Data")  #0000125c0000820000005a00 MAP OF ZIMOV #0000012c0000470000001000 for miscerene plains
    #    → server: ack for position
    hex_recv(s, label="Ack for Position")

    # 10) Resend Position: “0002013a”
    send_and_log("0002013a", "Resend Position")
    #    → server: extra state data
    hex_recv(s, label="Extra State Data")

    # 11) Bulk Action: “000f3002”
    send_and_log("000f3002", "Bulk Action")
    send_and_log("1100000000000000000000012c00023209", "Bulk Action Contd.")

    # 12) Trigger Motion: “00020160”
    send_and_log("0002016000028100000281100002830000028200", "Trigger Motion")
    #    → server: motion ack
    hex_recv(s, label="Motion Ack")

    # 13) Visuals Setup: “00038404”
    send_and_log("0003840400", "Visuals Setup")
    # there supposed to be a 00028100000281100002830000028200 in between here
    send_and_log("00025003", "World Ticks Start")
    send_and_log("001bb30000000000000000000000000000000000000000000000000000", "World Ticks")
    
    # 14) Presence Confirm: “00060202” + <char_id_hex>
    #send_and_log("00060202" + char_id_hex, "Presence Confirm")
    #    → server: presence ack
    #hex_recv(s, label="Presence Ack")

    # 15) World Tick: “00033006”
    #send_and_log("00033006", "World Tick")
    # 16) Trigger Something: “01000f300211000000020000000000031894”
    #send_and_log("01000f300211000000050000000000001554", "Trigger Something")
    #    → server: update
    hex_recv(s, label="Server Update")

    # 17) Char “idle + coords” right away:
    #     “00067110” + <char_id_hex> + coords packet
    #send_and_log("00067110" + char_id_hex + CURRENT_COORDS, "Char Idle + Coords")

    #send_and_log("0006a102" + "38e2edca", "Summon Pet")    #for each sin TODO
    #    → server: update
    #hex_recv(s, label="Summon Pet")

    print("\n[+] Game session established. Starting packet loop and GUI…\n")
    print("[+] Entering infinite cerbera Battle loop")
    

    print("\n[+] Battle loop & Threads active.")
    
    threading.Thread(target=coordinate_sender, args=(s,), daemon=True).start()
    threading.Thread(target=continuous_receiver, args=(s,), daemon=True).start()
    threading.Thread(target=combat_engine, args=(s,), daemon=True).start()

    root = tk.Tk()
    app = App(root, s) # Pass s here
    root.mainloop()

if __name__ == "__main__":
    main()