import os
import sys
import argparse
import threading
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from core.client import client
from core.game_state import state
from core.map_teleport import teleport, teleport_preset, KNOWN_MAPS, find_map_by_name
from core.mob_db import load_mob_db

# Load Mob SQL on startup
load_mob_db()

# Parse arguments
parser = argparse.ArgumentParser(description="Iruna Server")
parser.add_argument("--minimal", action="store_true", help="Run the server with the minimal web UI")
parser.add_argument("--url", type=str, help="Launch URL to auto-connect and auto-start")
parser.add_argument("--nolog", action="store_true", help="Disable packet logging to disk")
args = parser.parse_args()

app = Flask(__name__, static_folder="web")
CORS(app)

# Buffer for sys.stdout redirection
log_buffer = []
log_history = []

class WebLogRedirector:
    def __init__(self, original_stdout):
        self.original_stdout = original_stdout
        self.current_line = ""

    def write(self, string):
        self.original_stdout.write(string)
        self.current_line += string
        while '\n' in self.current_line:
            line, self.current_line = self.current_line.split('\n', 1)
            
            # Temporary buffer for web polling
            if len(log_buffer) > 500:
                log_buffer.pop(0)
            log_buffer.append(line + '\n')
            
            # Permanent history buffer for page reloads
            if len(log_history) > 500:
                log_history.pop(0)
            log_history.append(line + '\n')
            
    def flush(self):
        self.original_stdout.flush()

# Route stdout heavily
sys.stdout = WebLogRedirector(sys.stdout)

if args.url:
    def auto_connect_loop():
        import time
        print(f"[*] Auto-connecting to {args.url[:50]}...")
        if client.connect_and_start(args.url):
            print("[*] Connected! Waiting for world to load...")
            # Wait until we are fully loaded in a map
            while not state.current_map_hex:
                time.sleep(1)
            # Short buffer to ensure environment is stabilized
            time.sleep(2)
            
            print("[*] World loaded. Starting Auto-Zimov loop!")
            from core.boss_module import auto_zimov_loop
            # Start the loop in this thread
            auto_zimov_loop(client.sock)
            
    threading.Thread(target=auto_connect_loop, daemon=True).start()

@app.route("/")
def index():
    if args.minimal:
        return send_from_directory("web", "minimal.html")
    return send_from_directory("web", "index.html")

@app.route("/<path:path>")
def static_files(path):
    return send_from_directory("web", path)

@app.route("/api/connect", methods=["POST"])
def connect_iruna():
    data = request.json
    url = data.get("url")
    if not url: return jsonify({"error": "No URL provided"}), 400

    def background_connect():
        import time
        if client.connect_and_start(url):
            if args.minimal:
                print("[*] Connected via minimal UI. Waiting for world to load to auto-start Zimov...")
                # Wait until we are fully loaded in a map
                while not state.current_map_hex:
                    time.sleep(1)
                # Short buffer to ensure environment is stabilized
                time.sleep(2)
                
                print("[*] World loaded. Auto-starting Zimov...")
                if not getattr(state, "auto_nemesis_running", False):
                    from core.boss_module import auto_zimov_loop
                    # Start the loop in this thread
                    auto_zimov_loop(client.sock)

    threading.Thread(target=background_connect, daemon=True).start()
    return jsonify({"status": "Connecting..."})

@app.route("/api/state", methods=["GET"])
def get_state():
    try:
        import subprocess
        commit_hash = subprocess.check_output(['git', 'log', '-1', '--format=%h - %s']).decode('utf-8').strip()
    except Exception:
        commit_hash = "Unknown Version"

    return jsonify({
        "version": commit_hash,
        "connected": client.is_connected,
        "mode": state.mode,
        "paused": state.paused,
        "targetUid": state.target_uid,
        "monsters": state.monsters,
        "inventory": state.inventory,
        "map_name": state.map_name,
        "current_map_hex": state.current_map_hex,
        "auto_zimov_running": getattr(state, "auto_zimov_running", False),
        "auto_zimov_kill_count": getattr(state, "auto_zimov_kill_count", 0),
        "auto_zimov_run_count": getattr(state, "auto_zimov_run_count", 0),
        "spina_earned": getattr(state, "spina_earned", 0),
        "player_hp": getattr(state, "player_hp", 0),
        "player_mp": getattr(state, "player_mp", 0),
        "player_max_hp": getattr(state, "player_max_hp", 0),
        "player_max_mp": getattr(state, "player_max_mp", 0),
        "party": state.party_members,
        "pendingInvite": state.pending_party_invite
    })

