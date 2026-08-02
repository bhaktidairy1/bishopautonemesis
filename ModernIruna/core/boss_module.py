import time
import binascii

from core.game_state import state
from core.packet_helpers import hex_send
from core.packets import (
    PKT_MAP_SYNC_BEGIN, PKT_MOVEMENT_STEPS, PKT_WARP_SYNC_START, PKT_WARP_SYNC_END,
    build_warp_exit_packet, build_warp_position_packet, build_warp_entry_packet
)
from core.map_teleport import teleport
from core.inventory import calculate_bag_usage

# Hardcoded backstab packets provided by user for Boss
# Use max damage flag 'b4' on the skill
BACKSTAB_CAST_PREFIX   = "000a01431b870102"
BACKSTAB_DAMAGE_PREFIX = "000e01484e210102"

def log_and_exit(msg):
    import os
    from core.packet_helpers import write_log
    print(f"\n[CRITICAL EXIT] {msg}")
    write_log(f"CRITICAL EXIT TRIGGERED: {msg}")
    os._exit(1)
BACKSTAB_CAST_PREFIX   = "000a01431b870102"
BACKSTAB_DAMAGE_PREFIX = "000e01484e210102"

def do_warp_sync(sock, from_map: str, to_map: str, x: str, y: str, portal_id: str = "00", send_exit: bool = True, wait_3003: bool = True):
    """
    Executes a single step of the warp sequence and waits for b503/b505 Map Sync.
    """
    print(f"\n[*] Scripted Warp: {from_map} -> {to_map} ({x}, {y})")
    
    state.teleport_event.clear()
    state.map_ready_event.clear()
    
    # Send warp packets (No 3006 packets as per user request)
    # The client sends the 3002 Exit packet and 0110 Position packet back-to-back.
    if send_exit:
        hex_send(sock, build_warp_exit_packet(portal_id, from_map))
    hex_send(sock, build_warp_position_packet(to_map, x, y))
    
    # Wait for b503 (or b505) and 0138 Map Ready
    print("    [!] Waiting for Map Sync (b503/b505) + Ready (0138)...")
    if not state.teleport_event.wait(timeout=10):
        try: sock.close()
        except: pass
        log_and_exit("Teleport timeout (b503). Server unresponsive.")
        
    if not state.map_ready_event.wait(timeout=10):
        try: sock.close()
        except: pass
        log_and_exit("Map Ready timeout (0138). Server unresponsive.")
    
    # Clear map data event just before we trigger the entry, to avoid premature triggers
    state.map_data_event.clear()
    
    # Acknowledge Map Ready and enter
    hex_send(sock, PKT_MAP_SYNC_BEGIN)
    hex_send(sock, build_warp_entry_packet(to_map))
    
    # Wait for 3003 Map Data
    if wait_3003:
        print("    [!] Waiting for Map Data (3003)...")
        if not state.map_data_event.wait(timeout=10):
            try: sock.close()
            except: pass
            log_and_exit("Map Data timeout (3003). Server unresponsive.")
    
    time.sleep(0.1)


