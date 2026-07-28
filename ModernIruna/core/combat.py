"""
combat.py — Combat engine and coordinate heartbeat threads.

Two daemon threads:
  - coordinate_sender: sends position updates every 1s
  - combat_engine: auto-attack loop with target selection
"""
import time

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
