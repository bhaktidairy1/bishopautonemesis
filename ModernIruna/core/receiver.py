"""
receiver.py — Continuous packet receiver with opcode dispatch.

Runs as a daemon thread. Reads the TCP stream, parses packets
using the 4-byte length header + 2-byte opcode format, and 
dispatches to registered handler functions.
"""
import socket
import binascii

from core.game_state import state
from core.packets import (
    OP_MAP_SYNC, OP_MAP_SYNC_B505, OP_MOB_SPAWN, OP_ENTITY_DEATH, OP_HIT_CONFIRM,
    OP_INVENTORY, OP_ITEM_DROP, OP_INV_UPDATE, OP_MAP_READY, OP_MAP_DATA, OP_BOSS_SPAWN,
    OP_PET_ITEM_DROP, OP_MAP_ENTITIES, OP_ISLAND_LIST, OP_ISLAND_STALL
)
from core.map_teleport import get_map_name
from core.packet_helpers import write_log
from core.inventory import (
    handle_item_drop, handle_inventory_update, handle_full_inventory, handle_pet_item_drop,
)


# ════════════════════════════════════════════
#  OPCODE HANDLERS
# ════════════════════════════════════════════

def handle_map_sync_b503(payload: bytes):
    _handle_map_sync_internal(payload, success=True)

def handle_map_sync_b505(payload: bytes):
    _handle_map_sync_internal(payload, success=False)

def _handle_map_sync_internal(payload: bytes, success: bool):
    """
    Opcode 0xb503 or 0xb505 — Server forces a position sync.
    Parses map ID, X, Y from the payload and updates state.
    Clears existing monsters since we are in a new location.
    """
    try:
        previous_map = getattr(state, 'current_map_hex', None)
        
        raw_map = binascii.hexlify(payload[3:5]).decode()  # 2 bytes = 4 hex chars (e.g. "3e1c")
        raw_x = int.from_bytes(payload[5:9], "big")
        raw_y = int.from_bytes(payload[9:13], "big")
        
        if raw_x < 256:
            shifted_x = format((raw_x << 8) & 0xFFFF, '04x')
        else:
            shifted_x = format(raw_x & 0xFFFF, '04x')
            
        if raw_y < 256:
            shifted_y = format((raw_y << 8) & 0xFFFF, '04x')
        else:
            shifted_y = format(raw_y & 0xFFFF, '04x')

        state.current_map_hex = raw_map
        state.last_map_coords = shifted_x + shifted_y
        state.player_x = int(shifted_x, 16) / 256.0
        state.player_y = int(shifted_y, 16) / 256.0
        state.map_name = get_map_name(int(raw_map, 16))
        
        # Clear out old entities
        state.monsters.clear()
        state.target_uid = None
        
        # Signal any waiting teleport routine
        state.teleport_success = success
        state.teleport_event.set()
        
        status = "SUCCESS" if success else "REJECTED/OVERRIDE"
        print(f"\n[!] MAP SYNC ({status}): Map {raw_map} | Coords {shifted_x}{shifted_y}")
        
        # Auto-rejoin PT Area if we were kicked from it (000aae60 -> anything else via rejection)
        if not success and previous_map == "ae60" and raw_map != "ae60":
            print("[!] PT Area Instance Expired! Spawning background thread to auto-rejoin...")
            from core.pt_area import auto_rejoin_pt_area_thread
            from core.client import client
            import threading
            threading.Thread(target=auto_rejoin_pt_area_thread, args=(client.sock, True), daemon=True).start()
            
    except Exception as e:
        print(f"[!] Sync Parse Error: {e}")


def handle_mob_spawn(payload: bytes):
    """
    Opcode 0x0245 — Monster/NPC spawned or moved.
    Extracts UID, monster ID, and exact coordinates.
    Format: [uid(4)][speed/time(2)][start_x(2)][start_y(2)][end_x(2)][end_y(2)]
    """
    uid = binascii.hexlify(payload[0:4]).decode()
    
    # Check if this is a spawn blob sub-packet or a real movement packet
    if len(payload) >= 14:
        # Movement packet has start and end coords
        raw_x = int.from_bytes(payload[10:12], "big")
        raw_y = int.from_bytes(payload[12:14], "big")
    elif len(payload) >= 10:
        raw_x = int.from_bytes(payload[6:8], "big")
        raw_y = int.from_bytes(payload[8:10], "big")
    else:
        return # invalid length
        
    x = raw_x / 256.0
    y = raw_y / 256.0
    
    if uid in state.monsters:
        # Update existing mob, preserving flags like is_player
        state.monsters[uid]['x'] = x
        state.monsters[uid]['y'] = y
    else:
        # We don't have its base ID, but we know where it is
        state.monsters[uid] = {
            'id': 0, 'variant': 0, 'name': 'Unknown', 'x': x, 'y': y
        }
    
    # Catch boss spawns dynamically during sequences
    if state.in_scripted_sequence:
        # Zimov spawn is usually caught here
        state.boss_id_hex = uid
        state.boss_spawn_event.set()

