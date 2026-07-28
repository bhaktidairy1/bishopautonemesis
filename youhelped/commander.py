import tkinter as tk
from tkinter import ttk
import threading, time, binascii
from iruna_engine import IrunaEngine

class GameState:
    def __init__(self):
        self.stop_event = threading.Event()
        self.monsters = {}
        self.target_uid = None
        self.mode = "STANDBY"
        self.last_map_coords = "0000470000001000"
        self.current_map_hex = "012c" 
        self.char_id_hex = ""
        self.waiting_for_hit = threading.Event()

state = GameState()

# === BACKGROUND WORKERS ===

def continuous_receiver(engine):
    """The Global Opcode Logger."""
    buffer = b""
    while not state.stop_event.is_set():
        try:
            data = engine.sock.recv(4096)
            if not data: break
            buffer += data
            while len(buffer) >= 6:
                p_len = int.from_bytes(buffer[0:4], "big")
                opcode = int.from_bytes(buffer[4:6], "big")
                total = p_len + 4
                if len(buffer) < total: break
                
                raw = buffer[:total]
                payload = buffer[6:total]
                # Full hex log for every opcode
                print(f"← [RECV] {hex(opcode)} | {binascii.hexlify(raw).decode()}")

                if opcode == 0x245: # Monster Spawn
                    uid = binascii.hexlify(payload[0:4]).decode()
                    state.monsters[uid] = {
                        'id': int.from_bytes(payload[4:6], "big"),
                        'x': binascii.hexlify(payload[8:10]).decode() + "00",
                        'y': binascii.hexlify(payload[12:14]).decode() + "00"
                    }
                elif opcode == 0x244: # Entity Death
                    uid = binascii.hexlify(payload[0:4]).decode()
                    if uid in state.monsters: del state.monsters[uid]
                elif opcode == 0x241: # Hit
                    state.waiting_for_hit.set()

                buffer = buffer[total:]
        except: break

def heartbeat_sender(engine):
    """0x101 Sync Loop."""
    while not state.stop_event.is_set():
        try:
            pos = state.last_map_coords
            if state.target_uid in state.monsters:
                m = state.monsters[state.target_uid]
                pos = m['x'] + m['y']
            engine.send_hex("00060101" + pos)
        except: break
        time.sleep(1.0)

# === GUI APPLICATION ===

class App:
    def __init__(self, root, engine):
        self.root = root
        self.engine = engine
        self.root.title("IRUNA COMMANDER PRO")

        # Warp Control
        f_warp = ttk.LabelFrame(root, text="Map Handshakes")
        f_warp.pack(fill="x", padx=10, pady=5)
        ttk.Button(f_warp, text="Miscern (300) → Fort Bailune (400)", 
                   command=lambda: engine.warp_handshake("0190", "02", "000e", "0013")).pack(side="left", padx=5, pady=5)

        # Custom Hex
        f_hex = ttk.LabelFrame(root, text="Manual Injection")
        f_hex.pack(fill="x", padx=10, pady=5)
        self.hex_ent = ttk.Entry(f_hex, width=40)
        self.hex_ent.pack(side="left", padx=5, pady=5)
        ttk.Button(f_hex, text="Send Hex", command=self.send_manual).pack(side="left", padx=5)

        # Radar
        self.lb = tk.Listbox(root, height=10, font=("Consolas", 10))
        self.lb.pack(fill="both", expand=True, padx=10, pady=5)
        self.refresh()

    def send_manual(self): 
        self.engine.send_hex(self.hex_ent.get().strip(), "GUI")
        self.hex_ent.delete(0, tk.END)

    def refresh(self):
        self.lb.delete(0, tk.END)
        for uid, d in list(state.monsters.items()):
            self.lb.insert(tk.END, f"ID: {d['id']} | UID: {uid} | POS: {d['x']},{d['y']}")
        self.root.after(1000, self.refresh)

def main():
    # THE AUTH URL (Mikeross version)
    URL = "https://gae4php82-real.an.r.appspot.com/_ah/login?continue=https://gae4php82-real.an.r.appspot.com/authcreate&auth=g.a0008AjsE7nmtOE_FRrLzq3c0eCenIrHPLtvizyyNSyUpEC01rs3xOPaAL3b6yqU6aCo6AzWVQACgYKAesSARESFQHGX2MivSa5uCui6fUjbNajHhfgERoVAUF8yKoQVfPkaFGTvdLOGFA-XYpY0076"

    eng = IrunaEngine(state)
    if eng.full_login_handshake(URL):
        threading.Thread(target=continuous_receiver, args=(eng,), daemon=True).start()
        threading.Thread(target=heartbeat_sender, args=(eng,), daemon=True).start()

        root = tk.Tk()
        app = App(root, eng)
        root.mainloop()

if __name__ == "__main__":
    main()