def zimov_battle_thread(sock):
    """
    Scripted flow:
      1. Warp from Dierolt (3e1c) to Boss Room 1 (3e58)
      2. Warp from Boss Room 1 (3e58) to Boss Room 2 (3e76)
      3. Wait for Zimov to spawn (catch UID)
      4. Use Backstab twice (max damage B4)
      5. Wait for drops (0123 / 4018 logic automatically handled by receiver.py)
      6. Warp back to Boss Room 1 (3e58)
      7. Warp back to Dierolt (3e1c)
    """
    if state.current_map_hex != "3e1c":
        print("[!] Cannot start Zimov script — not in Dierolt (3e1c)")
        return
        
    print("\n" + "="*50)
    print(" [ZIMOV AUTOMATION STARTED]")
    print("="*50)
    
    # Take control from coordinate sender
    state.in_scripted_sequence = True
    state.boss_id_hex = None
    state.boss_spawn_event.clear()
    state.boss_death_event.clear()
    
    try:
        # Step 1: 3e1c -> 3e58 (Entrance coords roughly 4300 7c00 from logs, portal 02)
        do_warp_sync(sock, "3e1c", "3e58", "4300", "7c00", portal_id="02")
        
        # Step 2: 3e58 -> 3e76 (Boss coords roughly 4400 8300 from logs, portal 04)
        do_warp_sync(sock, "3e58", "3e76", "4400", "8300", portal_id="04", wait_3003=False)
        
        # Step 3: Wait for Boss Spawn (receiver.py catches 0248/0245)
        print("\n[*] Waiting for Zimov to spawn...")
        state.boss_spawn_event.clear()
        if not state.boss_spawn_event.wait(timeout=10):
            log_and_exit("Boss spawn timeout! (Waited 10s for 0248/0245)")
        else:
            print(f"[+] Zimov Spawned! UID: {state.boss_id_hex}")
            time.sleep(0.2) # Wait 0.2s before strike
            
            # Step 4: Backstab
            print("[*] Executing Backstab Sequence...")
            # 000a01431b870102 + Boss UID
            cast_pkt = BACKSTAB_CAST_PREFIX + state.boss_id_hex
            hex_send(sock, cast_pkt)
            
            # The client sends the angle of the backstab at the end, 
            # e.g. 00000000 or 000000b3. 
            # The previous '000000b4' flag was triggering a simultaneous fatal response from the boss.
            dmg_pkt = BACKSTAB_DAMAGE_PREFIX + state.boss_id_hex + "00000000"
            hex_send(sock, dmg_pkt)
            
            # Wait for boss death confirmation / drops
            print("[*] Waiting for Boss death / drops...")
            state.boss_death_event.wait(timeout=10)
            
            # Send battle state cleared packet (Client telling server combat is over)
            print("[*] Releasing combat state...")
            battle_end_pkt = "00060157" + state.boss_id_hex
            hex_send(sock, battle_end_pkt)
            time.sleep(0.1)
            
        if state.is_reviving or state.current_map_hex != "3e76":
            print("[!] Player died or map changed during sequence. Aborting Zimov battle thread.")
            return
            
        # Step 5: 3e76 -> 3e58 (Exit coords roughly 4300 5000)
        # Note: Genuine client skips the 3002 Exit packet when leaving instances!
        do_warp_sync(sock, "3e76", "3e58", "4300", "5000", send_exit=False, wait_3003=False)
        
        # Step 6: 3e58 -> 3e1c (Exit coords roughly 4300 5200, portal 08)
        # Note: Genuine client sends 3002 Exit and 0110 Pos together, and doesn't wait for 3003!
        # HOWEVER, we MUST wait for 3003 here so the next loop doesn't start too early!
        do_warp_sync(sock, "3e58", "3e1c", "4300", "5200", portal_id="08", wait_3003=True)
        
        print("\n[+] Zimov Sequence Complete.")
        
    except Exception as e:
        print(f"[CRITICAL] Zimov sequence failed: {e}")
        if "10054" in str(e) or "closed" in str(e).lower() or isinstance(e, (ConnectionError, OSError)):
            log_and_exit(f"Connection dropped ({e}). Stopping automation.")
        
    finally:
        # Return control
        state.in_scripted_sequence = False
        print("="*50 + "\n")


def kakeula_heal_thread(sock, return_map_id=15900, return_x=67, return_y=128):
    """
    Scripted flow:
      1. Teleport to Kakeula (25100, 87, 92)
      2. Wait for map load
      3. Send heal interaction packet
      4. Wait for 3003 map data response
      5. Teleport back to original map (default Dierolt 15900)
    """
    if state.in_scripted_sequence:
        print("[!] Cannot start Heal script — a sequence is already running")
        return

    print("\n" + "="*50)
    print(" [HEAL SEQUENCE STARTED]")
    print("="*50)

    state.in_scripted_sequence = True

    try:
        # Step 1: Teleport to Kakeula
        print("[*] Warping to Kakeula (25100)...")
        result = teleport(sock, 25100, 87, 92)
        if not result:
            print("[-] Teleport to Kakeula failed.")
            return

        print("[*] Map loaded. Sending heal interaction...")

        # Step 2: Send heal interaction packet
        heal_pkt = "0011300211000000040000000200000000620c"
        
        # Clear map data event to wait for the 3003 response from the heal
        state.map_data_event.clear()
        hex_send(sock, heal_pkt, label="HEAL INTERACTION")

        # Wait for 3003 response
        if not state.map_data_event.wait(timeout=10.0):
            print("[-] Timeout waiting for heal confirmation (3003).")
        else:
            print("[+] Heal confirmed by server.")

        # Step 3: Teleport back
        print(f"[*] Returning to Map {return_map_id}...")
        teleport(sock, return_map_id, return_x, return_y)

        print("\n[+] Heal Sequence Complete.")

    except Exception as e:
        print(f"[-] Kakeula Heal Sequence Error: {e}")
        if "10054" in str(e) or "closed" in str(e).lower() or isinstance(e, (ConnectionError, OSError)):
            log_and_exit(f"Connection dropped during heal ({e}). Stopping automation.")
    finally:
        state.in_scripted_sequence = False