@app.route("/api/party/invite", methods=["POST"])
def api_party_invite():
    if not client or not client.sock:
        return jsonify({"error": "Not connected"}), 400
    uid = request.json.get("uid")
    if not uid:
        return jsonify({"error": "Missing uid"}), 400
    
    from core.packet_helpers import hex_send
    from core.packets import build_party_invite_packet
    pkt = build_party_invite_packet(uid)
    hex_send(client.sock, pkt, f"PARTY INVITE -> {uid}")
    return jsonify({"success": True})

@app.route("/api/party/accept", methods=["POST"])
def api_party_accept():
    if not client or not client.sock:
        return jsonify({"error": "Not connected"}), 400
    uid = state.pending_party_invite
    if not uid:
        return jsonify({"error": "No pending invite"}), 400
    
    from core.packet_helpers import hex_send
    from core.packets import build_party_accept_packet
    pkt = build_party_accept_packet(uid)
    hex_send(client.sock, pkt, f"ACCEPT PARTY -> {uid}")
    
    state.pending_party_invite = None
    return jsonify({"success": True})

@app.route("/api/disconnect", methods=["POST"])
def disconnect_client():
    if client and client.sock:
        try:
            client.sock.close()
        except Exception:
            pass
        client.sock = None
        client.is_connected = False
        print("[*] Connection closed manually via Web UI")
    return jsonify({"success": True})

@app.route("/api/party/leave", methods=["POST"])
def api_party_leave():
    if not client or not client.sock:
        return jsonify({"error": "Not connected"}), 400
    
    from core.packet_helpers import hex_send
    from core.packets import build_party_leave_packet
    pkt = build_party_leave_packet()
    hex_send(client.sock, pkt, "LEAVE/DISBAND PARTY")
    return jsonify({"success": True})

@app.route("/api/radar", methods=["GET"])
def get_radar():
    import math
    radar_mobs = []
    px, py = state.player_x, state.player_y
    for uid, m in state.monsters.items():
        mx, my = m.get('x', 0.0), m.get('y', 0.0)
        dist = math.sqrt((px - mx)**2 + (py - my)**2)
        
        name = m.get('name', 'Unknown')
        if name == 'Unknown':
            name = 'Unknown (Player?)'
            
        radar_mobs.append({
            "uid": uid,
            "id": m.get('id', -1),
            "is_player": m.get('is_player', False),
            "name": name,
            "x": mx,
            "y": my,
            "distance": round(dist, 2)
        })
    return jsonify({
        "player": {"x": px, "y": py},
        "mobs": radar_mobs
    })

@app.route("/api/revive", methods=["POST"])
def api_revive():
    if not client or not client.sock:
        return jsonify({"error": "Not connected"}), 400
    
    from core.packet_helpers import hex_send
    hex_send(client.sock, "00020134", "REVIVE REQUEST")
    return jsonify({"success": True})


@app.route("/api/cast_skill", methods=["POST"])
def api_cast_skill():
    data = request.json
    uid = data.get("uid")
    skill_hex = data.get("skill_hex")
    
    if not uid or not skill_hex:
        return jsonify({"error": "Missing uid or skill_hex"}), 400
        
    if uid == "self":
        target_uid = state.char_id_hex
        mob_x = state.player_x
        mob_y = state.player_y
    else:
        mob = state.monsters.get(uid)
        if not mob:
            return jsonify({"error": "Mob not found in state"}), 404
        target_uid = uid
        mob_x = mob.get('x', 0)
        mob_y = mob.get('y', 0)
    
    from core.packet_helpers import hex_send
    from core.packets import build_coord_packet, build_skill_cast_packet
    
    # Calculate hex coords to teleport onto the mob or self
    x_int = int(mob_x * 256)
    y_int = int(mob_y * 256)
    
    x_hex = format(x_int & 0xFFFF, '04x')
    y_hex = format(y_int & 0xFFFF, '04x')
    
    # 1. Update internal state and Teleport onto target (if not self)
    if uid != "self":
        state.player_x = mob_x
        state.player_y = mob_y
        coord_pkt = build_coord_packet(f"{x_hex}{y_hex}")
        hex_send(client.sock, coord_pkt, "RADAR TARGET")
    
    # 2. Fire Skill (0143 = Prepare)
    cast_pkt = build_skill_cast_packet(skill_hex, target_uid)
    hex_send(client.sock, cast_pkt, "SKILL CAST")
    
    # 3. Fire Skill Execute (0141)
    # MUST use the correct flag! 0101 for Nemesis (138f), 0001 for most others
    flag = "0101" if skill_hex == "138f" else "0001"
    execute_pkt = f"000a0141{skill_hex}{flag}{target_uid}"
    hex_send(client.sock, execute_pkt, "SKILL EXECUTE")

    # 4. Track Target
    if uid != "self":
        state.target_uid = target_uid
        
    return jsonify({"success": True})

