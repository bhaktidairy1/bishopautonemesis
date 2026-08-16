"""
client.py — Slim orchestrator that wires all modules together.

This is the single entry point imported by server.py.
All heavy logic lives in the focused modules:
  - login.py:       Token fetch + TCP login handshake
  - world_entry.py: Character select + world entry sequence
  - receiver.py:    Packet receiver + opcode dispatch
  - combat.py:      Combat engine + coordinate heartbeat
"""
import threading

from core.login import connect_and_login
from core.world_entry import enter_world
from core.receiver import continuous_receiver
from core.combat import coordinate_sender, combat_engine
from core.game_state import state
from core.packet_helpers import start_packet_log, hex_send, hex_recv
from core.packets import PKT_INVENTORY_REQ
from core.inventory import load_item_db, parse_inventory_response
from core.map_teleport import load_area_db


class IrunaClient:
    def __init__(self):
        self.sock = None
        self.login_token_hex = None
        self.char_id_hex = None
        self.is_connected = False
        load_item_db()   # Load item names from ItemMaster.sql (if present)
        load_area_db()   # Load map names from Area.sql (if present)

    def connect_and_start(self, mageurl):
        """
        Full connection flow: login → world entry → start threads.
        
        Returns True on success, False on failure.
        """
        try:
            # Phase 1: Login (HTTP auth + TCP handshake)
            self.sock, self.char_id_hex = connect_and_login(mageurl)
        except Exception as e:
            print(f"[-] Login failed: {e}")
            self.is_connected = False
            return False

        try:
            # Phase 2: Enter the game world (13-step replay)
            start_packet_log()  # Log everything after login (rolling log)
            state.char_id_hex = self.char_id_hex
            enter_world(self.sock, self.char_id_hex)
        except Exception as e:
            print(f"[-] World entry failed: {e}")
            self.is_connected = False
            return False

        # Phase 3: Request inventory sync
        # We send the request here, but we do NOT block waiting for the response.
        # The receiver thread will catch the 0120 payload asynchronously.
        hex_send(self.sock, PKT_INVENTORY_REQ, "INVENTORY REQ")
        print("[*] Requested full inventory sync...")

        # Phase 4: Spin up all daemon threads
        state.stop_event.clear()
        state.paused = False

        from core.combat import health_monitor_thread

        t1 = threading.Thread(target=continuous_receiver, args=(self.sock,), daemon=True)
        t2 = threading.Thread(target=coordinate_sender, args=(self.sock,), daemon=True)
        t3 = threading.Thread(target=combat_engine, args=(self.sock,), daemon=True)
        t4 = threading.Thread(target=health_monitor_thread, args=(self.sock,), daemon=True)

        t1.start()
        t2.start()
        t3.start()
        t4.start()

        print("\n[+] Game session established. Threads started.")
        self.is_connected = True
        return True

    def disconnect(self):
        """Safely stops threads and closes the socket."""
        print("[!] Disconnecting client and stopping threads...")
        try:
            from core.packet_helpers import upload_to_discord
            upload_to_discord()
        except:
            pass
        state.stop_event.set()
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
        self.is_connected = False
        
        # Reset stop event for next connection
        import time
        time.sleep(1.0) # Wait for threads to die
        state.stop_event.clear()

    def connect_to_island_and_start(self, mageurl, email):
        """
        Connect to Island (port 30009).
        """
        try:
            from core.login import connect_to_island
            self.sock, self.char_id_hex = connect_to_island(mageurl, email)
        except Exception as e:
            print(f"[-] Island Login failed: {e}")
            self.is_connected = False
            return False

        # Phase 2: Start background threads
        # Island mode may have a different set of threads, but we still need the receiver and coordinate sender
        print("\n[+] Island session established. Starting threads...")
        self.is_connected = True
        state.char_id_hex = self.char_id_hex
        state.is_island_mode = True
        state.in_island_map = False

        threading.Thread(target=coordinate_sender, args=(self.sock,), daemon=True).start()
        threading.Thread(target=continuous_receiver, args=(self.sock,), daemon=True).start()
        
        return True


# Singleton — imported by server.py as `from core.client import client`
client = IrunaClient()
