"""
login.py — Authentication token fetch and TCP login handshake.

Handles:
  1. HTTP auth flow to get the login token
  2. TCP connection to the game server
  3. Init packet + login packet exchange
  4. Character ID extraction from the ff03 response
"""
import socket
import binascii
import requests
from urllib.parse import urlparse

from core.packet_helpers import hex_recv, hex_send
from core.packets import PKT_INIT, build_login_packet

HOST = "202.239.51.41"
PORT = 30004


def fetch_token(mageurl: str) -> str:
    """
    HTTP auth flow → returns login_token_hex.
    
    Follows the OAuth redirect to get session cookies,
    then hits /authcreate to get the raw token string.
    """
    print(f"[+] Fetching auth token for {mageurl[:40]}...")
    session = requests.Session()
    session.get(mageurl, allow_redirects=True)
    base = f"{urlparse(mageurl).scheme}://{urlparse(mageurl).netloc}"
    resp = session.get(f"{base}/authcreate")
    login_token = resp.text.strip()
    token_hex = login_token.encode().hex()
    print("[+] Token:", token_hex)
    return token_hex


def connect_and_login(mageurl: str) -> tuple:
    """
    Full TCP login sequence. Returns (socket, char_id_hex).
    
    Steps:
      1. fetch_token() via HTTP
      2. TCP connect to HOST:PORT
      3. Send init packet (0002fff3)
      4. Send login packet (FF02 + token)
      5. Validate login ACK (must start with 00000003ff0200)
      6. Parse char_id_hex from ff03 packet
      
    Returns:
        tuple: (connected_socket, char_id_hex)
        
    Raises:
        ConnectionError: If login fails or char_id can't be parsed
    """
    # Step 1: Get auth token
    token_hex = fetch_token(mageurl)
    if not token_hex:
        raise ConnectionError("Failed to fetch token (empty). Check if the URL is correct and wrapped in quotes!")
    
    # Step 2: TCP connect
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(20.0)
    print(f"[+] Connecting to {HOST}:{PORT} …")
    sock.connect((HOST, PORT))
    print("[+] Connected.\n")
    
    # Step 3: Init handshake
    hex_send(sock, PKT_INIT, "Init Packet")
    hex_recv(sock, label="Init Header")
    
    # Step 4: Send login packet
    login_packet = build_login_packet(token_hex)
    sock.sendall(login_packet)
    print(f"-> Login Packet: {binascii.hexlify(login_packet).decode()}")
    
    # Step 5: Validate login ACK
    data = hex_recv(sock, label="Login ACK")
    h = binascii.hexlify(data).decode()
    if not h.startswith("00000003ff0200"):
        print("[-] Unexpected login response:", h)
        sock.close()
        raise ConnectionError("Login refused by server")
    print("[+] Login OK.\n")
    
    # Step 6: Parse char_id_hex from ff03 packet
    char_id_hex = _parse_char_id(sock)
    
    return sock, char_id_hex


def _parse_char_id(sock: socket.socket) -> str:
    """
    Read the ff03 character info packet and extract char_id_hex.
    
    The server sends this immediately after login ACK.
    Pattern: ff030100000001 followed by 4 bytes (8 hex chars) of char ID.
    """
    try:
        sock.settimeout(5.0)
        extra = hex_recv(sock, label="ff03 + char info")
        hexed = binascii.hexlify(extra).decode()
        idx = hexed.find("ff030100000001")
        if idx != -1 and len(hexed) >= idx + 14 + 8:
            char_id_hex = hexed[idx + 14 : idx + 14 + 8]
            print(f"[+] Parsed char_id_hex: {char_id_hex}\n")
            return char_id_hex
        else:
            sock.close()
            raise ConnectionError("Couldn't locate char_id_hex in ff03 packet")
    except socket.timeout:
        sock.close()
        raise ConnectionError("Timeout waiting for ff03 packet")
    finally:
        sock.settimeout(20.0)


def connect_to_island(mageurl: str, email: str) -> tuple:
    """
    TCP login sequence for Island server on port 30009.
    Returns (socket, char_id_hex).
    """
    token_hex = fetch_token(mageurl)
    if not token_hex:
        raise ConnectionError("Failed to fetch token.")
        
    print("[*] STEP 1: Fetching Character ID from Main Server (Port 30004)...")
    try:
        main_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        main_sock.settimeout(20.0)
        main_sock.connect((HOST, PORT))
        hex_send(main_sock, PKT_INIT, "Init Packet")
        hex_recv(main_sock, label="Init Header")
        
        login_packet = build_login_packet(token_hex)
        main_sock.sendall(login_packet)
        data = hex_recv(main_sock, label="Login ACK")
        if not binascii.hexlify(data).decode().startswith("00000003ff0200"):
            raise ConnectionError("Main server login refused.")
            
        char_id_hex = _parse_char_id(main_sock)
    finally:
        main_sock.close()
        print("[*] Main server connection closed.\n")

    print(f"[*] STEP 2: Connecting to Island Server (Port 30009) for character {char_id_hex}...")
    ISLAND_PORT = 30009
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(20.0)
    sock.connect((HOST, ISLAND_PORT))
    print("[+] Connected to Island.\n")
    
    # Island requires the same init handshake!
    hex_send(sock, PKT_INIT, "Init Packet")
    hex_recv(sock, label="Init Header")
    
    from core.packets import build_island_login_packet
    login_packet = build_island_login_packet(token_hex, email)
    sock.sendall(login_packet)
    print(f"-> Island Login Packet: {binascii.hexlify(login_packet).decode()}")
    
    data = hex_recv(sock, label="Island Login ACK")
    h = binascii.hexlify(data).decode()
    if not h.startswith("00000003ff0200"):
        print("[-] Unexpected island login response:", h)
        sock.close()
        raise ConnectionError("Island login refused by server")
    print("[+] Island Login OK.\n")
    
    print("[*] Sending pre-init char selection for Island...")
    hex_send(sock, f"00080002{char_id_hex}0000", "Island Char Select")
    
    # We must receive the ff03 char info again from the island server to complete the handshake
    _parse_char_id(sock)
    
    # Island requires an extra initialization step
    print("[*] Initializing island state...")
    hex_send(sock, "0002a002", "ISLAND INIT")
    
    return sock, char_id_hex
