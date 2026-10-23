#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Автономный сбор базы (GitHub Actions): расписание, время, счёт, результаты.
Источник расписания и результатов: free-api-live-football-data (RapidAPI).
Прогнозы с сайтов собирает отдельный collect_tips.py. По умолчанию DRY-RUN
(без записи); DRY_RUN=0 включает запись."""
import os, json, time, urllib.request, urllib.error, datetime, subprocess

KEY = os.environ.get("API_FOOTBALL_KEY", "")
HOST = "free-api-live-football-data.p.rapidapi.com"
DRY = os.environ.get("DRY_RUN", "1") == "1"
DAY_OFFSETS = (-2, -1, 4)  # два прошлых дня и новый крайний день расписания

LEAGUES = {47:"epl",87:"laliga",55:"seriea",54:"bundesliga",53:"ligue1",63:"rpl",943230:"ucl",943229:"uel"}

TEAM = {
 "Arsenal":"Арсенал","Aston Villa":"Астон Вилла","Bayern München":"Бавария","Real Betis":"Бетис",
 "Club Brugge":"Брюгге","Viking":"Викинг","Galatasaray":"Галатасарай","Inter":"Интер","Como":"Комо",
 "LASK":"ЛАСК","Lens":"Ланс","RB Leipzig":"Лейпциг","Lille":"Лилль","Manchester United":"Манчестер Юнайтед",
 "Real Madrid":"Реал Мадрид","Sporting CP":"Спортинг","Feyenoord":"Фейеноорд","Shakhtar Donetsk":"Шахтёр",
 "AEK Athens":"АЕК","Atlético Madrid":"Атлетико Мадрид","Barcelona":"Барселона","Bodø/Glimt":"Буде-Глимт",
 "FC Porto":"Порту","Liverpool":"Ливерпуль","Manchester City":"Манчестер Сити","Napoli":"Наполи",
 "PSV Eindhoven":"ПСВ","Paris Saint-Germain":"ПСЖ","Roma":"Рома","Slovan Bratislava":"Слован",
 "VfB Stuttgart":"Штутгарт","Villarreal":"Вильярреал",
 # UEL
 "AZ Alkmaar":"Алкмаар","Anderlecht":"Андерлехт","Ararat Armenia":"Арарат-Армения","Bayer Leverkusen":"Байер",
 "Benfica":"Бенфика","Beşiktaş":"Бешикташ","AFC Bournemouth":"Борнмут","Dinamo Zagreb":"Динамо Загреб",
 "Crystal Palace":"Кристал Пэлас","Lyon":"Лион","Marseille":"Марсель","Milan":"Милан",
 "NEC Nijmegen":"Неймеген","Olympiacos":"Олимпиакос","Real Sociedad":"Реал Сосьедад","Rennes":"Ренн",
 "Sunderland":"Сандерленд","Celtic":"Селтик","Celta Vigo":"Сельта","Torreense":"Торреенсе",
 "Ferencváros":"Ференцварош","Hoffenheim":"Хоффенхайм","Sturm Graz":"Штурм","Juventus":"Ювентус",
 "Hapoel Beer Sheva":"Хапоэль Беэр-Шева","Jagiellonia Białystok":"Ягеллония","Lech Poznań":"Лех",
 "Levski Sofia":"Левски","Lillestrøm":"Лиллестрём","NK Celje":"Целе","OFI Crete":"ОФИ",
 "Omonia Nicosia":"Омония","Salzburg":"Зальцбург","Sparta Prague":"Спарта Прага",
 "Union St.Gilloise":"Юнион Сен-Жиллуаз","Viktoria Plzeň":"Виктория Пльзень",
 # EPL
 "Brighton & Hove Albion":"Брайтон","Brentford":"Брентфорд","Ipswich Town":"Ипсвич","Coventry City":"Ковентри",
 "Leeds United":"Лидс","Nottingham Forest":"Ноттингем Форест","Newcastle United":"Ньюкасл","Tottenham Hotspur":"Тоттенхэм",
 "Fulham":"Фулхэм","Hull City":"Халл","Chelsea":"Челси","Everton":"Эвертон",
 # LaLiga
 "Deportivo Alavés":"Алавес","Athletic Club":"Атлетик","Valencia":"Валенсия","Deportivo A Coruña":"Депортиво",
 "Levante":"Леванте","Málaga":"Малага","Osasuna":"Осасуна","Rayo Vallecano":"Райо Вальекано","Racing Santander":"Расинг",
 "Sevilla":"Севилья","Getafe":"Хетафе","Elche":"Эльче","Espanyol":"Эспаньол",
 # SerieA
 "Atalanta":"Аталанта","Bologna":"Болонья","Venezia":"Венеция","Genoa":"Дженоа","Cagliari":"Кальяри",
 "Lazio":"Лацио","Lecce":"Лечче","Monza":"Монца","Parma":"Парма","Sassuolo":"Сассуоло","Torino":"Торино",
 "Udinese":"Удинезе","Fiorentina":"Фиорентина","Frosinone":"Фрозиноне",
 # Bundesliga
 "Eintracht Frankfurt":"Айнтрахт Франкфурт","Augsburg":"Аугсбург","Borussia Dortmund":"Боруссия Дортмунд",
 "Borussia Mönchengladbach":"Боруссия Мёнхенгладбах","Werder Bremen":"Вердер","Hamburger SV":"Гамбург",
 "1. FC Köln":"Кёльн","Mainz 05":"Майнц","Paderborn":"Падерборн","Union Berlin":"Унион Берлин","Freiburg":"Фрайбург",
 "Schalke 04":"Шальке","Elversberg":"Эльферсберг",
 # Ligue1
 "Angers":"Анже","Brest":"Брест","Le Havre":"Гавр","Le Mans":"Ле-Ман","Lorient":"Лорьян","Monaco":"Монако",
 "Nice":"Ницца","Auxerre":"Осер","Paris FC":"Париж","Strasbourg":"Страсбур","Troyes":"Труа","Toulouse":"Тулуза",
 # RPL
 "Akron Togliatti":"Акрон","FK Akhmat":"Ахмат","Baltika":"Балтика","Dinamo Moscow":"Динамо",
 "Dynamo Makhachkala":"Динамо (Махачкала)","Zenit St. Petersburg":"Зенит","FC Krasnodar":"Краснодар",
 "Krylya Sovetov Samara":"Крылья Советов","Lokomotiv Moscow":"Локомотив","FC Orenburg":"Оренбург",
 "Rodina":"Родина","FC Rostov":"Ростов","Rubin Kazan":"Рубин","Spartak Moscow":"Спартак","Fakel":"Факел","CSKA Moscow":"ЦСКА",
}

def get(path):
    req = urllib.request.Request("https://"+HOST+path, headers={"x-rapidapi-key":KEY,"x-rapidapi-host":HOST})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read().decode("utf-8","replace"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace").strip()
        headers = e.headers or {}
        details = body or str(e.reason)
        retry_after = headers.get("Retry-After")
        remaining = headers.get("X-RapidAPI-Requests-Remaining") or headers.get("X-Ratelimit-Requests-Remaining")
        if retry_after:
            details += f" (Retry-After: {retry_after}s)"
        if remaining is not None:
            details += f" (requests remaining: {remaining})"
        return {"_err": f"HTTP Error {e.code}: {details}", "_status": e.code}
    except Exception as e:
        return {"_err": str(e)}

def msk(utc):
    dt = datetime.datetime.strptime(utc[:19], "%Y-%m-%dT%H:%M:%S") + datetime.timedelta(hours=3)
    return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")

def norm(s):
    return s.replace("РБ ","").replace("ФК ","").lower().replace(" ","").replace("-","").replace("ё","е")

data = json.load(open("data.json"))
tour = {t["id"]: t for t in data["tournaments"]}

def find_match(tid, hr, ar):
    t = tour.get(tid)
    if not t: return None
    nh, na = norm(hr), norm(ar)
    for m in t["matches"]:
        if norm(m["home"]) == nh and norm(m["away"]) == na:
            return m
    return None

today = datetime.datetime.now(
    datetime.timezone(datetime.timedelta(hours=3))).date()
today_s = today.strftime("%Y-%m-%d")
updated = added = 0
scores = {}       # для settle: {рус_хозяева: "2:1"}
unmapped = set()
errors = []
got_response = False

for request_index, offset in enumerate(DAY_OFFSETS):
    if request_index:
        time.sleep(1.2)  # не отправляем несколько запросов подряд в RapidAPI
    d = (today + datetime.timedelta(days=offset)).strftime("%Y%m%d")
    resp = get(f"/football-get-matches-by-date?date={d}")
    if "_err" in resp or resp.get("status") == "failed":
        errors.append(f"{d}: {resp.get('_err') or resp.get('message')}")
        print("ERR", d, resp.get("_err") or resp.get("message"))
        if resp.get("_status") == 429:
            print("Остановка запросов: достигнут лимит API (HTTP 429).")
            break
        continue
    got_response = True
    for m in resp.get("response", {}).get("matches", []):
        tid = LEAGUES.get(m.get("leagueId"))
        if not tid: continue
        hr, ar = TEAM.get(m["home"]["name"]), TEAM.get(m["away"]["name"])
        if not hr: unmapped.add(f'{tid}:{m["home"]["name"]}')
        if not ar: unmapped.add(f'{tid}:{m["away"]["name"]}')
        if not hr or not ar: continue
        st = m.get("status", {})
        if not st.get("utcTime"): continue
        dd, tt = msk(st["utcTime"])
        fin = bool(st.get("finished"))
        sc = st.get("scoreStr", "").replace(" ", "")
        ft = sc.replace("-", ":") if ("-" in sc) else (sc if ":" in sc else None)
        ex = find_match(tid, hr, ar)
        if ex:
            if ex.get("status") == "fixture":   # уточняем дату/время только для ещё не оформленных
                ex["date"], ex["time"] = dd, tt
            if fin and ft:
                ex["ft"] = ft
                ex["status"] = "full"
                scores[hr] = ft               # счёт для settle (сработает, если матч обогащён)
            updated += 1
        else:
            if fin:       # прошедший матч без карточки не добавляем как «расписание»
                continue
            if dd < today_s:
                continue  # уже в прошлом
            nm = {"date": dd, "time": tt, "home": hr, "away": ar, "status": "fixture"}
            tour[tid]["matches"].append(nm)
            added += 1

summary = f"updated={updated} added={added} finished_scores={len(scores)} unmapped={len(unmapped)} errors={len(errors)} got_response={got_response} DRY={DRY}"
print(summary)
if unmapped:
    print("UNMAPPED:", sorted(unmapped))
try:
    with open("fetch_log.txt", "w", encoding="utf-8") as f:
        f.write(datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z") + "\n" + summary + "\n")
        if errors:
            f.write("ERRORS:\n" + "\n".join(errors) + "\n")
        if unmapped:
            f.write("UNMAPPED: " + ", ".join(sorted(unmapped)) + "\n")
except Exception:
    pass

if DRY:
    print("DRY RUN — запись не выполнялась")
    if errors:
        raise SystemExit("API ответил ошибками; см. журнал выше.")
    print("==== DONE5")
elif errors:
    print("Обновление отменено: API вернул неполный набор ответов, существующие данные сохранены.")
    raise SystemExit("Сбор данных не завершён — проверьте лимит и ключ API.")
elif not got_response:
    print("Ни одного успешного ответа API — data.json НЕ трогаем (вероятно лимит API).")
    raise SystemExit("API не вернул матчи; существующие данные сохранены.")
else:
    for t in data["tournaments"]:
        t["matches"].sort(key=lambda x: (x.get("date", ""), x.get("time", "")))
    data["today"] = today_s
    data["updated"] = datetime.datetime.now(
        datetime.timezone(datetime.timedelta(hours=3))).strftime("%Y-%m-%dT%H:%M:%S+03:00")
    json.dump(data, open("data.json", "w"), ensure_ascii=False, indent=1)
    print("data.json записан.")
    if scores:
        json.dump(scores, open("scores_api.json", "w"), ensure_ascii=False)
        try:
            r = subprocess.run(["python3", "settle.py", "data.json", "scores_api.json", "results.json"],
                               capture_output=True, text=True, timeout=120)
            print("settle stdout:", (r.stdout or "")[-600:])
            if r.stderr: print("settle stderr:", r.stderr[-300:])
        except Exception as e:
            print("settle err:", e)
    print("==== DONE5")