@app.route("/api/set_coords", methods=["POST"])
def api_set_coords():
    data = request.json
    try:
        x = float(data.get("x", 0))
        y = float(data.get("y", 0))
        state.player_x = x
        state.player_y = y
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/api/logs", methods=["GET"])
def get_logs():
    global log_buffer
    logs_to_send = log_buffer[:]
    log_buffer = []  # clear after fetching to keep payload lightning fast
    return jsonify({"logs": logs_to_send})

@app.route("/api/logs/history", methods=["GET"])
def get_log_history():
    return jsonify({"logs": log_history})

@app.route("/api/action", methods=["POST"])
def perform_action():
    data = request.json
    action_type = data.get("type")
    
    if action_type == "set_mode":
        state.mode = data.get("mode")
        return jsonify({"success": True})
        
    elif action_type == "toggle_pause":
        state.paused = not state.paused
        return jsonify({"success": True, "paused": state.paused})
        
    elif action_type == "join_pt_area":
        if not client.sock:
            return jsonify({"error": "Not connected"}), 400
            
        from core.packet_helpers import hex_send
        from core.packets import build_warp_entry_packet
        import time
        
        def _join_pt_area():
            try:
                map_hex = getattr(state, 'current_map_hex', '00030d42')
                if len(map_hex) < 8: map_hex = map_hex.zfill(8)
                
                print(f"[*] Initiating PT Area Join Sequence for Map {map_hex}...")
                
                # 1. Handshake 2
                hex_send(client.sock, "0002b502", "PT_AREA_2")
                time.sleep(0.4)
                
                # 2. Handshake 9
                hex_send(client.sock, "0002b509", "PT_AREA_9")
                time.sleep(1.2)
                
                state.map_ready_event.clear()
                
                # 3. Enter Area 
                hex_send(client.sock, f"00120114000aae600000000000000000{map_hex}", "PT_AREA_ENTER")
                
                print("    [!] Waiting for Map Sync OK (b503)...")
                if not state.map_ready_event.wait(timeout=10.0):
                    print("[!] Timeout waiting for PT Area Map Sync OK.")
                
                time.sleep(0.1)
                
                # 4. Handshake 1
                hex_send(client.sock, "0002b501", "PT_AREA_1")
                time.sleep(0.2)
                
                # 5. Map Sync ACK
                hex_send(client.sock, "0002013a", "MAP_SYNC_ACK")
                
                # 6. Map Entry Exit 
                hex_send(client.sock, build_warp_entry_packet(map_hex), "MAP_ENTRY")
                
                print("[+] Successfully joined PT Area.")
                
                time.sleep(1.0)
                print("[*] Forcing position to safe spot (108, 180)...")
                state.player_x = 108.0
                state.player_y = 180.0
                
                from core.packets import build_coord_packet
                from core.map_teleport import _make_heartbeat_coords
                coords = _make_heartbeat_coords(108, 180)
                hex_send(client.sock, build_coord_packet(coords), "FORCE COORD")
                
            except Exception as e:
                print(f"[!] PT Area join error: {e}")
                
        threading.Thread(target=_join_pt_area, daemon=True).start()
        return jsonify({"success": True})

    elif action_type == "create_pt_area":
        if not client.sock:
            return jsonify({"error": "Not connected"}), 400
            
        from core.packet_helpers import hex_send
        from core.packets import build_warp_entry_packet
        import time
        
        def _create_and_enter_pt_area():
            try:
                from core.pt_area import create_and_enter_pt_area
                create_and_enter_pt_area(client.sock)
            except Exception as e:
                print(f"[!] PT Area error: {e}")
                
        threading.Thread(target=_create_and_enter_pt_area, daemon=True).start()
        return jsonify({"success": True})
    elif action_type == "inject_hex":
        raw = data.get("hex", "").strip()
        try:
            if all(c in "0123456789abcdefABCDEF " for c in raw) and (len(raw.replace(" ","")) % 2 == 0):
                from core.packet_helpers import hex_send
                hex_send(client.sock, raw, "MANUAL INJECT")
                return jsonify({"success": True})
            return jsonify({"error": "Invalid hex format"}), 400
        except Exception as e:
            return jsonify({"error": str(e)}), 500
            
    elif action_type == "set_target":
        state.target_uid = data.get("uid")
        return jsonify({"success": True})

    elif action_type == "teleport":
        preset = data.get("preset")
        if preset:
            threading.Thread(
                target=teleport_preset,
                args=(client.sock, preset),
                daemon=True
            ).start()
            return jsonify({"success": True, "target": preset})
        map_id = data.get("map_id")
        if map_id:
            x = data.get("x")
            y = data.get("y")
            threading.Thread(
                target=teleport,
                args=(client.sock, int(map_id), x, y),
                daemon=True
            ).start()
            return jsonify({"success": True, "map_id": map_id})
        return jsonify({"error": "Need 'preset' or 'map_id'"}), 400

    elif action_type == "search_maps":
        query = data.get("query", "")
        results = find_map_by_name(query)[:20]
        return jsonify({"results": [{"id": r[0], "hex": f"{r[0]:04X}", "name": r[1]} for r in results]})

    elif action_type == "zimov_boss":
        from core.boss_module import zimov_battle_thread
        
        if state.current_map_hex != "3e1c":
            return jsonify({"status": "error", "message": "Must be in Dierolt (3e1c) to start Zimov"}), 400
            
        if state.in_scripted_sequence or getattr(state, "auto_zimov_running", False):
            return jsonify({"status": "error", "message": "A sequence is already running"}), 400
            
        threading.Thread(target=zimov_battle_thread, args=(client.sock,), daemon=True).start()
        return jsonify({"status": "zimov_started"})

    elif action_type == "kakeula_heal":
        from core.boss_module import kakeula_heal_thread
        
        if state.in_scripted_sequence or getattr(state, "auto_zimov_running", False):
            return jsonify({"status": "error", "message": "A sequence is already running"}), 400
            
        threading.Thread(target=kakeula_heal_thread, args=(client.sock,), daemon=True).start()
        return jsonify({"status": "heal_started"})

    elif action_type == "kakeula_sell":
        from core.boss_module import kakeula_sell_thread
        
        if state.in_scripted_sequence or getattr(state, "auto_zimov_running", False):
            return jsonify({"status": "error", "message": "A sequence is already running"}), 400
            
        threading.Thread(target=kakeula_sell_thread, args=(client.sock,), daemon=True).start()
        return jsonify({"status": "sell_started"})

    elif action_type == "start_auto_zimov":
        from core.boss_module import auto_zimov_loop
        
        if state.current_map_hex != "3e1c":
            return jsonify({"status": "error", "message": "Must be in Dierolt (3e1c) to start"}), 400
            
        if getattr(state, "auto_zimov_running", False) or getattr(state, "auto_nemesis_running", False) or state.in_scripted_sequence:
            return jsonify({"status": "error", "message": "A sequence is already running"}), 400
            
        threading.Thread(target=auto_zimov_loop, args=(client.sock,), daemon=True).start()
        return jsonify({"status": "auto_zimov_started"})
        
    elif action_type == "stop_auto_zimov":
        state.auto_zimov_running = False
        return jsonify({"status": "auto_zimov_stopped"})

    elif action_type == "start_auto_nemesis":
        from core.boss_module import auto_nemesis_loop
        
        if getattr(state, "auto_zimov_running", False) or getattr(state, "auto_nemesis_running", False) or state.in_scripted_sequence:
            return jsonify({"status": "error", "message": "A sequence is already running"}), 400
            
        threading.Thread(target=auto_nemesis_loop, args=(client.sock,), daemon=True).start()
        return jsonify({"status": "auto_nemesis_started"})
        
    elif action_type == "stop_auto_nemesis":
        state.auto_nemesis_running = False
        return jsonify({"status": "auto_nemesis_stopped"})
        
    elif action_type == "cast_buffs":
        from core.boss_module import cast_bishop_buffs
        if client.sock:
            threading.Thread(target=cast_bishop_buffs, args=(client.sock,), daemon=True).start()
        return jsonify({"status": "buffs_cast"})
        
    elif action_type == "cast_individual_buff":
        from core.boss_module import cast_individual_buff
        buff_id = data.get("buff_id")
        if client.sock and buff_id:
            threading.Thread(target=cast_individual_buff, args=(client.sock, buff_id), daemon=True).start()
        return jsonify({"status": "individual_buff_cast"})

    return jsonify({"error": "Unknown action"}), 400

