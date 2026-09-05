import sys
import socket
import binascii
import time

def parse_trace(filename):
    actions = []
    with open(filename, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            if "→" not in line:
                # Some lines might have weird encoding of arrow
                line = line.replace("+'", "→")
                if "→" not in line:
                    if " C S " in line or " S C " in line:
                        line = line.replace(" C S ", " C→S ").replace(" S C ", " S→C ")
            
            if "C→S" in line:
                parts = line.split("C→S", 1)[1].split(":", 1)
                if len(parts) == 2:
                    hex_str = parts[1].strip()
                    if hex_str and all(c in "0123456789abcdefABCDEF" for c in hex_str[:8]):
                        actions.append(('RECV', hex_str))
            elif "S→C" in line:
                parts = line.split("S→C", 1)[1].split(":", 1)
                if len(parts) == 2:
                    hex_str = parts[1].strip()
                    if hex_str and all(c in "0123456789abcdefABCDEF" for c in hex_str[:8]):
                        actions.append(('SEND', hex_str))
    return actions

def run_mock_server(port, trace_file):
    actions = parse_trace(trace_file)
    print(f"[Mock] Parsed {len(actions)} actions from trace.")
    
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('127.0.0.1', port))
    server.listen(1)
    print(f"[Mock] Listening on 127.0.0.1:{port} ...")
    
    conn, addr = server.accept()
    print(f"[Mock] Accepted connection from {addr}")
    
    for act_type, hex_str in actions:
        if act_type == 'SEND':
            print(f"[Mock] -> SENDing {len(hex_str)//2} bytes: {hex_str[:30]}...")
            conn.sendall(binascii.unhexlify(hex_str))
            time.sleep(0.01)
        elif act_type == 'RECV':
            expected_len = len(hex_str) // 2
            print(f"[Mock] <- EXPECTING {expected_len} bytes starting with {hex_str[:8]}...")
            
            # Read 2 byte length header
            len_bytes = conn.recv(2)
            if not len_bytes:
                print("[Mock] Connection closed prematurely by client!")
                return
            pkt_len = int.from_bytes(len_bytes, 'big')
            
            # Read the rest of the packet based on length header
            received_data = len_bytes
            to_read = pkt_len
            while to_read > 0:
                chunk = conn.recv(to_read)
                if not chunk:
                    print("[Mock] Connection closed prematurely by client!")
                    return
                received_data += chunk
                to_read -= len(chunk)
            
            recv_hex = binascii.hexlify(received_data).decode()
            print(f"[Mock] <- RECEIVED: {recv_hex[:30]}...")
            
            # Simple check if the opcode matches (e.g. first 8-10 chars)
            if recv_hex[:8] != hex_str[:8]:
                print(f"[Mock] WARNING: Mismatch! Expected {hex_str[:20]}, got {recv_hex[:20]}")
    
    print("[Mock] Finished all actions. Keeping socket open for 2 seconds.")
    time.sleep(2)
    conn.close()
    server.close()
    print("[Mock] Done.")

if __name__ == "__main__":
    trace = r"g:\Games\Drive_D_Backup\Hacking Projects\iruna\TradeHacks\NoAPKgaming\StandaloneCustomIruna\genuineflowBaumMap.txtt"
    run_mock_server(30004, trace)
