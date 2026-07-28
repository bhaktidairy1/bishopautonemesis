import re
import os

MOB_DB = {}

def load_mob_db():
    global MOB_DB
    MOB_DB.clear()
    
    # Path to the decrypted_Monster.sql
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sql_path = os.path.join(base_dir, "decrypted_Monster.sql")
    
    if not os.path.exists(sql_path):
        print(f"[!] Could not find {sql_path}. Mob names will not resolve.")
        return

    print(f"[*] Loading Mob Database from {sql_path}...")
    
    try:
        with open(sql_path, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                if not line.startswith("INSERT INTO `Monster` VALUES"):
                    continue
                    
                # Extract the values inside parentheses
                # Example: INSERT INTO `Monster` VALUES (12500,0,'Botaniga',...)
                match = re.search(r"\((.*?)\);", line)
                if not match:
                    continue
                    
                values_str = match.group(1)
                # Split by comma, but be careful with strings containing commas
                # For this specific SQL dump, simple split usually works, but let's be slightly safer
                parts = []
                in_str = False
                current = ""
                for char in values_str:
                    if char == "'":
                        in_str = not in_str
                    elif char == ',' and not in_str:
                        parts.append(current)
                        current = ""
                        continue
                    current += char
                parts.append(current) # Add last part
                
                if len(parts) >= 3:
                    try:
                        area_id = int(parts[0].strip())
                        variant = int(parts[1].strip())
                        name = parts[2].strip().strip("'")
                        
                        full_id = area_id * 100 + variant
                        MOB_DB[full_id] = name
                    except ValueError:
                        pass
        print(f"[+] Loaded {len(MOB_DB)} distinct Base Mob IDs from SQL.")
    except Exception as e:
        print(f"[!] Error loading Mob DB: {e}")

def get_mob_name(full_id: int) -> str:
    """Attempt to resolve mob name from DB."""
    if full_id in MOB_DB:
        return MOB_DB[full_id]
    return f"Unknown Mob ({full_id})"
