'''
#iptables
#server1
iptables -t nat -A OUTPUT -p tcp --dport 30001 -j DNAT --to-destination 192.168.1.20:30001

#server3
iptables -t nat -A OUTPUT -p tcp --dport 30003 -j DNAT --to-destination 192.168.1.24:30003

iptables -t nat -A OUTPUT -p tcp --dport 31096 -j DNAT --to-destination 192.168.1.20:31096


#server4
iptables -t nat -A OUTPUT -p tcp --dport 30004 -j DNAT --to-destination 192.168.1.23:30004

wind ark
000e0110000138800000320000000f00
before boss:
000e01100001388a0000320000000f00
forceWarp(15900, 67, 128) to go to zimov
forceWarp(25100, 87, 92) go to kakeula

# harvey specter  https://gae4php82-real.an.r.appspot.com/_ah/login?continue=https://gae4php82-real.an.r.appspot.com/authcreate&auth=g.a000_AgHxtZwYUg6UzxIoLktRY9_0NIwsEP6RIrKMlJPrvFr7Yz4WpxEYi9ex-vcdsUEikqZzAACgYKAQsSARYSFQHGX2MicDCklNW1k0JgRkX3M-OD0xoVAUF8yKq5o_EDjiK3yaOGce1R1iy20076
#

#mikeross
# https://gae4php82-real.an.r.appspot.com/_ah/login?continue=https://gae4php82-real.an.r.appspot.com/authcreate&auth=g.a000_QjsE7dNos7nJeqRo5Sj1nY8GLhKNmN2td3cBldGwd8dRu8LsifU-AWT-zBSMxOPQhHs4AACgYKAWwSARESFQHGX2MikAfVYXjuZyGLSrYhpy84kBoVAUF8yKpIhRf8-TUie2uRq0DQloSp0076




'''
import socket
import threading
import time
import tkinter as tk
from datetime import datetime

# Configuration
PROXY_HOST = '192.168.1.23'
PROXY_PORT = 30004
SERVER_HOST = '202.239.51.41'
SERVER_PORT = 30004



# Active sockets
active_server_socket = None
active_client_socket = None

# Heartbeat synchronization
event_heartbeat_done = threading.Event()

import os

# Logging utility
_log_file = None

def init_logger():
    global _log_file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs("proxy_logs", exist_ok=True)
    _log_file = open(f"proxy_logs/proxy_log_{timestamp}.txt", "a", encoding="utf-8")
    _log_file.write(f"=== Proxy Session Started: {datetime.now()} ===\n")
    _log_file.flush()

def log(msg):
    ts = datetime.now().strftime('%H:%M:%S.%f')[:-3]
    log_msg = f"[{ts}] {msg}"
    print(log_msg)
    if _log_file:
        _log_file.write(log_msg + "\n")
        _log_file.flush()

init_logger()

# GUI setup
root = tk.Tk()
root.title('Tcp MitM Proxy Control')

# Actions must wait for heartbeat boundary before sending
def wait_for_heartbeat():
    """
    Block until the next heartbeat end (0x56006200) is observed.
    """
    log("Waiting for heartbeat boundary...")
    event_heartbeat_done.wait()
    event_heartbeat_done.clear()
    log("Heartbeat boundary reached, sending...")

# Custom header and payload send function
def send_custom():
    if not active_server_socket:
        return log("No server connection.")
    header_hex = custom_header_entry.get().strip()
    payload_hex = custom_payload_entry.get().strip()
    try:
        header = bytes.fromhex(header_hex) if header_hex else b''
        payload = bytes.fromhex(payload_hex) if payload_hex else b''
        wait_for_heartbeat()
        if header:
            active_server_socket.sendall(header)
            log(f"Sent custom header to SERVER: {header.hex()}")
        if payload:
            active_server_socket.sendall(payload)
            log(f"Sent custom payload to SERVER: {payload.hex()}")
        if not header and not payload:
            log("Error: Both header and payload are empty.")
    except ValueError:
        log("Error: Invalid hexadecimal string in header or payload.")

