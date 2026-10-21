#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Пробник: найти эндпоинт коэффициентов (odds) и лайв-структуру."""
import os, json, urllib.request, urllib.error, datetime

KEY = os.environ.get("API_FOOTBALL_KEY", "")
HOST = "free-api-live-football-data.p.rapidapi.com"

def get(path):
    req = urllib.request.Request("https://"+HOST+path, headers={"x-rapidapi-key":KEY,"x-rapidapi-host":HOST})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, r.read().decode("utf-8","replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8","replace")[:200]
    except Exception as e:
        return 0, f"ERR {e}"

# взять id ближайшего матча (завтра)
tom = (datetime.date.today()+datetime.timedelta(days=1)).strftime("%Y%m%d")
st, body = get(f"/football-get-matches-by-date?date={tom}")
mid = None
try:
    ms = json.loads(body)["response"]["matches"]
    for m in ms:
        if m.get("leagueId") in (47,87,55,54,53,63,943230,943229) and not m["status"].get("finished"):
            mid = m["id"]; print("sample match:", mid, m["home"]["name"],"-",m["away"]["name"]); break
    if not mid and ms: mid = ms[0]["id"]; print("fallback match:", mid)
except Exception as e:
    print("no match id", e)

cands = [
    f"/football-get-match-odds?eventid={mid}",
    f"/football-get-odds?eventid={mid}",
    f"/football-get-all-odds?eventid={mid}",
    f"/football-get-match-all-odds?eventid={mid}",
    f"/football-get-match-event-odds?eventid={mid}",
    f"/football-get-match-event-all-odds?eventid={mid}",
    f"/football-get-event-odds?eventid={mid}",
    f"/football-get-odds-by-match?eventid={mid}",
    f"/football-get-match-detail?eventid={mid}",
    f"/football-get-match-event-all-stats?eventid={mid}",
    # live
    "/football-get-all-live-match",
    "/football-get-live-match",
    "/football-get-livescores",
]
for p in cands:
    st, body = get(p)
    print(f"\n==== {p}\nstatus {st}\n{body[:700]}")

print("\n==== DONEP")