def kakeula_sell_thread(sock):
    """
    Scripted flow:
      1. Teleport to Kakeula (25100, 87, 92)
      2. Wait for map load
      3. Send merchant interaction packet (0208)
      4. Bulk sell whitelisted items (Zimov Tail, Lithium, Zimov, Esmeralda)
      5. Wait for 0120 (inventory refresh)
      6. Return to Dierolt
    """
    if state.in_scripted_sequence:
        print("[!] Cannot start Sell script — a sequence is already running")
        return

    print("\n" + "="*50)
    print(" [SELL SEQUENCE STARTED]")
    print("="*50)

    state.in_scripted_sequence = True

    try:
        # Step 1: Teleport to Kakeula
        print("[*] Warping to Kakeula (25100)...")
        result = teleport(sock, 25100, 87, 92)
        if not result:
            print("[-] Teleport to Kakeula failed.")
            return

        print("[*] Map loaded. Refreshing inventory for accurate instance IDs...")
        hex_send(sock, "00020120", label="PRE-SELL INV REFRESH")
        time.sleep(2.0) # Wait for 0120 response and parse

        print("[*] Opening merchant...")

        # Step 2: Open Merchant
        hex_send(sock, "000402080000", label="OPEN MERCHANT")
        time.sleep(1.0) # Wait a moment for merchant to open

        # Step 3 & 4: Find items to sell and build packet
        whitelist = {
            10430, # Zimov Tail
            10431, # Lithium
            28574, # Zimov (Crysta)
            5209, 5703, 5734, 5775, 5884 # Esmeralda variants
        }
        
        stacks_to_sell = [] # List of tuples: (instance_hex, count_hex)
        
        for key, item_data in state.inventory.items():
            if item_data["id"] in whitelist:
                for slot in item_data.get("slots", []):
                    if slot["count"] > 0 and len(slot["instance"]) == 8:
                        # The game limits selling to 99 items per stack slot at a time.
                        # If a slot has more than 99, we must split it into multiple 99-count stacks
                        # in the bulk sell packet.
                        remaining = slot["count"]
                        while remaining > 0:
                            chunk = min(99, remaining)
                            stacks_to_sell.append((slot["instance"], f"{chunk:02x}"))
                            remaining -= chunk
                        
        if not stacks_to_sell:
            print("[*] No whitelisted items found to sell.")
        else:
            print(f"[*] Selling {len(stacks_to_sell)} stacks of whitelisted items...")
            
            # Build 2101 bulk sell packet
            # Format: [Length (2 bytes)] 2101 [StackCount (4 bytes)] [InstanceID (4 bytes)] [Quantity (1 byte)] ...
            stack_count_hex = f"{len(stacks_to_sell):08x}"
            
            payload = "2101" + stack_count_hex
            for instance, count in stacks_to_sell:
                payload += instance + count
                
            length_hex = f"{int(len(payload)/2):04x}"
            sell_pkt = length_hex + payload
            
            # Send sell packet
            hex_send(sock, sell_pkt, label="BULK SELL")
            
            # Wait a moment for server to process the sell
            time.sleep(1.0)
            
            # Step 5: Update local inventory state manually to avoid sending another 0120
            print("[*] Sell complete. Updating local inventory state...")
            
            prices = {
                10430: 2300,   # Zimov Tail
                10431: 25000,  # Lithium
                28574: 1,      # Zimov (Crysta)
                5209: 50000, 5703: 50000, 5734: 50000, 5775: 50000, 5884: 50000 # Esmeralda variants
            }
            
            spina_gained = 0
            keys_to_delete = []
            
            for key, item_data in state.inventory.items():
                if item_data["id"] in whitelist:
                    item_count = item_data.get("count", 0)
                    price = prices.get(item_data["id"], 0)
                    spina_gained += item_count * price
                    keys_to_delete.append(key)
                    
            for k in keys_to_delete:
                del state.inventory[k]
                
            if spina_gained > 0:
                state.spina_earned += spina_gained
                print(f"[+] Earned {spina_gained:,} Spina from this run! (Total: {state.spina_earned:,})")

        # Step 6: Return to Dierolt
        print("[*] Returning to Dierolt (15900)...")
        teleport(sock, 15900, 67, 128)

        print("\n[+] Sell Sequence Complete.")

    except Exception as e:
        print(f"[-] Kakeula Sell Sequence Error: {e}")
    finally:
        state.in_scripted_sequence = False

