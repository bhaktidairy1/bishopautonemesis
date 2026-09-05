import re
data_hex = "00000051013001000001000101000001010001f001a2001a0701e5310167f52c0000118a000007e400012e0000001500890000000000000000000000000000118a00000988"
idx = data_hex.find("0130")
matches = re.finditer(r'(?=([0-9a-f]{8})([0-9a-f]{8})([0-9a-f]{8})([0-9a-f]{4}))', data_hex[idx:])
for m in matches:
    spina_hex, hp_hex, mp_hex, namelen_hex = m.groups()
    max_hp = int(hp_hex, 16)
    max_mp = int(mp_hex, 16)
    name_len = int(namelen_hex, 16)
    
    if 0 < max_hp < 500000 and 0 < max_mp < 100000 and 1 <= name_len <= 32:
        end_idx = m.start() + 28 + (name_len * 2)
        if end_idx + 2 <= len(data_hex[idx:]) and data_hex[idx:][end_idx:end_idx+2] == '00':
            spina = int(spina_hex, 16)
            print(f"[+] Found! Spina: {spina:,} | HP: {max_hp} | MP: {max_mp} | NameLen: {name_len} at start {m.start()}")
