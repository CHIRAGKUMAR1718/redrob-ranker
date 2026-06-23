import csv

with open('submission/team_001.csv', 'r', encoding='utf-8') as f:
    rows = list(csv.DictReader(f))

print('Total rows:', len(rows))
print()
print('TOP 10:')
for r in rows[:10]:
    print(f"Rank {r['rank']}: {r['candidate_id']} | Score: {r['score']}")
    print(f"  Reasoning: {r['reasoning']}")
    print()