def cleanup_and_exit():
    print("[!] Cleaning up resources...")
    state.auto_zimov_running = False
    state.auto_nemesis_running = False
    
    if client.sock:
        try:
            client.sock.close()
        except:
            pass
            
    # Try to extract the log file before stopping the logger
    log_filepath = None
    try:
        from core.packet_helpers import get_current_log_filepath
        log_filepath = get_current_log_filepath()
    except Exception:
        pass

    try:
        from core.packet_helpers import stop_packet_log
        stop_packet_log()
    except:
        pass
        
    # --- Discord Webhook Upload ---
    # webhook_url = "https://discord.com/api/webhooks/1520498468655730788/z6GwrwKJbCWSFPoDn2V1hlskBygnrX-E6Ijw1szMmckieJiriKqNb6R8nV0fJ5TWv4po"
    # if log_filepath and os.path.exists(log_filepath):
    #     print(f"[*] Uploading log to Discord: {os.path.basename(log_filepath)}...")
    #     try:
    #         import requests
    #         with open(log_filepath, "rb") as f:
    #             response = requests.post(
    #                 webhook_url,
    #                 files={"file": (os.path.basename(log_filepath), f)}
    #             )
    #         if response.status_code in (200, 204):
    #             print("[+] Successfully uploaded packet log to Discord.")
    #         else:
    #             print(f"[-] Discord upload failed: {response.status_code}")
    #     except Exception as e:
    #         print(f"[-] Discord upload error: {e}")

    
    print("[!] Resources freed. Exiting program.")
    os._exit(0)