def auto_zimov_loop(sock):
    """
    Loops 7 Zimov kills, followed by 1 Kakeula heal, repeatedly.
    """
    state.auto_zimov_running = True
    print("\n==================================================")
    print(" [AUTO ZIMOV LOOP STARTED]")
    print("==================================================")
    
    try:
        while state.auto_zimov_running:
            for i in range(7):
                if not state.auto_zimov_running:
                    break
                    
                print(f"\n[*] Auto-Zimov: Kill {i+1}/7")
                
                # Run the battle sequence synchronously
                zimov_battle_thread(sock)
                state.auto_zimov_kill_count += 1
                
                # Small pause to ensure map fully registers before next iteration
                time.sleep(1.5)
                
                if state.current_map_hex != "3e1c" or getattr(state, "is_reviving", False):
                    print("[!] Player is not in Dierolt (likely died). Breaking Zimov kill loop.")
                    break
            
            if not state.auto_zimov_running:
                break
                
            bag_usage = calculate_bag_usage()
            print(f"\n[*] Auto-Zimov: Checking Bag Space ({bag_usage}/50 slots used)")
            
            if bag_usage >= 30:
                print("[*] Bag nearly full! Initiating Auto-Sell...")
                kakeula_sell_thread(sock)
            else:
                print("[*] Auto-Zimov: Healing at Kakeula...")
                kakeula_heal_thread(sock)
                
            state.auto_zimov_run_count += 1
            
            # Wait for heal sequence to complete and return to Dierolt
            time.sleep(1.5)
            
    except Exception as e:
        print(f"[-] Auto-Zimov Loop Error: {e}")
    finally:
        state.auto_zimov_running = False
        print("\n==================================================")
        print(" [AUTO ZIMOV LOOP STOPPED]")
        print("==================================================")

def cast_bishop_buffs(sock):
    """Casts Bishop self-buffs: Revelation, Risparmio, Preire, Bless"""
    from core.packet_helpers import hex_send
    import time
    from core.game_state import state
    print("[*] Refreshing Bishop Self-Buffs...")
    
    buffs = [
        ("1c20", "0001", "Revelation"),
        ("1b8f", "0002", "Risparmio"),
        ("1b8e", "0003", "Preire"),
        ("1b79", "0002", "Bless"),
    ]
    
    for skill_hex, flag, name in buffs:
        state.skill_cast_event.clear()
        
        cast_pkt = f"000a0143{skill_hex}{flag}{state.char_id_hex}"
        hex_send(sock, cast_pkt, f"{name} CAST")
        
        exec_pkt = f"000a0141{skill_hex}{flag}{state.char_id_hex}"
        hex_send(sock, exec_pkt, f"{name} EXECUTE")
        
        # Wait for the 0142 skill result packet instead of blindly sleeping
        if not state.skill_cast_event.wait(timeout=3.0):
            print(f"[-] Timeout waiting for {name} response.")
            
        time.sleep(0.5) # Small buffer between skills