def handle_map_entities(payload: bytes):
    """
    Opcode 0x0240 — Initial Entity Spawn Dump
    Contains a massive block of 16-byte entity structures.
    Format per entity: [UID(4)][BaseID(3)][Variant(1)][Unknown(4)][X(2)][Y(2)]
    """
    from core.mob_db import get_mob_name
    import math
    
    # Payload is 4 bytes prefix + array of 16-byte structs
    entity_data = payload[4:]
    for i in range(0, len(entity_data), 16):
        block = entity_data[i:i+16]
        if len(block) < 16:
            break
            
        uid = binascii.hexlify(block[0:4]).decode()
        full_id = int.from_bytes(block[4:8], "big")
        raw_x = int.from_bytes(block[12:14], "big")
        raw_y = int.from_bytes(block[14:16], "big")
        
        x = raw_x / 256.0
        y = raw_y / 256.0
        
        name = get_mob_name(full_id)
        
        if uid in state.monsters:
            if not state.monsters[uid].get('is_player', False):
                state.monsters[uid]['id'] = full_id
                state.monsters[uid]['name'] = name
            state.monsters[uid]['x'] = x
            state.monsters[uid]['y'] = y
        else:
            state.monsters[uid] = {
                'id': full_id,
                'name': name,
                'x': x,
                'y': y
            }
        print(f"[+] Radar tracked: {state.monsters[uid]['name']} ({uid}) at ({x:.1f}, {y:.1f})")
def handle_0248_entity_def(payload: bytes):
    """
    Opcode 0x0248 - New Entity Definition.
    Format: [UID(4)][BaseID(4)][Unknown(4)]
    The server sends this to tell the client what kind of mob a new UID is,
    right before sending the 0245 spawn packet to place it.
    """
    if len(payload) >= 8:
        uid = binascii.hexlify(payload[0:4]).decode()
        full_id = int.from_bytes(payload[4:8], "big")
        
        from core.mob_db import get_mob_name
        name = get_mob_name(full_id)
        
        # If it doesn't exist yet, seed it with dummy coords. 
        # The 0245 packet will arrive immediately after to give it real coords.
        if uid not in state.monsters:
            state.monsters[uid] = {
                'id': full_id,
                'name': name,
                'x': 0.0,
                'y': 0.0
            }
        else:
            # Only update if it's not already tracked as a player
            if not state.monsters[uid].get('is_player', False):
                state.monsters[uid]['id'] = full_id
                state.monsters[uid]['name'] = name
            
        print(f"[+] Entity Defined: {name} ({uid})")


def handle_entity_death(payload: bytes):
    """
    Opcode 0x0244 — Entity died/despawned.
    Removes from monster tracker. Clears target if it was our target.
    """
    uid = binascii.hexlify(payload[0:4]).decode()
    if uid in state.monsters:
        mob_name = state.monsters[uid]['name']
        print(f"[-] {mob_name} ({uid}) died. Removing from radar.")
        del state.monsters[uid]
        
    if state.target_uid == uid:
        state.target_uid = None
        
    if state.in_scripted_sequence and uid == state.boss_id_hex:
        state.boss_death_event.set()


def handle_hit_confirm(payload: bytes):
    """
    Opcode 0x0241 — Attack hit confirmed by server.
    Signals the combat engine to continue the attack cycle.
    """
    state.waiting_for_hit.set()


