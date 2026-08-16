import time
import threading
from core.packet_helpers import hex_send
from core.game_state import state
from core.packets import build_warp_entry_packet
from core.map_teleport import teleport

def create_and_enter_pt_area(sock, map_hex=None):
    if not map_hex:
        map_hex = getattr(state, 'current_map_hex', '00030d42')
    if len(map_hex) < 8: map_hex = map_hex.zfill(8)
    
    print(f"[*] Initiating PT Area Sequence for Map {map_hex}...")
    
    hex_send(sock, f"0006b500{map_hex}", "PT_AREA_CREATE")
    time.sleep(0.4)
    hex_send(sock, "0002b502", "PT_AREA_2")
    time.sleep(0.4)
    hex_send(sock, "0002b509", "PT_AREA_9")
    time.sleep(1.2)
    
    state.map_ready_event.clear()
    hex_send(sock, f"00120114000aae600000000000000000{map_hex}", "PT_AREA_ENTER")
    
    print("    [!] Waiting for Map Sync OK (b503)...")
    if not state.map_ready_event.wait(timeout=10.0):
        print("[!] Timeout waiting for PT Area Map Sync OK.")
    time.sleep(0.1)
    
    hex_send(sock, "0002b501", "PT_AREA_1")
    time.sleep(0.2)
    hex_send(sock, "0002013a", "MAP_SYNC_ACK")
    hex_send(sock, build_warp_entry_packet(map_hex), "MAP_ENTRY")
    print("[+] Successfully entered PT Area.")
    
    # 8. Force position to a safe spot (108, 180) to avoid instantly pulling aggro
    time.sleep(1.0)
    print("[*] Forcing position to safe spot (108, 180)...")
    state.player_x = 108.0
    state.player_y = 180.0
    
    from core.packets import build_coord_packet
    from core.map_teleport import _make_heartbeat_coords
    coords = _make_heartbeat_coords(108, 180)
    hex_send(sock, build_coord_packet(coords), "FORCE COORD")

def join_pt_area(sock, map_hex=None):
    if not map_hex:
        # Default to whatever the last known base map was, or Miscerene Plains if unknown
        map_hex = getattr(state, 'pt_area_base_map_hex', '00030d42')
    if len(map_hex) < 8: map_hex = map_hex.zfill(8)
    
    print(f"[*] Initiating PT Area Join Sequence for Map {map_hex}...")
    
    # 1. Handshake 2
    hex_send(sock, "0002b502", "PT_AREA_2")
    time.sleep(0.4)
    
    # 2. Handshake 9
    hex_send(sock, "0002b509", "PT_AREA_9")
    time.sleep(1.2)
    
    state.map_ready_event.clear()
    
    # 3. Enter Area 
    hex_send(sock, f"00120114000aae600000000000000000{map_hex}", "PT_AREA_ENTER")
    
    print("    [!] Waiting for Map Sync OK (b503)...")
    if not state.map_ready_event.wait(timeout=10.0):
        print("[!] Timeout waiting for PT Area Map Sync OK.")
    
    time.sleep(0.1)
    
    # 4. Handshake 1
    hex_send(sock, "0002b501", "PT_AREA_1")
    time.sleep(0.2)
    
    # 5. Map Sync ACK
    hex_send(sock, "0002013a", "MAP_SYNC_ACK")
    
    # 6. Map Entry Exit 
    hex_send(sock, build_warp_entry_packet(map_hex), "MAP_ENTRY")
    
    print("[+] Successfully joined PT Area.")
    
    time.sleep(1.0)
    print("[*] Forcing position to safe spot (108, 180)...")
    state.player_x = 108.0
    state.player_y = 180.0
    
    from core.packets import build_coord_packet
    from core.map_teleport import _make_heartbeat_coords
    coords = _make_heartbeat_coords(108, 180)
    hex_send(sock, build_coord_packet(coords), "FORCE COORD")

def auto_rejoin_pt_area_thread(sock):
    """
    Called when the PT Area expires or map changes.
    Rejoins the existing PT area for the base map.
    """
    print("[*] Rejoining PT Area automatically...")
    
    base_map = getattr(state, 'pt_area_base_map_hex', '00030d42')
    
    # Check if we are already in the base map. If not, we might need to teleport there first?
    # Wait, the join sequence requires you to be in the base map FIRST!
    if state.current_map_hex and int(state.current_map_hex, 16) != int(base_map, 16):
        print(f"[*] Teleporting to base map {base_map} before joining PT Area...")
        teleport(sock, int(base_map, 16), 108, 180)
        time.sleep(2.0)
    
    # Join the existing PT Area
    join_pt_area(sock, base_map)
