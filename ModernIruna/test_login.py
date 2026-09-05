import os, sys, time, socket, binascii

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from core.login import connect_and_login
from core.world_entry import enter_world
from core.packet_helpers import start_packet_log
from core.game_state import state

# I will fetch token with powershell and pass it or use app.js url
MAGEURL = 'https://gae4php82-real.an.r.appspot.com/a/iruna/api/world/login?test=1' # wait, the real url is in the proxy trace
