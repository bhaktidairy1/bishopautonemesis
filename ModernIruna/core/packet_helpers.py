"""
packet_helpers.py — Low-level send/receive helpers with optional file logging.

Call start_packet_log() after login to begin writing all packets to a timestamped file.
"""
import binascii
import datetime
import os

# ════════════════════════════════════════════
#  FILE LOGGING
# ════════════════════════════════════════════
import threading

_log_file = None
_log_filepath = None
_log_lines = 0
_log_lock = threading.RLock()


def get_current_log_filepath():
    """Return the active packet log filepath, if any."""
    with _log_lock:
        return _log_filepath


def start_packet_log(log_dir=None):
    """
    Start logging all packets to a timestamped file.
    Call this after login to capture the full game session.
    """
    global _log_file, _log_filepath, _log_lines
    import sys
    if "--nolog" in sys.argv:
        print("[*] Packet logging disabled via --nolog")
        return None
        
    with _log_lock:
        if log_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            log_dir = os.path.join(base_dir, "logs")
        os.makedirs(log_dir, exist_ok=True)
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        _log_filepath = os.path.join(log_dir, f"packet_log_{timestamp}.txt")
        
        _log_file = open(_log_filepath, "a", encoding="utf-8")
        _log_file.write(f"=== Packet Log Started: {datetime.datetime.now()} ===\n")
        _log_file.flush()
        _log_lines = 0
        print(f"[+] Packet logging to: {_log_filepath}")
        return _log_filepath


def stop_packet_log():
    """Close the log file."""
    global _log_file, _log_filepath
    with _log_lock:
        if _log_file:
            try:
                _log_file.write(f"=== Packet Log Ended: {datetime.datetime.now()} ===\n")
                _log_file.close()
            except Exception:
                pass
            _log_file = None

def upload_to_discord():
    """Upload the current packet log to Discord."""
    import sys, os
    if "--minimal" not in sys.argv:
        return
        
    webhook_url = "https://discord.com/api/webhooks/1520498468655730788/z6GwrwKJbCWSFPoDn2V1hlskBygnrX-E6Ijw1szMmckieJiriKqNb6R8nV0fJ5TWv4po"
    filepath = get_current_log_filepath()
    if not filepath or not os.path.exists(filepath):
        return
        
    print(f"[*] Uploading log to Discord: {os.path.basename(filepath)}...")
    try:
        import requests
        with open(filepath, "rb") as f:
            response = requests.post(
                webhook_url,
                files={"file": (os.path.basename(filepath), f)}
            )
        if response.status_code in (200, 204):
            print("[+] Successfully uploaded packet log to Discord.")
        else:
            print(f"[-] Discord upload failed: {response.status_code}")
    except Exception as e:
        print(f"[-] Discord upload error: {e}")


def write_log(line: str):
    """Write a line to the packet log file (if logging is active)."""
    global _log_file, _log_lines, _log_filepath
    with _log_lock:
        if _log_file:
            ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
            try:
                _log_file.write(f"[{ts}] {line}\n")
                _log_file.flush()
                _log_lines += 1
                
                import sys
                if "--minimal" in sys.argv and _log_lines >= 1000:
                    # Overwrite log in minimal mode to strictly cap disk usage
                    _log_file.close()
                    _log_file = open(_log_filepath, "w", encoding="utf-8")
                    _log_file.write(f"=== Packet Log Rolled Over: {datetime.datetime.now()} ===\n")
                    _log_lines = 0
            except Exception:
                pass


# ════════════════════════════════════════════
#  SEND / RECEIVE HELPERS
# ════════════════════════════════════════════

def hex_recv(sock, expect_len=4096, label=None) -> bytes:
    data = sock.recv(expect_len)
    if not data:
        raise ConnectionError("Server closed connection")
    h = binascii.hexlify(data).decode()
    if label:
        msg = f"<- {label} ({len(data)} bytes): {h}"
    else:
        msg = f"<- Received ({len(data)} bytes): {h}"
        
    import sys
    if "--minimal" not in sys.argv:
        print(msg)
    write_log(msg)
    return data


def hex_send(sock, hexstr: str, label=None):
    hexstr = hexstr.replace(" ", "")
    raw = binascii.unhexlify(hexstr)
    sock.sendall(raw)
    if label:
        msg = f"-> {label}: {hexstr}"
    else:
        msg = f"-> Sent: {hexstr}"
        
    import sys
    if "--minimal" not in sys.argv:
        print(msg)
    write_log(msg)
