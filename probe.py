#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Пробник эндпоинтов free-api-live-football-data (RapidAPI).
Опрашивает несколько вероятных путей, печатает статус и начало ответа.
Запускается в GitHub Actions, результат коммитится в probe_out.txt."""
import os, json, urllib.request, urllib.error, datetime

KEY = os.environ.get("API_FOOTBALL_KEY", "")
HOST = "free-api-live-football-data.p.rapidapi.com"

def call(path):
    url = "https://" + HOST + path
    req = urllib.request.Request(url, headers={
        "x-rapidapi-key": KEY, "x-rapidapi-host": HOST})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            body = r.read().decode("utf-8", "replace")
            print(f"\n==== {path}\nSTATUS {r.status}  len={len(body)}\n{body[:2200]}")
    except urllib.error.HTTPError as e:
        try:
            msg = e.read().decode("utf-8", "replace")[:400]
        except Exception:
            msg = ""
        print(f"\n==== {path}\nHTTP {e.code}: {msg}")
    except Exception as e:
        print(f"\n==== {path}\nERR {type(e).__name__}: {e}")

today = datetime.date.today()
d1 = today.strftime("%Y%m%d")
d2 = today.strftime("%Y-%m-%d")

paths = [
    # лиги
    "/football-get-all-leagues",
    "/football-get-all-popular-leagues",
    "/football-get-popular-leagues",
    "/football-popular-leagues",
    "/football-leagues",
    # страны
    "/football-get-all-countries",
    "/football-get-countries",
    # матчи по дате
    f"/football-get-matches-by-date?date={d1}",
    f"/football-get-all-matches-by-date?date={d1}",
    f"/football-get-matches-by-date?date={d2}",
    f"/football-get-matches?date={d1}",
    # лайв
    "/football-get-live-matches",
    "/football-get-all-live-matches",
    "/football-live-matches",
    # матчи лиги (leagueid наугад — проверка формата/ошибки)
    "/football-get-matches-by-league?leagueid=42",
    "/football-get-all-matches-by-league?leagueid=42",
    "/football-get-league-matches?leagueid=42",
    "/football-league-detail?leagueid=42",
    "/football-get-standings?leagueid=42",
]

print("PROBE", datetime.datetime.utcnow().isoformat(), "key_set:", bool(KEY))
for p in paths:
    call(p)
print("\n==== DONE")
