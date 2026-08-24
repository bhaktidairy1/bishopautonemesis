import time
import threading
from core.packet_helpers import hex_send
from core.game_state import state
from core.packets import build_warp_entry_packet
from core.map_teleport import teleport

def create_and_enter_pt_area(sock, map_hex=None):
    if not map_hex:
        map_hex = getattr(state, 'pt_area_base_map_hex', getattr(state, 'current_map_hex', '000086c4'))
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
    
    if state.current_map_hex != "ae60":
        print("[-] Server rejected PT Area entry! You are likely on a server cooldown.")
        return False
        
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
        # Default to whatever map the user was currently tracking in state, or fallback to current map
        map_hex = getattr(state, 'pt_area_base_map_hex', getattr(state, 'current_map_hex', '000086c4'))
        
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
        # We don't return False here, because the check below is more reliable
    time.sleep(0.1)
    
    if state.current_map_hex != "ae60":
        print("[-] Server rejected PT Area entry! The host may not have created it yet.")
        return False
        
    # 4. Map Sync 1
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
    base_map = getattr(state, 'pt_area_base_map_hex', '000086c4')
    
    if not is_expired:
        print("[*] Rejoining PT Area automatically (not expired)...")
        success = join_pt_area(sock, base_map)
        if not success:
            print("[!] Failed to rejoin PT Area.")
        return

    print(f"[*] PTA Reset Sequence Triggered. PTA Mode: {getattr(state, 'pta_rejoin_mode', 'NONE')}")
    
    mode = getattr(state, 'pta_rejoin_mode', 'NONE')
    
    if mode == "NONE":
        print("[!] PTA Rejoin Mode is NONE. Aborting auto-rejoin.")
        return
        
    from core.map_teleport import teleport
    
    if mode == "CREATE":
        print("[*] CREATE MODE: Moving to safe town (Kakeula 25100) to wait out server cooldown...")
        teleport(sock, 25100, 87, 92)
        
        # Wait 5 minutes (300 seconds)
        print("[*] Waiting 300 seconds (5 minutes) before recreating PT Area...")
        for i in range(300, 0, -10):
            if getattr(state, 'pta_rejoin_mode', 'NONE') != "CREATE":
                print("[!] PTA mode changed. Aborting wait.")
                return
            if i % 30 == 0:
                print(f"[*] Waiting... {i} seconds left before creation.")
            time.sleep(10)
            
        print(f"[*] Cooldown complete. Teleporting to base map {base_map}...")
        teleport(sock, int(base_map, 16), 120, 120)
        time.sleep(2.0)
        create_and_enter_pt_area(sock, base_map)
        start_proactive_pta_timer(sock)
        
    elif mode == "REJOIN":
        print("[*] REJOIN MODE: Moving to safe town (Kakeula 25100) while waiting for old PTA to expire...")
        teleport(sock, 25100, 87, 92)
        
        # Wait 5 minutes (300 seconds) to ensure the old instance is completely gone
        print("[*] Waiting 300 seconds (5 minutes) before polling for new PT Area...")
        for i in range(300, 0, -10):
            if getattr(state, 'pta_rejoin_mode', 'NONE') != "REJOIN":
                print("[!] PTA mode changed. Aborting wait.")
                return
            if i % 30 == 0:
                print(f"[*] Waiting... {i} seconds left before polling.")
            time.sleep(10)
        
        print("[*] REJOIN MODE: Polling server every 10 seconds until new PT area is active.")
        timeout = 360 # 6 minutes max wait
        elapsed = 0
        while elapsed < timeout:
            if getattr(state, 'pta_rejoin_mode', 'NONE') != "REJOIN":
                print("[!] PTA mode changed. Aborting rejoin.")
                return
                
            hex_send(sock, "0002b502", "PT_AREA_STATUS_CHECK")
            time.sleep(2.0)
            
            if getattr(state, 'pta_active', False):
                print("[+] PT Area is now ACTIVE! Rejoining...")
                time.sleep(3.0) # Give host an extra 3 seconds to fully enter
                join_pt_area(sock, base_map)
                start_proactive_pta_timer(sock)
                return
                
            if elapsed % 30 == 0:
                print(f"[*] Still waiting for host to create PTA... (Waited {elapsed+2}s)")
            time.sleep(8.0)
            elapsed += 10
            
        print("[-] Timed out waiting for host to create PT Area after 6 minutes.")

def start_proactive_pta_timer(sock):
    """
    Starts a proactive timer in the background using the server's reported time.
    """
    # If a timer is already running, don't start a new one.
    if getattr(state, 'pta_timer_running', False):
        print("[*] Proactive PT Area timer already running. Not starting a duplicate.")
        return
        
    def _timer_thread():
        state.pta_timer_running = True
        
        # Give the b502 packet a moment to be parsed by receiver.py
        time.sleep(2.0)
        
        # Default to 59 minutes if no exact time is known yet
        remaining_secs = getattr(state, 'pta_time_remaining', 3540)
        
        # Proactively leave 60 seconds before server expiration
        sleep_time = remaining_secs - 60
        
        if sleep_time <= 0:
            print("[!] PT Area is about to expire right now! Initiating reset immediately.")
            sleep_time = 0
        else:
            mins = int(sleep_time // 60)
            secs = int(sleep_time % 60)
            print(f"[*] Proactive PT Area timer STARTED. Sleeping for {mins}m {secs}s (until 1 min before server expiry).")
        
        for i in range(int(sleep_time), 0, -10):
            sleep_chunk = min(i, 10)
            time.sleep(sleep_chunk)
            
        print("[!] Proactive PT Area timer EXPIRED (1 min before server)! Initiating proactive reset sequence...")
        state.pta_timer_running = False
        
        mode = getattr(state, 'pta_rejoin_mode', 'NONE')
        if mode == "NONE":
            print("[*] Auto-PTA mode disabled. Ignoring proactive reset.")
            return
            
        auto_rejoin_pt_area_thread(sock, is_expired=True)
        
    threading.Thread(target=_timer_thread, daemon=True).start()
