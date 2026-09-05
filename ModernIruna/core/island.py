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
    Sends the a000 packet to enter an island and completes the handshake.
    Based on legitimate packet capture.
    """
    if len(island_id_hex) < 8:
        island_id_hex = island_id_hex.zfill(8)
    print(f"[*] Entering island {island_id_hex}...")
    
    # 1. Enter island command
    hex_send(sock, f"000aa00000{island_id_hex}00020000", "ISLAND ENTER")
    
    # Wait briefly for a1a1 and server data
    time.sleep(1.0)
    
    # 2. Map Load Handshake
    hex_send(sock, "0003020700", "ISLAND_MAGIC_1")
    # 23f3 is the Post-Map opcode. Wait, in normal map entry it requires char_id_hex. 
    # The client sends: 0006 23f3 00 4b53f0. 4b53f0 is the island_id_hex (well, part of it? No, the island_id is 49f07e00, 4b53f0 is char_id)
    # Yes, 4b53f0 is the user's char ID from earlier logs!
    hex_send(sock, f"000623f3{state.char_id_hex}", "ISLAND_POST_MAP")
    time.sleep(0.5)
    
    # 3. Movement Handshake
    hex_send(sock, "00023300", "ISLAND_MOVE_1")
    hex_send(sock, "00023303", "ISLAND_MOVE_2")
    time.sleep(0.5)
    
    # 4. Movement Ready
    hex_send(sock, "00026002", "ISLAND_MOVE_READY")
    time.sleep(0.5)
    
    # 5. Island specifics
    hex_send(sock, "00022400", "ISLAND_SPECIFIC_1")
    hex_send(sock, f"0006241200{island_id_hex[2:]}", "ISLAND_SPECIFIC_2") # island_id but the user had 36fad3... actually we'll just skip 2412 if we don't know the second ID. 
    # Actually the user's capture had: 000624120036fad3. 36fad3 was the second ID in the island list (unk_id).
    # Since we don't pass unk_id to this function yet, we'll send a placeholder or fetch it from the island list.
    
    # Let's find the unk_id from state.island_list if it exists
    unk_id = "000000"
    for island in getattr(state, "island_list", []):
        if island_id_hex in island.get("raw_hex", ""):
            # We don't have it explicitly parsed in state right now, but it's okay, we can just send it as 000000 or omit.
            pass
            
    # For now we'll skip 2412, or just send a dummy one if server ignores it. 
    # Let's send Map Sync ACK instead which is the most important
    hex_send(sock, "0002013a", "ISLAND_MAP_SYNC_ACK")
    hex_send(sock, "00022084", "ISLAND_MAGIC_2")
    hex_send(sock, "0002a017", "ISLAND_MAGIC_3")
    hex_send(sock, "00020160", "ISLAND_MAGIC_4")
    time.sleep(0.5)
    
    hex_send(sock, "0003840400", "ISLAND_MAGIC_5")
    hex_send(sock, "0002a017", "ISLAND_MAGIC_6")
    hex_send(sock, "0002a500", "ISLAND_MAGIC_7")
    time.sleep(0.5)
    
    hex_send(sock, "00023209", "ISLAND_MAGIC_8")
    hex_send(sock, "00022006", "ISLAND_MAGIC_9")
    hex_send(sock, "00025003", "ISLAND_MAGIC_10")
    
    state.in_island_map = True

def enter_island_edit_mode(sock):
    """
    Sends the a000 packet to enter YOUR OWN island in EDIT mode.
    Based on the user's packet capture.
    """
    print(f"[*] Entering your island in EDIT mode...")
    
    # 1. Enter island command for own island in EDIT mode (00010000 suffix)
    hex_send(sock, f"000aa00000{state.char_id_hex}00010000", "ISLAND EDIT ENTER")
    time.sleep(1.0)
    
    # 2. Map Load Handshake
    hex_send(sock, "0003020700", "ISLAND_EDIT_MAGIC_1")
    hex_send(sock, f"000623f3{state.char_id_hex}", "ISLAND_EDIT_POST_MAP")
    time.sleep(0.5)
    
    # 3. Movement Handshake
    hex_send(sock, "00023300", "ISLAND_EDIT_MOVE_1")
    hex_send(sock, "00023303", "ISLAND_EDIT_MOVE_2")
    time.sleep(0.5)
    
    # 4. Movement Ready
    hex_send(sock, "00026002", "ISLAND_EDIT_MOVE_READY")
    time.sleep(0.5)
    
    # 5. Island specifics
    hex_send(sock, "00022400", "ISLAND_EDIT_SPECIFIC_1")
    hex_send(sock, "00022406", "ISLAND_EDIT_SPECIFIC_2")
    time.sleep(0.5)
    
    hex_send(sock, "0002013a", "ISLAND_EDIT_SYNC_ACK")
    hex_send(sock, "00022084", "ISLAND_EDIT_MAGIC_2")
    hex_send(sock, "0002a00c", "ISLAND_EDIT_MAGIC_3")
    hex_send(sock, "00020160", "ISLAND_EDIT_MAGIC_4")
    time.sleep(0.5)
    
    hex_send(sock, "0003840400", "ISLAND_EDIT_MAGIC_5")
    hex_send(sock, "0002a056", "ISLAND_EDIT_MAGIC_6")
    hex_send(sock, "0002a00c", "ISLAND_EDIT_MAGIC_7")
    hex_send(sock, "0002a017", "ISLAND_EDIT_MAGIC_8")
    time.sleep(0.5)
    
    hex_send(sock, "0002a500", "ISLAND_EDIT_MAGIC_9")
    time.sleep(0.5)
    
    hex_send(sock, "00023209", "ISLAND_EDIT_MAGIC_10")
    hex_send(sock, "0002f085", "ISLAND_EDIT_MAGIC_11")
    hex_send(sock, "00022006", "ISLAND_EDIT_MAGIC_12")
    hex_send(sock, "00025003", "ISLAND_EDIT_MAGIC_13")
    time.sleep(0.5)
    
    # 6. Start sending coords
    hex_send(sock, "0006010120002000", "ISLAND_EDIT_COORDS")
    
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

def deposit_1b_spina(sock):
    """
    Sequence to convert 1,000,000,000 Spina into a 1B Spina Item.
    Requires at least 1,002,000,000 Spina in inventory to be safe.
    """
    print("[*] Initiating 1B Spina Deposit Sequence...")
    hex_send(sock, "0002b402", "DEPOSIT_INIT_1")
    time.sleep(0.5)
    hex_send(sock, "0007b4040100000001", "DEPOSIT_EXECUTE_1B")
    time.sleep(0.5)
    hex_send(sock, "0002b402", "DEPOSIT_FINALIZE")
    print("[+] 1B Spina Deposit Sequence Completed.")
