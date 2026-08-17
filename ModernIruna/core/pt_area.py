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
    
    # When creating, current map is the base map
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
    current_map = getattr(state, 'current_map_hex', '00030d42')
    if len(current_map) < 8: current_map = current_map.zfill(8)
    hex_send(sock, f"00120114000aae600000000000000000{current_map}", "PT_AREA_ENTER")
    
    print("    [!] Waiting for Map Sync OK (b503)...")
    if not state.map_ready_event.wait(timeout=10.0):
        print("[!] Timeout waiting for PT Area Map Sync OK. Instance may have expired.")
        return False
    
    time.sleep(0.1)
    
    # 4. Handshake 1
    hex_send(sock, "0002b501", "PT_AREA_1")
    time.sleep(0.2)
    
    # 5. Map Sync ACK
    hex_send(sock, "0002013a", "MAP_SYNC_ACK")
    
    # 6. Map Entry Exit (Always uses the base map!)
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
    return True

def auto_rejoin_pt_area_thread(sock, is_expired=False):
    """
    Called when the PT Area expires or map changes.
    Rejoins the existing PT area or creates a new one depending on state.pta_rejoin_mode.
    """
    base_map = getattr(state, 'pt_area_base_map_hex', '00030d42')
    
    if not is_expired:
        print("[*] Rejoining PT Area automatically (not expired)...")
        success = join_pt_area(sock, base_map)
        if not success:
            print("[!] Failed to rejoin PT Area.")
        return

    print(f"[*] Map changed unexpectedly (PTA Expired). PTA Mode: {getattr(state, 'pta_rejoin_mode', 'NONE')}")
    
    mode = getattr(state, 'pta_rejoin_mode', 'NONE')
    
    if mode == "NONE":
        print("[!] PTA Rejoin Mode is NONE. Aborting auto-rejoin.")
        return
        
    print("[*] Checking if PTA is actually expired or if this was just a glitch...")
    hex_send(sock, "0002b502", "PT_AREA_STATUS_CHECK")
    time.sleep(2.0)
    
    if getattr(state, 'pta_active', False):
        print("[+] PTA is STILL ACTIVE! Rejoining immediately without waiting.")
        join_pt_area(sock, base_map)
        return
        
    print("[*] PTA is definitively INACTIVE. Waiting 65 seconds for server cool-down...")
    time.sleep(65.0)
    
    if mode == "REJOIN":
        print("[*] Attempting to REJOIN existing PT Area...")
        join_pt_area(sock, base_map)
    elif mode == "CREATE":
        print("[*] Attempting to CREATE new PT Area...")
        from core.map_teleport import teleport
        print(f"[*] Teleporting to base map {base_map} before creating PT Area...")
        teleport(sock, int(base_map, 16), 108, 180)
        time.sleep(2.0)
        create_and_enter_pt_area(sock, base_map)