def handle_0142_skill_result(payload: bytes):
    """
    Opcode 0x0142 — Skill/Magic damage or heal result.
    Structure: [Skill(2)][Flag(1)][Caster(4)][NumTargets(4)]
    For each target: [TypeFlag(1)][Target(4)][Amount(4)]
    """
    if len(payload) >= 11:
        skill_id = binascii.hexlify(payload[0:2]).decode()
        caster = binascii.hexlify(payload[3:7]).decode()
        num_targets = int.from_bytes(payload[7:11], "big")
        
        offset = 11
        for _ in range(num_targets):
            if offset + 9 > len(payload):
                break
            
            type_flag = payload[offset]
            target = binascii.hexlify(payload[offset+1:offset+5]).decode()
            amount = int.from_bytes(payload[offset+5:offset+9], "big")
            
            # Print if it's a monster taking damage AND we are the caster
            if caster == state.char_id_hex and target in state.monsters and type_flag == 0x01:
                mob_name = state.monsters[target]['name']
                print(f"[*] SKILL {skill_id} hit {mob_name} for {amount} damage!")
            
            offset += 9
            
        # Signal that a skill has finished executing
        if caster == state.char_id_hex:
            state.skill_cast_event.set()
            if skill_id == "138f":
                state.skill_exec_confirm_event.set()

def handle_0143_skill_cast(payload: bytes):
    """
    Opcode 0x0143 — Skill Cast (Start or Confirm).
    When the server confirms our cast, it sends a 3-byte packet: 00000003014300.
    The payload is just a single byte: 0x00.
    If the cast was cancelled (e.g. target died), the payload is 0xff.
    """
    if len(payload) == 1:
        if payload[0] == 0x00:
            # Cast confirmed!
            state.skill_cast_confirm_event.set()
        elif payload[0] == 0xff:
            # Cast rejected / interrupted
            state.skill_failed = True
            state.skill_cast_confirm_event.set()
    elif len(payload) >= 3:
        # Some other players casting something around us, not relevant to our confirm wait
        pass

def handle_0141_skill_exec(payload: bytes):
    """
    Opcode 0x0141 — Skill Execute.
    Normally sent by client to execute damage, but server sends it with 0xff payload
    if the execution failed (e.g. target died during cast).
    """
    if len(payload) == 1 and payload[0] == 0xff:
        state.skill_failed = True
        state.skill_exec_confirm_event.set()


def handle_0132_exp(payload: bytes):
    """
    Opcode 0x0132 — Experience gained.
    Structure: [Timestamp/Seq(4)][Player(4)][Mob(4)][Exp(4)][Unk(1)]
    """
    if len(payload) >= 16:
        player_uid = binascii.hexlify(payload[4:8]).decode()
        mob_uid = binascii.hexlify(payload[8:12]).decode()
        exp = int.from_bytes(payload[12:16], "big")
        
        # Only print our EXP
        if player_uid == state.char_id_hex:
            mob_name = "Monster"
            if mob_uid in state.monsters:
                mob_name = state.monsters[mob_uid]['name']
                
            print(f"[*] Earned {exp} EXP from {mob_name}!")

def handle_0246_skill_ready(payload: bytes):
    """
    Opcode 0x0246 — Server resolves skill target and spawns an AoE/Projectile entity.
    Payload: [OriginalTarget(4)][NewTarget(4)][Caster(4)]
    """
    if len(payload) >= 12:
        original_target = binascii.hexlify(payload[0:4]).decode()
        new_target = binascii.hexlify(payload[4:8]).decode()
        caster = binascii.hexlify(payload[8:12]).decode()
        
        # In Iruna, when a skill hits a monster, the server permanently re-assigns
        # the monster's UID to the newly generated entity UID for the rest of its lifespan!
        if original_target in state.monsters:
            state.monsters[new_target] = state.monsters.pop(original_target)
            # We don't need to print this spam, but it updates the internal state.
            
        # If we cast the skill, lock our target onto the new UID!
        if caster == state.char_id_hex:
            if state.target_uid == original_target:
                state.target_uid = new_target
                print(f"[*] Target locked onto new entity ID: {new_target}")

def handle_0111_revive_warp(payload: bytes):
    """
    Opcode 0x0111 — Server provides the respawn warp destination (after death/revive).
    Payload: [MapID(4)][X(2)][Y(2)]
    The client must echo this back as 0110 (WARP_REQ) to initiate the map change.
    """
    if state.is_island_mode:
        print("[*] Ignored 0111 revive packet in Island mode.")
        return

    from core.packet_helpers import hex_send
    from core.client import client
    
    if len(payload) >= 8:
        map_hex = binascii.hexlify(payload[0:4]).decode()
        x_hex = binascii.hexlify(payload[4:6]).decode()
        y_hex = binascii.hexlify(payload[6:8]).decode()
        
        # Build 0110 WARP_REQ: [MapID(4)] [0000(2) + X(2)] [0000(2) + Y(2)]
        # X and Y are provided as 2 bytes in 0111, but need to be 4 bytes in 0110
        warp_payload = f"{map_hex}0000{x_hex}0000{y_hex}"
        
        # Length of payload = 12 bytes. Total length = 14 bytes (0x000e)
        warp_pkt = f"000e0110{warp_payload}"
        
        print(f"[*] Revive triggered! Warping to respawn point (Map {map_hex})...")
        hex_send(client.sock, warp_pkt, "WARP_REQ (REVIVE)")
        
        # Clear target and stop attacks
        state.target_uid = None
        state.player_hp = 1 # temporary so we aren't dead while map syncing


