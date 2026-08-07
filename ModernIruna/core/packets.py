"""
packets.py — Opcode constants and packet construction helpers.

All known Iruna opcodes and reusable packet builders live here.
When you discover new opcodes, add them to this file.
"""
import binascii

# ════════════════════════════════════════════
#  RECEIVE OPCODES (server → client)
# ════════════════════════════════════════════
OP_MAP_SYNC      = 0xb503   # Position auto-sync from server
OP_MAP_SYNC_B505 = 0xb505   # Alternate position sync (used in teleport)
OP_MOB_SPAWN     = 0x0245   # Monster/NPC appears
OP_ENTITY_DEATH  = 0x0244   # Entity removed (death/despawn)
OP_HIT_CONFIRM   = 0x0241   # Attack landed confirmation
OP_MAP_ENTITIES  = 0x0240   # Initial entities spawn dump
OP_INVENTORY     = 0x0120   # Full inventory dump
OP_ITEM_DROP     = 0x0123   # Item received (drop / reward)
OP_INV_UPDATE    = 0x4018   # Inventory slot changed
OP_PET_ITEM_DROP = 0xa108
OP_BOSS_SPAWN    = 0x0248   # Boss/special entity spawn
OP_DMG_RESULT    = 0x0142   # Skill damage result
OP_EXP_REWARD    = 0x0132   # Experience gained
OP_BOSS_DEFEAT   = 0x0249   # Boss defeated / reward trigger
OP_MAP_READY     = 0x0138   # Map ready for sync
OP_MAP_DATA      = 0x3003   # Map data (weather, BGM, final ack)
OP_CHAR_STATS    = 0x0130   # Initial character stats sync

# ════════════════════════════════════════════
#  SEND OPCODES / PACKET PREFIXES (client → server)
# ════════════════════════════════════════════
PKT_INIT           = "0002fff3"
PKT_CHAR_SELECT    = "0002f032"
PKT_NEW_CHAR_SEL   = "00020003"
PKT_ENTER_WORLD    = "00080002"  # Followed by char_id_hex + 0000
PKT_POST_MAP       = "000623f3"
PKT_MOVEMENT_STEPS = ["00023300", "00023303"]
PKT_MOVEMENT_READY = "00026002"
PKT_PRESENCE_START = "001bb300"
PKT_MAP_SYNC_BEGIN = "0002013a"
PKT_MAGIC_BUNDLE   = ["0003020700", "0002013a", "00023209", "0006011300000000", "00020160", "00028100", "00028110", "00028300", "00028200", "0003840400"]
PKT_BULK_HEADER    = "000f3002"
PKT_WORLD_TICKS    = "00025003"
PKT_SUMMON_PET     = "0006a102"
PKT_COORD_PREFIX   = "00060101"
PKT_ATTACK_PREFIX  = "000a0241"
PKT_INVENTORY_REQ  = "00020120"   # Fetch full inventory (send ONCE)

# Warp sequence
PKT_WARP_SYNC_START = "0003300601"
PKT_WARP_SYNC_END   = "0003300600"

# Padding constants
# Presence/world-ticks packets: length 0x001b = 27, minus 2 for opcode b300 = 25 data bytes
PRESENCE_ZEROS = "00" * 25


# ════════════════════════════════════════════
#  ISLAND OPCODES
# ════════════════════════════════════════════
OP_ISLAND_LIST   = 0xa008
OP_ISLAND_ENTER  = 0xa000
OP_ISLAND_STALL  = 0x2410

# ════════════════════════════════════════════
#  PACKET BUILDERS
# ════════════════════════════════════════════

def build_island_login_packet(token_hex: str, email: str) -> bytes:
    """Builds the FF02 login packet for the Island server (port 30009)."""
    email_hex = email.encode('ascii').hex()
    email_len = f"{len(email_hex)//2:04x}"
    payload = f"ff020020{token_hex}{email_len}{email_hex}"
    
    # Total packet length includes the 4-byte header!
    # If payload is N bytes, header says N+4 bytes. (Unlike normal login which uses 2-byte header?)
    # Wait, the user's dump showed C->S: 003c ff02...
    # 003c is 60 bytes total length.
    # ff02 (2) + 0020 (2) + token (32) + email_len (2) + email (?)
    # Let's count the user's hex dump:
    # 003c (60)
    # ff020020 (4)
    # 3939623164633266323165376338623963346236353439626466383035666631 (32)
    # 0016 (2) -> length of email string
    # 6b69747a67616d696e67323440676d61696c2e636f6d (22)
    # Total = 4 + 32 + 2 + 22 = 60. So length header is 003c.
    # Therefore, the length header is just 2 bytes, denoting the size of the *entire packet* (including the 2 byte header).
    # Wait, 2 + 60 = 62?
    # No, the length header itself is 2 bytes (003c = 60).
    # And the payload bytes are: 4 + 32 + 2 + 22 = 60 bytes.
    # Wait, the length header specifies the length of the *entire packet* including the 2 bytes of the header?
    # No, let's look at the old login packet builder:
    # return len(payload).to_bytes(2, "big") + payload -> this means the 2 bytes specify the length of the payload only!
    # Wait, if payload is 60 bytes, len(payload) is 60. Then 003c is 60.
    # Ah! The user's dump had 003eff02 in the broken log, because I calculated the length manually as `len(payload)//2 + 2`
    
    raw_payload = bytes.fromhex(payload)
    return len(raw_payload).to_bytes(2, "big") + raw_payload
