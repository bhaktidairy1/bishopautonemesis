import os
logs = [os.path.join('proxy_logs', f) for f in os.listdir('proxy_logs')]
for f in logs:
    with open(f, 'r', encoding='utf-8') as file:
        try:
            lines = file.readlines()
            for i, line in enumerate(lines):
                if '0000000000000000' in line:
                    continue
                if 'HP (0)' in line or 'HP: 0' in line or 'HP:0' in line or 'died' in line.lower():
                    print(f"Found death in {f}")
                    for j in range(max(0, i-5), min(i+15, len(lines))):
                        if '→' in lines[j] or '←' in lines[j]:
                            print(lines[j].strip())
                    break
        except Exception:
            pass
