import threading

class GameState:
    def __init__(self):
        self.stop_event = threading.Event()
        self.monsters = {}         
        self.target_uid = None     
        self.mode = "MANUAL"      
        self.last_map_coords = "47001000"  # Miscerene Plains spawn (x=0x47, y=0x10)
        self.player_x = 0.0
        self.player_y = 0.0
        self.player_hp = 1
        self.player_mp = 1
        self.player_max_hp = 1
        self.player_max_mp = 0
        self.player_spina = 0
        self.waiting_for_hit = threading.Event()
        self.char_id_hex = ""
        self.damage_log = []
        self.paused = False
        self.inventory = {}
        self.current_map_hex = "012c"  # Default: Miscerene Plains (map 300)
        self.map_name = "Miscerene Plains"
        self.teleport_event = threading.Event()
        self.teleport_success = False
        self.is_reviving = False
        self.map_ready_event = threading.Event()
        self.map_data_event = threading.Event()
        self.check_alive_event = threading.Event()
        self.pending_skill_hex = None
        self.skill_cast_event = threading.Event()
        
        self.skill_cast_confirm_event = threading.Event()
        self.skill_exec_confirm_event = threading.Event()
        self.skill_failed = False
        self.nemesis_fail_count = 0
        
        # Party System
        self.party_members = {}
        self.pending_party_invite = None
        self.party_update_event = threading.Event()

        # Scripting & Boss Automation
        self.in_scripted_sequence = False
        self.auto_zimov_running = False
        self.auto_zimov_kill_count = 0
        self.auto_zimov_run_count = 0
        self.spina_earned = 0
        self.pet_uid_hex = None
        self.boss_id_hex = None
        self.boss_spawn_event = threading.Event()
        self.boss_death_event = threading.Event()
        
        # Disabled Skills/Buffs
        self.disabled_buffs = set()
        
        # Skill Levels (Overrides the default '0001', '0002', etc flags if set)
        self.buff_levels = {
            "revelation": "0001",
            "risparmio": "0002",
            "preire": "0003",
            "bless": "0002"
        }
        
        # Island Mode
        self.is_island_mode = False
        self.in_island_map = False
        self.stall_items = []
        self.island_list = []
        
        self.npc_talk_mode = False

state = GameState()