@app.route("/api/stop", methods=["POST", "GET"])
@app.route("/stop", methods=["POST", "GET"])
def stop_server():
    print("[!] Shutdown requested via Web UI.")
    cleanup_and_exit()

if __name__ == "__main__":
    def find_free_port(start_port):
        import socket
        port = start_port
        while True:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.bind(("0.0.0.0", port))
                s.close()
                return port
            except OSError:
                port += 1
                
    base_port = int(os.environ.get("PORT", 10000))
    port = find_free_port(base_port)
    if port != base_port:
        print(f"[!] Port {base_port} is occupied. Using port {port} instead.")
        
    # --- Foolproof Exit Handlers ---
    import atexit
    import signal
    import sys

    # Prevent cleanup_and_exit from running multiple times
    _cleanup_done = False
    def safe_cleanup(*args):
        global _cleanup_done
        if not _cleanup_done:
            _cleanup_done = True
            cleanup_and_exit()

    atexit.register(safe_cleanup)
    
    # Catch termination signals (like Render shutting down the container)
    try:
        signal.signal(signal.SIGTERM, safe_cleanup)
        signal.signal(signal.SIGINT, safe_cleanup)
    except Exception:
        pass # In case signals aren't supported on this thread/OS
        
    # Catch unhandled exceptions
    def handle_unhandled_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        print(f"[CRITICAL] Unhandled exception: {exc_value}")
        safe_cleanup()
        
    sys.excepthook = handle_unhandled_exception

    try:
        app.run(host="0.0.0.0", port=port, debug=False)
    except Exception as e:
        print(f"\n[CRITICAL] Server crashed: {e}")
    finally:
        safe_cleanup()
