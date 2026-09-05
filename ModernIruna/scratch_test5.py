import re
data_hex = "0130000100010001000100010478017b000b092c97cf0139b3db00000f59000004d00008414141414141414100"
idx = data_hex.find("0130")
matches = re.finditer(r'(?=([0-9a-f]{8})([0-9a-f]{8})([0-9a-f]{8})([0-9a-f]{4}))', data_hex[idx:])
for m in matches:
    if m.start() % 2 != 0:
        continue
    spina_hex, hp_hex, mp_hex, namelen_hex = m.groups()
    max_hp = int(hp_hex, 16)
    max_mp = int(mp_hex, 16)
    name_len = int(namelen_hex, 16)
    
    if 0 < max_hp < 500000 and 0 < max_mp < 100000 and 1 <= name_len <= 32:
        end_idx = m.start() + 28 + (name_len * 2)
        if end_idx + 2 <= len(data_hex[idx:]) and data_hex[idx:][end_idx:end_idx+2] == '00':
            spina = int(spina_hex, 16)
            print(f"[+] Found! Spina: {spina:,} | HP: {max_hp} | MP: {max_mp} | NameLen: {name_len} | NameHex: {data_hex[idx:][m.start()+28:m.start()+28+(name_len*2)]}")