def send_custom_client():
    if not active_client_socket:
        return log("No client connection.")
    header_hex = client_header_entry.get().strip()
    payload_hex = client_payload_entry.get().strip()
    try:
        header = bytes.fromhex(header_hex) if header_hex else b''
        payload = bytes.fromhex(payload_hex) if payload_hex else b''
        wait_for_heartbeat()
        if header:
            active_client_socket.sendall(header)
            log(f"Sent custom header to CLIENT: {header.hex()}")
        if payload:
            active_client_socket.sendall(payload)
            log(f"Sent custom payload to CLIENT: {payload.hex()}")
        if not header and not payload:
            log("Error: Both header and payload are empty.")
    except ValueError:
        log("Error: Invalid hexadecimal string in header or payload.")

def update_coords():
    global coords
    hex_input = coords_entry.get().strip()
    try:
        coords = bytes.fromhex(hex_input)
        coords_label.config(text=f"Current Coords: {coords.hex()}")
        log(f"Updated coords to: {coords.hex()}")
    except ValueError:
        log("Error: Invalid hexadecimal string. Please enter a valid hex value.")

def update_precoords():
    global precoords
    hex_input = precoords_entry.get().strip()
    try:
        precoords = bytes.fromhex(hex_input)
        precoords_label.config(text=f"Current Precoords: {precoords.hex()}")
        log(f"Updated precoords to: {precoords.hex()}")
    except ValueError:
        log("Error: Invalid hexadecimal string. Please enter a valid hex value (e.g., '00060101').")



# Custom Packet Frame (Server)
custom_frame = tk.LabelFrame(root, text="Send to Server")
custom_frame.grid(row=4, column=0, padx=10, pady=5, sticky="ew")

custom_header_label = tk.Label(custom_frame, text="Header (hex):")
custom_header_label.grid(row=0, column=0, sticky="w", padx=5, pady=2)

custom_header_entry = tk.Entry(custom_frame, width=40)
custom_header_entry.grid(row=1, column=0, columnspan=2, padx=5, pady=2)

custom_payload_label = tk.Label(custom_frame, text="Payload (hex):")
custom_payload_label.grid(row=2, column=0, sticky="w", padx=5, pady=2)

custom_payload_entry = tk.Entry(custom_frame, width=40)
custom_payload_entry.grid(row=3, column=0, columnspan=2, padx=5, pady=2)

btn_custom = tk.Button(custom_frame, text='Send to Server', command=send_custom)
btn_custom.grid(row=4, column=0, columnspan=2, padx=5, pady=5)

# Custom Packet Frame (Client)
client_frame = tk.LabelFrame(root, text="Send to Client")
client_frame.grid(row=5, column=0, padx=10, pady=5, sticky="ew")

client_header_label = tk.Label(client_frame, text="Header (hex):")
client_header_label.grid(row=0, column=0, sticky="w", padx=5, pady=2)

client_header_entry = tk.Entry(client_frame, width=40)
client_header_entry.grid(row=1, column=0, columnspan=2, padx=5, pady=2)

client_payload_label = tk.Label(client_frame, text="Payload (hex):")
client_payload_label.grid(row=2, column=0, sticky="w", padx=5, pady=2)

client_payload_entry = tk.Entry(client_frame, width=40)
client_payload_entry.grid(row=3, column=0, columnspan=2, padx=5, pady=2)

btn_client_custom = tk.Button(client_frame, text='Send to Client', command=send_custom_client)
btn_client_custom.grid(row=4, column=0, columnspan=2, padx=5, pady=5)

# Coordinates Frame
coords_frame = tk.LabelFrame(root, text="Coordinates")
coords_frame.grid(row=1, column=0, padx=10, pady=5, sticky="ew")

coords_label = tk.Label(coords_frame, text="Current Coords: 829d6320")
coords_label.grid(row=0, column=0, sticky="w", padx=5, pady=2)

coords_entry = tk.Entry(coords_frame, width=20)
coords_entry.insert(0, '829d6320')
coords_entry.grid(row=0, column=1, padx=5, pady=2)

btn_update_coords = tk.Button(coords_frame, text='Update Coords', command=update_coords)
btn_update_coords.grid(row=0, column=2, padx=5, pady=2)

precoords_label = tk.Label(coords_frame, text="Current Precoords: 00060101")
precoords_label.grid(row=1, column=0, sticky="w", padx=5, pady=2)

precoords_entry = tk.Entry(coords_frame, width=20)
precoords_entry.insert(0, '00060101')
precoords_entry.grid(row=1, column=1, padx=5, pady=2)

