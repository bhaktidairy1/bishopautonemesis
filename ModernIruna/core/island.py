import binascii
import time
from core.packet_helpers import hex_send, hex_recv
from core.game_state import state
from core.inventory import get_item_name

def get_island_list(sock):
    """
    Sends the 0005a008010001 packet to get the list of available islands.
    """
    print("[*] Requesting island list...")
    hex_send(sock, "0005a008010001", "ISLAND LIST REQ")

def enter_island(sock, island_id_hex):
    """
    Sends the a000 packet to enter an island.
    """
    if len(island_id_hex) < 8:
        island_id_hex = island_id_hex.zfill(8)
    print(f"[*] Entering island {island_id_hex}...")
    hex_send(sock, f"000aa00000{island_id_hex}00020000", "ISLAND ENTER")
    state.in_island_map = True

def browse_stall(sock, target_char_id, stall_uid):
    """
    Browses a stall/shop inside an island.
    """
    print(f"[*] Browsing stall {stall_uid} for owner {target_char_id}...")
    hex_send(sock, f"000a241000{target_char_id}01{stall_uid}", "BROWSE STALL")


def parse_stall_data(payload_hex):
    """
    Parses the 2410 shop response payload (excluding length & opcode).
    """
    try:
        b = bytes.fromhex(payload_hex)
        # payload_hex structure: 00 01 00 00 00 09 00 64 ...
        
        # If the first two bytes are an index/flag, skip to count
        # In dump 1: 00 02 00 00 00 0a 00 c8
        # In dump 2: 00 01 00 00 00 09 00 64
        # Count is at index 4-6
        count = int.from_bytes(b[4:6], "big")
        b = b[8:] # skip header
        
        if count == 0 or len(b) == 0:
            return []
            
        if len(b) % count != 0:
            print(f"[-] Warning: {len(b)} bytes is not evenly divisible by {count}")
            return []
            
        chunk_size = len(b) // count
        items = []
        
        idx = 0
        for i in range(count):
            chunk = b[idx:idx+chunk_size]
            item_id = int.from_bytes(chunk[2:4], "big")
            name = get_item_name(item_id)
            
            # Simple heuristic: last 4 bytes before slot index might contain price
            price = int.from_bytes(chunk[-6:-2], "big")
            
            items.append({
                "item_id": item_id,
                "name": name,
                "price": price,
                "raw_hex": chunk.hex()
            })
            idx += chunk_size
            
        return items
    except Exception as e:
        print(f"[-] Failed to parse stall data: {e}")
        return []

def parse_island_data(payload_hex):
    """
    Parses OP_ISLAND_LIST response.
    """
    try:
        payload = bytes.fromhex(payload_hex)
        if len(payload) < 8: return []
        
        count = int.from_bytes(payload[4:8], "big")
        offset = 8
        islands = []
        
        for i in range(count):
            if offset + 10 > len(payload): break
            char_id = payload[offset:offset+4].hex()
            unk_id = payload[offset+4:offset+8].hex()
            name_len = int.from_bytes(payload[offset+8:offset+10], "big")
            offset += 10
            
            if offset + name_len > len(payload): break
            name = payload[offset:offset+name_len].decode('utf-8', 'ignore')
            offset += name_len
            
            islands.append({"char_id": char_id, "name": name})
            
            # Heuristic: skip 10 bytes after the name to align to the next ID
            offset += 10
            
        return islands
    except Exception as e:
        print(f"[-] Failed to parse island list: {e}")
        return []
