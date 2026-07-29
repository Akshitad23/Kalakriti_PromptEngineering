import csv
with open('kalakriti_scores_final.csv', encoding='utf-8') as f:
    rows = list(csv.DictReader(f))
print("Rows in CSV:", len(rows))
for r in rows[:5]:
    print("  rank=" + str(r.get("rank","?")) + "  team=" + r.get("team_id","?") + "  final=" + str(r.get("final_score_10","?")) + "  success=" + str(r.get("success","?")))