def handle_map_ready(payload: bytes):
    """
    Opcode 0x0138 — Server is ready for Map Sync (013a).
    """
    state.map_ready_event.set()

def handle_map_data(payload: bytes):
    """
    Opcode 0x3003 — Final Map Sync ACK from Server.
    """
    state.map_data_event.set()

def handle_0131_hp_mp(payload: bytes):
    if len(payload) >= 12:
        new_hp = int.from_bytes(payload[4:8], "big")
        new_mp = int.from_bytes(payload[8:12], "big")
        
        # 0131 sends CURRENT HP/MP.
        state.player_hp = new_hp
        state.player_mp = new_mp
        
        # Dynamically track max HP/MP
        if new_hp > state.player_max_hp:
            state.player_max_hp = new_hp
        if new_mp > state.player_max_mp:
            state.player_max_mp = new_mp

def handle_0130_char_stats(payload: bytes):
    """
    Opcode 0x0130 — Initial Character Stats Sync.
    Sent when joining a map or logging in. Contains Spina, Max HP, and Max MP.
    The packet structure has variable length boolean flags, but we can reliably
    find the data by searching backward from the character name string length.
    Structure: [Spina:4b][MaxHP:4b][MaxMP:4b][NameLen:2b][Name:NameLen b]00
    """
    import re
    data_hex = binascii.hexlify(payload).decode()
    try:
        matches = re.finditer(r'([0-9a-f]{8})([0-9a-f]{8})([0-9a-f]{8})([0-9a-f]{4})', data_hex)
        for m in matches:
            spina_hex, hp_hex, mp_hex, namelen_hex = m.groups()
            max_hp = int(hp_hex, 16)
            max_mp = int(mp_hex, 16)
            name_len = int(namelen_hex, 16)
            
            # Name length usually 2 to 32 chars. Max HP/MP sanity checks.
            if 0 < max_hp < 500000 and 0 < max_mp < 100000 and 2 <= name_len <= 32:
                end_idx = m.end() + (name_len * 2)
                # Check if the string is followed by a 00 byte
                if end_idx + 2 <= len(data_hex) and data_hex[end_idx:end_idx+2] == '00':
                    spina = int(spina_hex, 16)
                    state.player_max_hp = max_hp
                    state.player_max_mp = max_mp
                    state.player_spina = spina
                    
                    if state.player_hp <= 1:
                        state.player_hp = max_hp
                    if state.player_mp <= 1:
                        state.player_mp = max_mp
                        
                    print(f"[*] Login Stats Loaded: Spina: {spina:,} | HP {state.player_hp}/{max_hp} | MP {state.player_mp}/{max_mp}")
                    return
    except Exception as e:
        print(f"[-] Failed to parse 0130 stats in receiver: {e}")

def handle_0242_attack(payload: bytes):
    """
    Opcode 0x0242 — Entity Physical Attack.
    Format: [Attacker(4)][Damage(4)][Flag(1)][Target(4)][AttackerHP(4)][TargetHP(4)]
    """
    if len(payload) >= 21:
        attacker = binascii.hexlify(payload[0:4]).decode()
        # Damage can sometimes contain flags in the highest byte (e.g., 0x01000000 for miss/evade)
        raw_damage = int.from_bytes(payload[4:8], "big")
        damage = raw_damage & 0x00FFFFFF
        # payload[8] is a flag byte
        target = binascii.hexlify(payload[9:13]).decode()
        # attacker_hp = int.from_bytes(payload[13:17], "big")
        current_hp = int.from_bytes(payload[17:21], "big")
        
        if target == state.char_id_hex:
            state.player_hp = current_hp
            mob_name = "Monster"
            if attacker in state.monsters:
                mob_name = state.monsters[attacker]['name']
            print(f"[*] {mob_name} hit us for {damage} damage! HP: {state.player_hp}")

# ════════════════════════════════════════════
#  PARTY PACKET HANDLERS
# ════════════════════════════════════════════