btn_update_precoords = tk.Button(coords_frame, text='Update Precoords', command=update_precoords)
btn_update_precoords.grid(row=1, column=2, padx=5, pady=2)

# Add near the top with other global variables
packet_flow_active = True

# Add to the GUI section (add this before the mainloop)
flow_control_frame = tk.LabelFrame(root, text="Flow Control")
flow_control_frame.grid(row=2, column=0, padx=10, pady=5, sticky="ew")

def toggle_packet_flow():
    global packet_flow_active
    if packet_flow_active:  # If currently active, wait for heartbeat before pausing
        wait_for_heartbeat()
        packet_flow_active = False
        btn_toggle_flow.config(text="Resume Packets")
        log("Packet flow paused at heartbeat boundary")
    else:  # If currently paused, resume immediately
        packet_flow_active = True
        btn_toggle_flow.config(text="Pause Packets")
        log("Packet flow resumed")

btn_toggle_flow = tk.Button(flow_control_frame, text="Pause Packets", command=toggle_packet_flow)
btn_toggle_flow.grid(row=0, column=0, padx=5, pady=5)

# Auto-Attack Toggle
auto_attack_active = False
def toggle_auto_attack():
    global auto_attack_active
    auto_attack_active = not auto_attack_active
    btn_auto_attack.config(text="Auto Attack: ON" if auto_attack_active else "Auto Attack: OFF")
    log(f"Auto Attack is now {'ON' if auto_attack_active else 'OFF'}")

btn_auto_attack = tk.Button(flow_control_frame, text="Auto Attack: OFF", command=toggle_auto_attack)
btn_auto_attack.grid(row=0, column=1, padx=5, pady=5)

noise = bytes.fromhex('00000011020100000001004a04b59d006600ffff00')
coords = bytes.fromhex('63002800')
precoords = bytes.fromhex('00060101')

ACK_TRADE    = bytes.fromhex('00000003220900')

# Custom exploit packet to send immediately after ACK_TRADE
CUSTOM_EXPLOIT = bytes.fromhex(
    ''
)

KNOWN_OPCODES = {
    '0101': 'COORDS',
    'b503': 'MAP_SYNC_OK',
    'b505': 'MAP_SYNC_REJECT',
    '0110': 'WARP_REQ',
    '0138': 'MAP_READY',
    '013a': 'MAP_SYNC_ACK',
    '3002': 'MAP_ENTRY_EXIT',
    '3003': 'MAP_DATA',
    '0245': 'MOB_SPAWN',
    '0248': 'BOSS_SPAWN',
    '0249': 'MOB_DATA',
    '0244': 'MOB_DEATH',
    '0123': 'ITEM_DROP',
    '4018': 'ITEM_DROP_4018',
    '0120': 'INVENTORY_SYNC',
    '0143': 'SKILL_CAST',
    '0148': 'SKILL_DAMAGE',
    '0146': 'HIT_CONFIRM',
    'ffff': 'KEEP_ALIVE',
    '0157': 'BATTLE_STATE',
}

def format_packet(label, data_hex):
    desc = ""
    opcode = ""
    # Try to extract opcode based on known packet headers
    if label == 'S→C' and len(data_hex) >= 12:
        opcode = data_hex[8:12]
    elif label == 'C→S' and len(data_hex) >= 8:
        opcode = data_hex[4:8]
        
    if opcode in KNOWN_OPCODES:
        desc = f" [{KNOWN_OPCODES[opcode]}]"
    else:
        # Fallback rough scan for embedded packets
        for op, name in KNOWN_OPCODES.items():
            if op in data_hex and len(data_hex) < 40:
                desc = f" [*{name}*]"
                break
                
    return f"{label}{desc}: {data_hex}"

