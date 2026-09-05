import sys
import json
import binascii

def build_mock_server(trace_file, output_file):
    with open(trace_file, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()

    # Clean up lines
    cleaned = []
    for line in lines:
        if " C S " in line or " S C " in line:
            line = line.replace(" C S ", " C→S ").replace(" S C ", " S→C ")
        line = line.replace("+'", "→")
        cleaned.append(line.strip())

    # Map C->S opcode to a list of S->C responses that follow it
    # We'll use the first 4 bytes (8 hex chars) of the C->S packet as the trigger.
    # Wait, the length is 2 bytes, so opcode is bytes 2-3 (chars 4-7).
    # e.g. 0002 fff3 -> 0002fff3, opcode is fff3.
    # Actually, let's just group S->C packets that occur before the next C->S packet.
    
    flow = []
    current_type = None
    current_hex = ""

    for line in cleaned:
        if "C→S" in line:
            # Save previous if any
            if current_type == "CS":
                flow.append({"req": current_hex, "resps": []})
            elif current_type == "SC":
                if len(flow) > 0:
                    flow[-1]["resps"].append(current_hex)
            
            current_type = "CS"
            parts = line.split("C→S", 1)[1].split(":", 1)
            if len(parts) == 2:
                current_hex = parts[1].strip()
        elif "S→C" in line:
            # Save previous if any
            if current_type == "CS":
                flow.append({"req": current_hex, "resps": []})
            elif current_type == "SC":
                if len(flow) > 0:
                    flow[-1]["resps"].append(current_hex)

            current_type = "SC"
            parts = line.split("S→C", 1)[1].split(":", 1)
            if len(parts) == 2:
                current_hex = parts[1].strip()
        else:
            # Continuation line
            if current_type is not None:
                current_hex += line.strip()

    # Save the last one
    if current_type == "CS":
        flow.append({"req": current_hex, "resps": []})
    elif current_type == "SC":
        if len(flow) > 0:
            flow[-1]["resps"].append(current_hex)


    # Generate mock_server_smart.py
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('''import socket
import binascii
import time

FLOW = [
''')
        for step in flow:
            req = step["req"]
            resps = step["resps"]
            f.write(f'    {{"req": "{req}", "resps": {json.dumps(resps)}}},\n')
            
        f.write(''']

def run():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('127.0.0.1', 30004))
    server.listen(1)
    print("[Mock] Listening on 127.0.0.1:30004...")
    
    conn, addr = server.accept()
    print(f"[Mock] Accepted connection from {addr}")
    
    step_idx = 0
    while step_idx < len(FLOW):
        expected_req = FLOW[step_idx]["req"]
        expected_len = len(expected_req) // 2
        
        # We just read packets from the client.
        # Length header is 2 bytes
        len_bytes = conn.recv(2)
        if not len_bytes:
            print("[Mock] Client disconnected.")
            break
            
        pkt_len = int.from_bytes(len_bytes, 'big')
        payload = b""
        while len(payload) < pkt_len:
            chunk = conn.recv(pkt_len - len(payload))
            if not chunk: break
            payload += chunk
            
        full_pkt = len_bytes + payload
        hex_pkt = binascii.hexlify(full_pkt).decode()
        print(f"[Mock] Recv: {hex_pkt[:40]}...")
        
        # Check if this matches our expected step
        # Just check opcode (chars 4-7)
        if hex_pkt[4:8] == expected_req[4:8]:
            print(f"[Mock] Matched step {step_idx} (Opcode {hex_pkt[4:8]})")
            
            # Send all buffered responses for this step
            for resp in FLOW[step_idx]["resps"]:
                print(f"[Mock] Sending {len(resp)//2} bytes...")
                conn.sendall(binascii.unhexlify(resp))
                time.sleep(0.05)
                
            step_idx += 1
        else:
            print(f"[Mock] IGNORING OUT OF ORDER PACKET (Got {hex_pkt[4:8]}, expected {expected_req[4:8]})")
            # We don't increment step_idx, just wait for the right one.
            # But what if the trace has multiple C->S back to back without S->C?
            # Our flow logic groups S->C under the most recent C->S.
            # If a C->S has no S->C, it still increments step_idx.
            # Wait, if client sends two packets back to back, the server processes them one by one.
            pass

    print("[Mock] Reached end of flow. Sleeping.")
    time.sleep(5)
    conn.close()
    server.close()

if __name__ == "__main__":
    run()
''')
    print("Built mock_server_smart.py")

if __name__ == "__main__":
    build_mock_server(r"g:\Games\Drive_D_Backup\Hacking Projects\iruna\TradeHacks\NoAPKgaming\StandaloneCustomIruna\genuineflowBaumMap.txtt", "mock_server_smart.py")