# ════════════════════════════════════════════

def build_login_packet(token_hex: str) -> bytes:
    """
    Build the dynamic-length login packet:
    [2-byte length][FF02][0020<token>0000]
    """
    token_with_prefix = "0020" + token_hex + "0000"
    raw_token = binascii.unhexlify(token_with_prefix)
    payload = b"\xFF\x02" + raw_token
    return len(payload).to_bytes(2, "big") + payload


def build_attack_packet(target_uid: str) -> str:
    """Build attack hex string: 000a0241 + <uid> + 00000001"""
    return PKT_ATTACK_PREFIX + target_uid + "00000001"

def build_skill_cast_packet(skill_id_hex: str, target_uid: str) -> str:
    """
    Build skill cast packet (0143).
    Example for Nemesis (138f): 000a0143138f0101 + target_uid
    Example for Bright Heal (1c36): 000a01431c360001 + target_uid
    """
    if skill_id_hex == "138f": # Nemesis (AoE)
        return f"000a0143{skill_id_hex}0101{target_uid}"
    elif skill_id_hex == "1c36": # Bright Heal (Targeted/Self)
        return f"000a0143{skill_id_hex}0001{target_uid}"
    else:
        return f"000a0143{skill_id_hex}0001{target_uid}"

def build_coord_packet(coords: str) -> str:
    """Build coordinate heartbeat: 00060101 + <4-byte coords>"""
    return PKT_COORD_PREFIX + coords


def build_map_data_packet(map_hex: str, x: str, y: str) -> str:
    """
    Build map position packet for world entry:
    000e01100000<map_2byte>0000<x_2byte>0000<y_2byte>
    Length 000e = 14 bytes payload
    """
    map_padded = map_hex.zfill(8)
    x_padded = x.zfill(8)
    y_padded = y.zfill(8)
    return f"000e0110{map_padded}{x_padded}{y_padded}"


def build_bulk_data_packet(map_hex: str) -> str:
    """Build bulk action data with current map reference."""
    map_padded = map_hex.zfill(8)
    return f"110000000000000000{map_padded}"


def build_warp_exit_packet(portal_id: str, current_map: str) -> str:
    """3002 EXIT packet for leaving current map."""
    map_padded = current_map.zfill(8)
    return f"000f300211000000{portal_id.zfill(2)}00000000{map_padded}"


def build_warp_position_packet(target_map: str, x: str, y: str) -> str:
    """110 POSITION packet for warp destination."""
    map_padded = target_map.zfill(8)
    x_padded = x.zfill(8)
    y_padded = y.zfill(8)
    return f"000e0110{map_padded}{x_padded}{y_padded}"


def build_warp_entry_packet(target_map: str) -> str:
    """3002 ENTRY packet for arriving at new map."""
    map_padded = target_map.zfill(8)
    return f"000f3002110000000000000000{map_padded}"


def build_world_ticks_packet() -> str:
    """Presence/world ticks packet: 001bb300 + 25 zero bytes (total 29 bytes)."""
    return PKT_PRESENCE_START + PRESENCE_ZEROS


# ════════════════════════════════════════════
#  PARTY PACKETS
# ════════════════════════════════════════════

def build_party_invite_packet(target_uid_hex: str) -> str:
    """Send a party invite to another player (Opcode 2007)."""
    # 0006 2007 target_uid
    return f"00062007{target_uid_hex}"

def build_party_accept_packet(inviter_uid_hex: str) -> str:
    """Accept a pending party invite (Opcode 2002)."""
    # 0006 2002 inviter_uid
    return f"00062002{inviter_uid_hex}"

def build_party_leave_packet() -> str:
    """Leave or disband the current party (Opcode 2005)."""
    return "00022005"

