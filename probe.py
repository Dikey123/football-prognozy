#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Пробник 3: собрать англ. названия команд по нашим лигам (для карты) и найти id Лиги Европы."""
import os, json, urllib.request, urllib.error, datetime

KEY = os.environ.get("API_FOOTBALL_KEY", "")
HOST = "free-api-live-football-data.p.rapidapi.com"

def get(path):
    url = "https://" + HOST + path
    req = urllib.request.Request(url, headers={"x-rapidapi-key": KEY, "x-rapidapi-host": HOST})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, (e.read().decode("utf-8", "replace")[:200] if True else "")
    except Exception as e:
        return 0, f"ERR {e}"

def matches(d):
    st, body = get(f"/football-get-matches-by-date?date={d}")
    try:
        return json.loads(body)["response"]["matches"]
    except Exception:
        return []

TARGET = {47: "epl", 87: "laliga", 55: "seriea", 54: "bundesliga", 53: "ligue1", 63: "rpl", 943230: "ucl"}
teams = {v: set() for v in TARGET.values()}
today = datetime.date.today()

for i in range(9):
    d = (today + datetime.timedelta(days=i)).strftime("%Y%m%d")
    for m in matches(d):
        key = TARGET.get(m.get("leagueId"))
        if key:
            teams[key].add(m["home"]["name"])
            teams[key].add(m["away"]["name"])

print("=== TEAM NAMES (англ) по лигам (на 9 дней вперёд) ===")
for k in ["ucl", "epl", "laliga", "seriea", "bundesliga", "ligue1", "rpl"]:
    print(f"\n## {k} ({len(teams[k])})")
    print(", ".join(sorted(teams[k])))

print("\n=== Поиск id Лиги Европы (четверги) ===")
for d in ["20261022", "20261023", "20261029", "20261030"]:
    seen = {}
    for m in matches(d):
        lid = m.get("leagueId")
        if isinstance(lid, int) and lid > 900000 and lid != 943230:
            seen.setdefault(lid, []).append(f'{m["home"]["name"]}-{m["away"]["name"]}')
    print(f"\n{d} крупные id:")
    for lid, exs in list(seen.items())[:12]:
        print(f"   {lid}: {exs[:3]}")

print("\n==== DONE3")
