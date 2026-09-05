import re
data_hex = "00000051013001000001000101000001010001f001a2001a0701e5310167f52c0000118a000007e400012e0000001500890000000000000000000000000000118a00000988"
idx = data_hex.find("0130")
matches = re.finditer(r'([0-9a-f]{8})([0-9a-f]{8})([0-9a-f]{8})([0-9a-f]{4})', data_hex[idx:])
for m in matches:
    print("Match:", m.groups())
    spina_hex, hp_hex, mp_hex, namelen_hex = m.groups()
    max_hp = int(hp_hex, 16)
    max_mp = int(mp_hex, 16)
    name_len = int(namelen_hex, 16)
    print("Vals:", max_hp, max_mp, name_len)
    end_idx = m.end() + (name_len * 2)
    print("Next:", data_hex[idx:][end_idx:end_idx+2])