def handle_player_update(payload: bytes):
    """
    Opcode 0x0201 — Player appearance / update (coords).
    Format: [Unknown(4)][UID(4)][X(2)][Y(2)]...
    """
    if len(payload) >= 12:
        player_uid = binascii.hexlify(payload[4:8]).decode()
        raw_x = int.from_bytes(payload[8:10], "big")
        raw_y = int.from_bytes(payload[10:12], "big")
        
        x = raw_x / 256.0
        y = raw_y / 256.0
        
        if player_uid not in state.monsters:
            state.monsters[player_uid] = {
                'id': 0,
                'name': 'Player',
                'x': x,
                'y': y,
                'is_player': True
            }
        else:
            state.monsters[player_uid]['x'] = x
            state.monsters[player_uid]['y'] = y
            state.monsters[player_uid]['is_player'] = True # Ensure this stays True
        
def handle_party_invite(payload: bytes):
    """
    Opcode 0x2008 — Party invite received!
    Format: [Inviter_UID(4)]
    """
    if len(payload) >= 4:
        inviter_uid = binascii.hexlify(payload[0:4]).decode()
        state.pending_party_invite = inviter_uid
        print(f"[+] Party Invite received from UID: {inviter_uid}")
        
def handle_player_info(payload: bytes):
    """
    Opcode 0x0202 — Player Info (Name, etc.)
    Format: [UID(4)][NameLen(2)][Name...]
    Also used for party member info / health update.
    """
    if len(payload) >= 6:
        member_uid = binascii.hexlify(payload[0:4]).decode()
        name_len = int.from_bytes(payload[4:6], "big")
        
        # If we have the name bytes
        if len(payload) >= 6 + name_len:
            name_bytes = payload[6:6+name_len]
            # Some names are null-terminated or have weird bytes, so decode safely
            name = name_bytes.decode('utf-8', errors='ignore').replace('\x00', '')
            
            # The server sends 0202 for players immediately.
            # If they are already in the monster list, update them.
            if member_uid in state.monsters:
                state.monsters[member_uid]['name'] = name
                state.monsters[member_uid]['is_player'] = True
                print(f"[+] Radar tracked Player: {name} ({member_uid})")
            else:
                # Add them anyway so they show up. We might receive their coords later.
                state.monsters[member_uid] = {
                    'id': 0,
                    'name': name,
                    'x': state.player_x, # Default to near us temporarily
                    'y': state.player_y,
                    'is_player': True
                }
                print(f"[+] Radar added Player (No Coords Yet): {name} ({member_uid})")
        
        state.party_update_event.set()

def handle_party_disband(payload: bytes):
    """
    Opcode 0x2012 — Party disbanded or left.
    """
    state.party_members.clear()
    state.pending_party_invite = None
    print("[-] Party disbanded / left.")
    state.party_update_event.set()


def handle_island_stall(payload: bytes):
    """
    Parses the 2410 shop response and prints the items.
    """
    try:
        from core.island import parse_stall_data
        # We need to pass the raw hex with length because parse_stall_data expects the full dump format currently
        # Wait, the payload is just the bytes after the length+opcode.
        # Let's adjust island.py to parse directly from the payload instead.
        import binascii
        items = parse_stall_data(binascii.hexlify(payload).decode())
        if items:
            state.stall_items = items
            print(f"[*] Fetched Stall! Found {len(items)} items.")
            for it in items:
                print(f"    - [{it['item_id']}] {it['name']} : {it['price']} Spina")
    except Exception as e:
        print(f"[-] Error in handle_island_stall: {e}")

def handle_island_list(payload: bytes):
    """
    Parses the a008 island list response and stores it in state.
    """
    try:
        from core.island import parse_island_data
        import binascii
        items = parse_island_data(binascii.hexlify(payload).decode())
        if items:
            state.island_list = items
            print(f"[*] Fetched Island List! Found {len(items)} islands.")
    except Exception as e:
        print(f"[-] Error in handle_island_list: {e}")

