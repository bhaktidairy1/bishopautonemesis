import sys
import socket

sys.path.append("ModernIruna")
# Monkey patch HOST and fetch_token
import core.login as login
login.HOST = "127.0.0.1"
login.PORT = 30004

def mock_fetch_token(url):
    print("[+] Returning mock token from trace")
    return "386635326565326166623162373064336137333139346638393635636637663000187265616c6c79636f6f6b6564303740676d61696c2e636f6d"

login.fetch_token = mock_fetch_token

# Actually the login_payload in genuine trace:
# 003eff020020 386635... 0018 7265616c6c79...
# wait, token is just the first part. The email is appended in connect_and_login?
# Let's check what login.py does.
# We'll just patch connect_and_login directly for testing if needed.

# But wait, login.py might append the email or not.
# We'll see.
# For now, let's just mock connect_and_login completely to just do the raw socket send!

import binascii
from core.game_state import state
from core.world_entry import enter_world

def test_offline():
    # Hardcoded values from genuine trace
    state.current_map_hex = "86c4"
    state.last_map_coords = "81008200"
    
    # Step 1: Connect and Login using actual login logic
    sock, char_id_hex = login.connect_and_login("http://fake")
    print(f"[Test] Logged in with mock token! char_id_hex={char_id_hex}")
    
    # Now run enter_world!
    try:
        enter_world(sock, char_id_hex)
    except Exception as e:
        print(f"Exception during enter_world: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_offline()
