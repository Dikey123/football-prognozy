#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Пробник 2: полный match-detail + структура лайв-матча + эндпоинты лайва."""
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

# 1) полный match-detail (ищем odds/lineup/live)
st, body = get("/football-get-match-detail?eventid=6106285")
print("=== MATCH-DETAIL (ключи верхнего уровня) ===", st)
try:
    det = json.loads(body)["response"]["detail"]
    print("detail keys:", list(det.keys()))
    for k in ("matchStatus","status","time","odds","liveTime","started","finished","score"):
        if k in det:
            print(f"  {k}:", json.dumps(det[k], ensure_ascii=False)[:300])
except Exception as e:
    print("parse err", e, body[:500])

# 2) сегодняшние матчи — найти ЛАЙВ (started && !finished) и показать статус
today = datetime.date.today().strftime("%Y%m%d")
st, body = get(f"/football-get-matches-by-date?date={today}")
print("\n=== СЕГОДНЯ: лайв/недавние матчи топ-лиг ===")
try:
    ms = json.loads(body)["response"]["matches"]
    cnt = 0
    for m in ms:
        if m.get("leagueId") in (47,87,55,54,53,63,943230,943229):
            s = m["status"]
            live = s.get("started") and not s.get("finished")
            if live or cnt < 4:
                print(f'  {m["home"]["name"]} {m["home"].get("score")}-{m["away"].get("score")} {m["away"]["name"]} '
                      f'| started={s.get("started")} finished={s.get("finished")} live={live}')
                print(f'     status: {json.dumps(s, ensure_ascii=False)[:420]}')
                cnt += 1
except Exception as e:
    print("parse err", e, body[:300])

# 3) кандидаты лайв-эндпоинтов
print("\n=== LIVE endpoints ===")
for p in ["/football-get-live","/football-livescores","/football-get-all-livescore",
          "/football-get-live-score","/football-all-live","/football-current-matches",
          "/football-get-all-matches-live","/football-live"]:
    st, b = get(p)
    print(f"  {p} -> {st}  {b[:90]}")

print("\n==== DONEP")
