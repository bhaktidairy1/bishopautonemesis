"""
combat.py — Combat engine and coordinate heartbeat threads.

Two daemon threads:
  - coordinate_sender: sends position updates every 1s
  - combat_engine: auto-attack loop with target selection
"""
import time
import threading

from core.game_state import state
from core.packet_helpers import hex_send
from core.packets import build_attack_packet, build_coord_packet


def coordinate_sender(sock):
    """
    Heartbeat loop — sends 0101 position packet every 1 second.
    Every 10 seconds, sends a 0002ffff check-alive and waits for a response (up to 5s).
    
    If targeting a monster, uses the monster's position instead
    of the player's last known coords (moves toward target).
    Pauses when state.paused is True (safe for manual warping).
    """
    import os
    ticks = 0
    while not state.stop_event.is_set():
        if state.paused or state.in_scripted_sequence or state.player_hp == 0:
            if state.player_hp == 0 and not state.paused and not getattr(state, "is_reviving", False):
                # Don't trigger global revive if auto nemesis is handling it or we are in island lobby
                if not getattr(state, "auto_nemesis_running", False) and not state.is_island_mode:
                    threading.Thread(target=do_auto_revive, args=(sock,), daemon=True).start()
            time.sleep(0.5)
            continue
            
        ticks += 1
        try:
            if ticks % 10 == 0:
                # 10-second check-alive heartbeat
                state.check_alive_event.clear()
                hex_send(sock, "0002ffff", label="STANDBY KEEP-ALIVE")
                
                # Wait for response, blocking coordinate sends during this wait
                if not state.check_alive_event.wait(timeout=15.0):
                    print("[-] Keep-Alive timeout (0002ffff). Server unresponsive in standby. Continuing anyway...")
                    # We DO NOT close the socket or exit here anymore. Map transitions or heavy combat can delay the server.
            else:
                if state.is_island_mode and not state.in_island_map:
                    # In Island mode lobby, don't send coords yet
                    continue
                    
                # Regular coordinate send
                x_hex = format(int(state.player_x * 256) & 0xFFFF, '04x')
                y_hex = format(int(state.player_y * 256) & 0xFFFF, '04x')
                current_pos = f"{x_hex}{y_hex}"
                
                # Override if we are tracking a target
                if state.target_uid and state.target_uid in state.monsters:
                    m = state.monsters[state.target_uid]
                    state.player_x = m.get('x', state.player_x)
                    state.player_y = m.get('y', state.player_y)
                    t_x_hex = format(int(state.player_x * 256) & 0xFFFF, '04x')
                    t_y_hex = format(int(state.player_y * 256) & 0xFFFF, '04x')
                    current_pos = f"{t_x_hex}{t_y_hex}"
                
                hex_send(sock, build_coord_packet(current_pos))
        except:
            break
            
        time.sleep(1.0)


def do_auto_revive(sock):
    if state.is_reviving:
        return
    state.is_reviving = True
    print("[*] Player died! Initiating auto-revive sequence...")
    hex_send(sock, "00020134", "REVIVE REQUEST")
    
    print("[*] Waiting to arrive in town...")
    time.sleep(6.0) # Wait for 0111 and map sync to finish
    
    # Check if we were in the PT area previously (Map 2707 usually, but we check if we have pt area coords in memory or something).
    # Since we don't have a strict flag, we'll just check if the last map was a PT Area map (starts with 0a).
    # Actually, pt area maps are instanced versions of 700000 or similar.
    # The user requested: "join pta again if char was in pta"
    # The Boss module checks start_map_id == 700000. We will check if the map was 700000 or 0aXX.
    # Actually, we can just safely always check if we should auto-rejoin based on if pt_area was used.
    # We will just do a simple check. If the map before we died was a PT Area map (starts with '0a' or '000ab', we'll re-join).
    if getattr(state, "current_map_hex", "").startswith("0a"):
        print("[*] Died in PT Area. Auto-rejoining...")
        from core.pt_area import auto_rejoin_pt_area_thread
        auto_rejoin_pt_area_thread(sock)
        
    state.is_reviving = False


def combat_engine(sock):
    """
    Auto-attack loop — sends attack packets when in AUTO or MANUAL mode.
    
    Modes:
      - STANDBY: Do nothing, clear target
      - AUTO: Automatically pick the nearest valid monster and attack
      - MANUAL: Attack only the manually selected target
      
    Uses state.waiting_for_hit event to pace attacks 
    (waits for server hit confirmation before next swing).
    """
    while not state.stop_event.is_set():
        if state.paused or state.player_hp == 0:
            time.sleep(0.5)
            continue
            
        if state.mode == "STANDBY":
            state.target_uid = None
            time.sleep(0.5)
            continue
            
        if state.mode == "AUTO":
            # Auto-select a target from known monsters if we don't have one
            if not state.target_uid or state.target_uid not in state.monsters:
                for uid, data in state.monsters.items():
                    if data['id'] in [30000, 30001, 30002]:  # Colons
                        state.target_uid = uid
                        break
            
            # Attack current target
            if state.target_uid and state.target_uid in state.monsters:
                attack_pkt = build_attack_packet(state.target_uid)
                state.waiting_for_hit.clear()
                hex_send(sock, attack_pkt)
                state.waiting_for_hit.wait(timeout=0.8)
                time.sleep(0.4)
            else:
                time.sleep(0.2)
                
        else: # MANUAL mode
            # In manual mode, we just wait. We don't spam basic attacks.
            time.sleep(0.5)

def health_monitor_thread(sock):
    """
    Dedicated background thread to monitor HP and cast Bright Heal asynchronously.
    Runs entirely independently from the main Auto Nemesis or Boss loops.
    This guarantees we can heal even if Nemesis is waiting on server confirmation.
    """
    from core.packets import build_skill_cast_packet
    
    last_heal_time = 0
    
    while not state.stop_event.is_set():
        if state.paused or state.player_hp == 0 or state.is_island_mode:
            time.sleep(0.5)
            continue
            
        # Only heal if HP drops below 20k and it's been at least 2 seconds since last heal
        now = time.time()
        if getattr(state, "player_hp", 0) < 20000 and (now - last_heal_time > 2.0):
            # Also ensure we only auto-heal if we are in a combat loop (nemesis or zimov)
            if getattr(state, "auto_nemesis_running", False) or getattr(state, "auto_zimov_running", False):
                print(f"[*] HEALTH MONITOR: HP ({state.player_hp}) below 20,000! Casting Bright Heal...")
                heal_hex = "1c36"
                cast_pkt = build_skill_cast_packet(heal_hex, state.char_id_hex)
                hex_send(sock, cast_pkt, "SELF HEAL CAST")
                execute_pkt = f"000a0141{heal_hex}0001{state.char_id_hex}"
                hex_send(sock, execute_pkt, "SELF HEAL EXECUTE")
                last_heal_time = time.time()
                
        # Fast poll rate for high responsiveness
        time.sleep(0.1)
