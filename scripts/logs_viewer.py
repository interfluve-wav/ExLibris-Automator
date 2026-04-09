"""
CLI to view submission logs from a CSV file (default: data.csv) and print a
compact table of Title and Submitted Date.
"""
import csv
import os
import argparse
from datetime import datetime

def read_logs(path='data.csv'):
    if not os.path.exists(path):
        print(f"No log file found at: {path}")
        return []
    with open(path, newline='', encoding='utf-8') as f:
        rdr = csv.DictReader(f)
        return list(rdr)

def print_table(rows, limit=None):
    if not rows:
        print("No logs."); return
    if limit:
        rows = rows[-limit:]
    title_w = max(5, min(80, max(len(r['Title']) for r in rows)))
    date_w = 19
    print(f"{'Title'.ljust(title_w)}  {'Submitted Date'.ljust(date_w)}")
    print(f"{'-'*title_w}  {'-'*date_w}")
    for r in rows:
        title = (r['Title'][:title_w-1] + '…') if len(r['Title']) > title_w else r['Title']
        print(f"{title.ljust(title_w)}  {r['Submitted Date'].ljust(date_w)}")

def main():
    ap = argparse.ArgumentParser(description="View submission logs from data.csv.")
    ap.add_argument('--path', default='data.csv', help='Path to log file.')
    ap.add_argument('--tail', type=int, default=20, help='Show last N entries.')
    args = ap.parse_args()
    rows = read_logs(args.path)
    print_table(rows, limit=args.tail)

if __name__ == "__main__":
    main()

