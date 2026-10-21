#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Пробник 2: найти ID РПЛ и карту leagueId в матчах по дате."""
import os, json, urllib.request, urllib.error

KEY = os.environ.get("API_FOOTBALL_KEY", "")
HOST = "free-api-live-football-data.p.rapidapi.com"

def get(path):
    url = "https://" + HOST + path
    req = urllib.request.Request(url, headers={"x-rapidapi-key": KEY, "x-rapidapi-host": HOST})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read().decode("utf-8", "replace")[:300]
        except Exception:
            return e.code, ""
    except Exception as e:
        return 0, f"ERR {e}"

# 1) все лиги — найти нужные (особенно РПЛ)
st, body = get("/football-get-all-leagues")
print("ALL-LEAGUES status", st)
try:
    leagues = json.loads(body)["response"]["leagues"]
    print("total leagues:", len(leagues))
    kw = ["russia", "premier league", "laliga", "la liga", "serie a",
          "bundesliga", "ligue 1", "champions league", "europa league", "russian"]
    for lg in leagues:
        n = lg["name"].lower(); cc = lg.get("ccode", "")
        if any(k in n for k in kw) or cc == "RUS":
            print(f'  id={lg["id"]:>8}  ccode={cc:>4}  {lg["name"]}')
except Exception as e:
    print("parse err", e, body[:300])

# 2) матчи по дате — карта leagueId + полная структура
for d in ["20261021", "20261025"]:
    st, body = get(f"/football-get-matches-by-date?date={d}")
    print(f"\nMATCHES-BY-DATE {d} status {st} len {len(body)}")
    try:
        ms = json.loads(body)["response"]["matches"]
        print("  matches:", len(ms))
        seen = {}
        for m in ms:
            lid = m.get("leagueId")
            if lid not in seen:
                seen[lid] = f'{m["home"]["name"]} - {m["away"]["name"]}'
        for lid, ex in sorted(seen.items(), key=lambda x: str(x[0])):
            print(f'    leagueId={lid}: {ex}')
        print("  SAMPLE MATCH:", json.dumps(ms[0], ensure_ascii=False)[:1400])
    except Exception as e:
        print("  parse err", e, body[:200])

print("\n==== DONE2")
