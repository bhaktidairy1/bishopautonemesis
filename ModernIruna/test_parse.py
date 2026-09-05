import re

# Simulate the second trace chunk where 0130 is found
# We copy the exact string from the user's message
trace = "000000530130000100010101010101000100450111001b0104dca701dc5b4600004fe30000191f000352616d00000015008900"

idx = trace.find("000000530130")
payload_hex = trace[idx + 12:]
print("Payload hex:", payload_hex)

spina_hex = payload_hex[42:50]
hp_hex = payload_hex[50:58]
mp_hex = payload_hex[58:66]

print(f"Spina hex: {spina_hex} -> {int(spina_hex, 16)}")
print(f"HP hex: {hp_hex} -> {int(hp_hex, 16)}")
print(f"MP hex: {mp_hex} -> {int(mp_hex, 16)}")
