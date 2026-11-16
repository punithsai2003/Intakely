"""Print contact-form messages saved by the site:  python scripts/show_messages.py"""
import os
import sqlite3
import time

db = os.environ.get("INTAKELY_DB", os.path.join(os.path.dirname(__file__), "..", "intakely.db"))
c = sqlite3.connect(db)
rows = c.execute("SELECT ts, first_name, last_name, email, phone, org, message FROM messages ORDER BY id DESC").fetchall()
if not rows:
    print("No messages yet.")
for ts, f, l, e, ph, org, m in rows:
    print(f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(ts))}  {f} {l}  <{e}>  {ph}  {org}\n    {m}\n")