def cast_individual_buff(sock, buff_id):
    """Casts a specific Bishop self-buff"""
    from core.packet_helpers import hex_send
    from core.game_state import state
    
    buffs = {
        "revelation": ("1c20", "0001", "Revelation"),
        "risparmio": ("1b8f", "0002", "Risparmio"),
        "preire": ("1b8e", "0003", "Preire"),
        "bless": ("1b79", "0002", "Bless"),
    }
    
    if buff_id not in buffs:
        return
        
    skill_hex, flag, name = buffs[buff_id]
    print(f"[*] Casting {name}...")
    state.skill_cast_event.clear()
    
    cast_pkt = f"000a0143{skill_hex}{flag}{state.char_id_hex}"
    hex_send(sock, cast_pkt, f"{name} CAST")
    
    exec_pkt = f"000a0141{skill_hex}{flag}{state.char_id_hex}"
    hex_send(sock, exec_pkt, f"{name} EXECUTE")
    
    if not state.skill_cast_event.wait(timeout=3.0):
        print(f"[-] Timeout waiting for {name} response.")

def auto_nemesis_loop(sock):
    """
    Auto Nemesis Grinding Loop:
    Targets nearest mob, casts Nemesis every 1 sec.
    If MP < 1000, returns to Kakeula to heal, then returns to original map.
    """
    state.auto_nemesis_running = True
    print("\n==================================================")
    print(" [AUTO NEMESIS LOOP STARTED]")
    print("==================================================")
    
    try:
        from core.packet_helpers import hex_send
        from core.packets import build_coord_packet, build_skill_cast_packet
        import math
        
        # Save initial map ID and position
        start_map_id = int(state.current_map_hex, 16)
        start_x = state.player_x
        start_y = state.player_y
        # Initialize buff timers
        last_buff_times = {
            "revelation": 0,
            "risparmio": 0,
            "preire": 0,
            "bless": 0
        }
        last_holy_spike_time = 0
        
        while state.auto_nemesis_running:
            # 0. Check Death
            if getattr(state, "player_hp", 1) <= 0:
                print("[*] Player died! Initiating auto-revive sequence...")
                hex_send(sock, "00020134", "REVIVE REQUEST")
                
                print("[*] Waiting to arrive in town...")
                time.sleep(6.0) # Wait for 0111 and map sync to finish
                
                if start_map_id == 700000:
                    print("[*] Died in PT Area. Auto-rejoining...")
                    from core.pt_area import auto_rejoin_pt_area_thread
                    auto_rejoin_pt_area_thread(sock)
                    continue
                else:
                    print(f"[*] Warping back to farm spot (Map {start_map_id})...")
                    res = teleport(sock, start_map_id, start_x, start_y)
                    if not res or res.get("status") != "success":
                        print("[!] Failed to warp back to farm spot (instance expired?). Stopping Auto-Nemesis.")
                        state.auto_nemesis_running = False
                        break
                    time.sleep(2.0)
                    continue

            # 0.5 Check if we accidentally changed maps
            if state.current_map_hex and int(state.current_map_hex, 16) != start_map_id:
                if start_map_id == 700000:
                    print("[*] PT Area expired! Waiting for background thread to re-create it...")
                    while state.current_map_hex != "ae60" and state.auto_nemesis_running:
                        time.sleep(1.0)
                    if not state.auto_nemesis_running:
                        break
                    print("[*] Successfully resumed Auto-Nemesis in new PT Area!")
                    continue
                else:
                    print(f"[*] Map changed unexpectedly. Warping back to {start_map_id}...")
                    res = teleport(sock, start_map_id, start_x, start_y)
                    if not res or res.get("status") != "success":
                        print("[!] Failed to warp back to farm spot (instance expired?). Stopping Auto-Nemesis.")
                        state.auto_nemesis_running = False
                        break
                    time.sleep(2.0)
                    continue

            # 1. Check MP
            if getattr(state, "player_mp", 0) < 1000:
                print(f"[*] MP ({state.player_mp}) below 1000! Healing at Kakeula...")
                kakeula_heal_thread(sock, return_map_id=start_map_id, return_x=start_x, return_y=start_y)
                time.sleep(1.5)
                continue
                
            # 1.5 Check HP and Self Heal
            if getattr(state, "player_hp", 0) < 20000:
                print(f"[*] HP ({state.player_hp}) below 20,000! Casting Bright Heal...")
                heal_hex = "1c36"
                cast_pkt = build_skill_cast_packet(heal_hex, state.char_id_hex)
                hex_send(sock, cast_pkt, "SELF HEAL CAST")
                execute_pkt = f"000a0141{heal_hex}0001{state.char_id_hex}"
                hex_send(sock, execute_pkt, "SELF HEAL EXECUTE")
                time.sleep(1.5) # Wait for heal to finish
                continue
                
            # 1.8 Check Buffs Individually
            now = time.time()
            if now - last_buff_times["revelation"] > 590: # 10 mins (600s), slightly less for safety
                cast_individual_buff(sock, "revelation")
                last_buff_times["revelation"] = time.time()
            if now - last_buff_times["bless"] > 350: # 6 mins (360s)
                cast_individual_buff(sock, "bless")
                last_buff_times["bless"] = time.time()
            if now - last_buff_times["risparmio"] > 290: # 5 mins (300s)
                cast_individual_buff(sock, "risparmio")
                last_buff_times["risparmio"] = time.time()
            if now - last_buff_times["preire"] > 290: # 5 mins
                cast_individual_buff(sock, "preire")
                last_buff_times["preire"] = time.time()
                
            # 2. Find nearest mob
            nearest_uid = None
            min_dist = 999999
            
            px, py = state.player_x, state.player_y
            mobs = list(state.monsters.items())
            
            for uid, m in mobs:
                # Filter strictly to Moss Golems as requested (or its raw ID if DB is missing)
                name = m.get('name', '')
                mob_id = m.get('id', 0)
                if "Moss Golem" not in name and not str(mob_id).startswith("2000028") and "2000028" not in name:
                    continue
                    
                mx = m.get('x', 0)
                my = m.get('y', 0)
                dist = math.sqrt((px - mx)**2 + (py - my)**2)
                if dist < min_dist:
                    min_dist = dist
                    nearest_uid = uid
                    
            if not nearest_uid:
                # No mobs found, wait
                time.sleep(1.0)
                continue
                
            # 3. Target the nearest mob
            target = state.monsters.get(nearest_uid)
            if not target:
                continue
                
            mx = target.get('x', 0)
            my = target.get('y', 0)
            
            # Teleport onto mob to ensure skill hits
            state.player_x = mx
            state.player_y = my
            
            x_int = int(mx * 256)
            y_int = int(my * 256)
            x_hex = format(x_int & 0xFFFF, '04x')
            y_hex = format(y_int & 0xFFFF, '04x')
            
            coord_pkt = build_coord_packet(f"{x_hex}{y_hex}")
            hex_send(sock, coord_pkt, "RADAR TARGET")
            
            state.waiting_for_hit.clear()
            
            # 3.5 Check Holy Spike
            now = time.time()
            if now - last_holy_spike_time > 33: # 35s duration
                print(f"[*] Casting Holy Spike on {target.get('name', nearest_uid)}...")
                spike_hex = "1cd8"
                spike_cast = build_skill_cast_packet(spike_hex, nearest_uid)
                hex_send(sock, spike_cast, "HOLY SPIKE CAST")
                spike_exec = f"000a0141{spike_hex}0101{nearest_uid}"
                hex_send(sock, spike_exec, "HOLY SPIKE EXECUTE")
                last_holy_spike_time = now
                time.sleep(0.5) # small delay before nemesis
            
            # Nemesis Skill ID: 138f, Flag: 0101
            skill_hex = "138f"
            cast_pkt = build_skill_cast_packet(skill_hex, nearest_uid)
            hex_send(sock, cast_pkt, "SKILL CAST")
            
            execute_pkt = f"000a0141{skill_hex}0101{nearest_uid}"
            hex_send(sock, execute_pkt, "SKILL EXECUTE")
            
            state.target_uid = nearest_uid
            
            # Wait 1 second before next cast
            time.sleep(1.0)
            
    except Exception as e:
        print(f"[-] Auto-Nemesis Loop Error: {e}")
    finally:
        state.auto_nemesis_running = False
        print("\n==================================================")
        print(" [AUTO NEMESIS LOOP STOPPED]")
        print("==================================================")