def handle_pta_status(payload: bytes):
    """
    Opcode 0xb502 — PT Area Status Response
    """
    try:
        import binascii
        hex_data = binascii.hexlify(payload).decode()
        if hex_data.startswith("0000000000000000"):
            state.pta_active = False
            state.pta_time_remaining = 0
            print("[-] PT Area Status: INACTIVE")
        else:
            state.pta_active = True
            time_remaining_ds = int(hex_data[8:16], 16)
            import time
            state.pta_time_remaining = time_remaining_ds / 10.0
            state.pta_time_last_updated = time.time()
            
            mins = int(state.pta_time_remaining // 60)
            secs = int(state.pta_time_remaining % 60)
            print(f"[+] PT Area Status: ACTIVE | Time remaining: {mins}m {secs}s")
    except Exception as e:
        print(f"[-] Error parsing PTA status: {e}")

# ════════════════════════════════════════════
#  HANDLER REGISTRY
# ════════════════════════════════════════════
# Add new opcode handlers here — no need to touch the receiver loop.

HANDLERS = {
    0xffff: lambda p: state.check_alive_event.set(),
    0x0201: handle_player_update,
    0x0202: handle_player_info,
    0x2008: handle_party_invite,
    0x2012: handle_party_disband,
    0x0111: handle_0111_revive_warp,
    0x0130: handle_0130_char_stats,
    0x0131: handle_0131_hp_mp,
    0x0132: handle_0132_exp,
    0x0141: handle_0141_skill_exec,
    0x0142: handle_0142_skill_result,
    0x0143: handle_0143_skill_cast,
    0x0242: handle_0242_attack,
    0x0244: handle_entity_death,
    0x0246: handle_0246_skill_ready,
    0x0248: handle_0248_entity_def,
    0xb502: handle_pta_status,
    OP_MAP_SYNC:        handle_map_sync_b503,
    OP_MAP_SYNC_B505:   handle_map_sync_b505,
    OP_MOB_SPAWN:       handle_mob_spawn,
    OP_MAP_ENTITIES:    handle_map_entities,
    OP_HIT_CONFIRM:     handle_hit_confirm,
    OP_INVENTORY:       handle_full_inventory,
    OP_ITEM_DROP:       handle_item_drop,
    OP_INV_UPDATE:      handle_inventory_update,
    OP_PET_ITEM_DROP:   handle_pet_item_drop,
    OP_MAP_READY:       handle_map_ready,
    OP_MAP_DATA:        handle_map_data,
    OP_ISLAND_STALL:    handle_island_stall,
    OP_ISLAND_LIST:     handle_island_list,
}


# ════════════════════════════════════════════
#  RECEIVER THREAD
# ════════════════════════════════════════════

def continuous_receiver(sock: socket.socket):
    """
    Buffer-based packet reader. Runs in a daemon thread.
    
    Protocol format:
      [4-byte length] [2-byte opcode] [payload...]
      Total packet size = length + 4
      
    Dispatches recognized opcodes to HANDLERS dict.
    Logs all packets for debugging.
    """
    buffer = b""
    print("[*] Receiver Thread: Online and Listening...")
    
    while not state.stop_event.is_set():
        try:
            data = sock.recv(4096)
            if not data:
                print("\n[!!!] SERVER DISCONNECTED")
                try:
                    from core.packet_helpers import upload_to_discord
                    upload_to_discord()
                except: pass
                break
            
            buffer += data
            
            while len(buffer) >= 6:
                pkt_len = int.from_bytes(buffer[0:4], "big")
                opcode = int.from_bytes(buffer[4:6], "big")
                total_pkt_size = pkt_len + 4
                
                # Safety: skip junk length headers
                if pkt_len > 10000 or pkt_len == 0:
                    buffer = buffer[1:]
                    continue
                
                # Wait for full packet
                if len(buffer) < total_pkt_size:
                    break
                
                raw_packet = buffer[:total_pkt_size]
                payload = buffer[6:total_pkt_size]
                
                # Log every packet (console + file)
                opcode_hex = hex(opcode)
                log_line = f"<- [RECV] {opcode_hex} | {binascii.hexlify(raw_packet).decode()}"
                print(log_line)
                write_log(log_line)
                
                # Dispatch to handler if registered
                handler = HANDLERS.get(opcode)
                if handler:
                    handler(payload)
                
                buffer = buffer[total_pkt_size:]
                
        except socket.timeout:
            print("\n[!!!] NO SERVER RESPONSE FOR 5 SECONDS. CONNECTION DEAD. EXITING.")
            try:
                from core.packet_helpers import upload_to_discord
                upload_to_discord()
            except: pass
            import os
            os._exit(1)
        except Exception as e:
            print(f"[CRITICAL] Error in receiver: {e}")
            try:
                from core.packet_helpers import upload_to_discord
                upload_to_discord()
            except: pass
            break
    
    print("[*] Receiver Thread: Offline.")