# Relay logic (pass through with logging)
def relay(src, dst, label):
    global auto_attack_active
    while True:
        try:
            data = src.recv(4096)
            if not data:
                break

            # Heartbeat detection
            if label == 'C→S':
                if data == precoords:
                    event_heartbeat_done.clear()
                elif data == coords:
                    event_heartbeat_done.set()

            # Always forward original packet if flow active
            if packet_flow_active:
                log(format_packet(label, data.hex()))
                dst.sendall(data)
                
                # Check for mob spawn and trigger auto-attack if active
                if auto_attack_active and label == 'S→C' and len(data) >= 12:
                    opcode_str = data[4:6].hex()
                    if opcode_str in ('0245', '0248'):
                        uid = data[6:10]
                        # Craft the skill cast packet targeting this UID
                        # e.g., 000a0143 + 00000100 + UID
                        # You mentioned: 440080cd 000a 0143 00000100 1c000a86
                        # Since we intercept it at S->C, we need to send C->S to the server.
                        # Wait for next C->S boundary or just send it directly if thread-safe.
                        # We are in the relay thread, so we can use active_server_socket.
                        
                        # Turn off the auto attack trigger immediately
                        auto_attack_active = False
                        root.after(0, lambda: btn_auto_attack.config(text="Auto Attack: OFF"))
                        log("Auto Attack triggered and turned OFF.")
                        
                        def execute_attack(target_uid):
                            time.sleep(0.5)  # Wait 0.5 seconds before striking
                            
                            # The multi-part Backstab skill attack:
                            # Part 1: Skill Cast execution
                            p1 = bytes.fromhex('000a01431b870102') + target_uid
                            # Part 2: Skill Damage calculation (with max dmg flag 000000b4)
                            p2 = bytes.fromhex('000e01484e210102') + target_uid + bytes.fromhex('000000b4')
                            
                            if active_server_socket:
                                active_server_socket.sendall(p1)
                                log(f"C→S [AUTO_ATTACK_1]: {p1.hex()}")
                                time.sleep(0.05)
                                active_server_socket.sendall(p2)
                                log(f"C→S [AUTO_ATTACK_2]: {p2.hex()}")
                                
                        threading.Thread(target=execute_attack, args=(uid,), daemon=True).start()
                
                # If client just sent ACK_TRADE, inject exploit
                if label == 'S→C' and data == ACK_TRADE:
                    log(f"Detected ACK_TRADE, sending custom exploit payload: {CUSTOM_EXPLOIT.hex()}")
                    dst.sendall(CUSTOM_EXPLOIT)
            else:
                log(f"{label} (dropped): {data.hex()}")

        except Exception as e:
            log(f"Relay error: {e}")
            break

# Handle client connections
def handle_client(client_sock, addr):
    global active_server_socket, active_client_socket
    log(f"Client connected: {addr}")
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.connect((SERVER_HOST, SERVER_PORT))
    active_server_socket = server_sock
    active_client_socket = client_sock
    log(f"Connected to {SERVER_HOST}:{SERVER_PORT}")

    threading.Thread(target=relay, args=(client_sock, server_sock, 'C→S'), daemon=True).start()
    threading.Thread(target=relay, args=(server_sock, client_sock, 'S→C'), daemon=True).start()
    try:
        while server_sock.fileno() != -1 and client_sock.fileno() != -1:
            time.sleep(0.5)
    finally:
        client_sock.close()
        server_sock.close()
        active_server_socket = None
        active_client_socket = None
        log("Connection closed")

# Start proxy server
def start_proxy():
    proxy = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    proxy.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    proxy.bind((PROXY_HOST, PROXY_PORT))
    proxy.listen(5)
    log(f"Proxy listening on {PROXY_HOST}:{PROXY_PORT}")
    try:
        while True:
            clsock, caddr = proxy.accept()
            threading.Thread(target=handle_client, args=(clsock, caddr), daemon=True).start()
    except KeyboardInterrupt:
        pass
    finally:
        proxy.close()
        log("Proxy stopped")

if __name__ == '__main__':
    threading.Thread(target=start_proxy, daemon=True).start()
    
    import signal
    import sys
    
    def on_closing():
        log("Shutting down proxy...")
        if active_client_socket:
            try: active_client_socket.close()
            except: pass
        if active_server_socket:
            try: active_server_socket.close()
            except: pass
        root.destroy()
        os._exit(0)
        
    root.protocol("WM_DELETE_WINDOW", on_closing)
    signal.signal(signal.SIGINT, lambda sig, frame: on_closing())
    
    # Keep the python interpreter waking up so it can catch the Ctrl+C signal
    def check_signals():
        root.after(100, check_signals)
        
    check_signals()
    root.mainloop()