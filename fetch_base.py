#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Автономный сбор базы (GitHub Actions): расписание, время, счёт, результаты.
Основной источник — free-api-live-football-data (RapidAPI); ESPN scoreboard
подхватывает результаты за два прошлых дня и расписание на четыре дня вперёд,
если основной API недоступен или исчерпал квоту.
Прогнозы с сайтов собирает отдельный collect_tips.py. По умолчанию DRY-RUN
(без записи); DRY_RUN=0 включает запись."""
import os, json, time, re, unicodedata, urllib.request, urllib.error, datetime, subprocess
from urllib.parse import urlencode

KEY = os.environ.get("API_FOOTBALL_KEY", "")
ODDS_API_KEY = os.environ.get("ODDS_API_KEY", "")
ODDS_REGIONS = os.environ.get("ODDS_REGIONS", "eu")
ODDS_SPORTS = {
    "epl": "soccer_epl", "laliga": "soccer_spain_la_liga",
    "seriea": "soccer_italy_serie_a", "bundesliga": "soccer_germany_bundesliga",
    "ligue1": "soccer_france_ligue_one", "rpl": "soccer_russia_premier_league",
    "ucl": "soccer_uefa_champs_league", "uel": "soccer_uefa_europa_league",
}
HOST = "free-api-live-football-data.p.rapidapi.com"
DRY = os.environ.get("DRY_RUN", "1") == "1"
DAY_OFFSETS = (-2, -1, 4)  # два прошлых дня и новый крайний день расписания

LEAGUES = {47:"epl",87:"laliga",55:"seriea",54:"bundesliga",53:"ligue1",63:"rpl",943230:"ucl",943229:"uel"}
ESPN_LEAGUES = {
    "eng.1": "epl", "esp.1": "laliga", "ita.1": "seriea",
    "ger.1": "bundesliga", "fra.1": "ligue1", "rus.1": "rpl",
    "uefa.champions": "ucl", "uefa.europa": "uel",
}

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

def normalized_team_name(value):
    value = str(value or "").casefold().translate(str.maketrans({
        "ł": "l", "ø": "o", "æ": "ae", "œ": "oe", "ß": "ss",
    }))
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"\b(?:fc|afc|cf|sc|ac|as|club|rb|nk|fk)\b", "", value)
    return re.sub(r"[^a-z0-9]", "", value)

TEAM_BY_ESPN_NAME = {normalized_team_name(source): target for source, target in TEAM.items()}
TEAM_BY_ESPN_NAME.update({
    "manutd": "Манчестер Юнайтед", "manunited": "Манчестер Юнайтед",
    "mancity": "Манчестер Сити", "athleticbilbao": "Атлетик",
    "intermilan": "Интер", "internazionale": "Интер",
    "bayernmunich": "Бавария", "parissaintgermain": "ПСЖ",
    "lasklinz": "ЛАСК", "hapoelbeer": "Хапоэль Беэр-Шева",
    "akhmatgrozny": "Ахмат", "akrontolyatti": "Акрон", "alaves": "Алавес",
    "deportivo": "Депортиво", "cologne": "Кёльн", "fakelvoronezh": "Факел",
    "hamburgsv": "Гамбург", "krylyasovetov": "Крылья Советов",
    "kryliyasovetov": "Крылья Советов", "rodinamoscow": "Родина",
    "baltikakaliningrad": "Балтика", "krylyasovetov": "Крылья Советов",
    "mainz": "Майнц",
    "psg": "ПСЖ", "barcelona": "Барселона", "realmadrid": "Реал Мадрид",
})

def espn_team_name(team):
    """Translate ESPN's English display names to the Russian team labels in data.json."""
    if isinstance(team, dict):
        candidates = (team.get("displayName"), team.get("name"), team.get("shortDisplayName"))
    else:
        candidates = (team,)
    for candidate in candidates:
        if not candidate:
            continue
        mapped = TEAM_BY_ESPN_NAME.get(normalized_team_name(candidate))
        if mapped:
            return mapped
    return None

def fetch_espn_matches(today):
    """Free fallback for recent results and the next four days of fixtures."""
    results = {}
    seen = set()
    responded = 0
    updated = added = 0
    unmapped = set()
    failures = []
    offsets = (-2, -1, 0, 1, 2, 3, 4)
    target_dates = {(today + datetime.timedelta(days=x)).strftime("%Y-%m-%d") for x in offsets}
    for league, tid in ESPN_LEAGUES.items():
        for offset in offsets:
            day = today + datetime.timedelta(days=offset)
            date_key = day.strftime("%Y%m%d")
            url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league}/scoreboard?dates={date_key}"
            req = urllib.request.Request(url, headers={
                "User-Agent": "FootballForecastCollector/1.0",
                "Accept": "application/json",
            })
            try:
                with urllib.request.urlopen(req, timeout=20) as response:
                    payload = json.loads(response.read().decode("utf-8", "replace"))
                responded += 1
            except Exception as exc:
                failures.append(f"ESPN {league} {date_key}: {exc}")
                continue

            for event in payload.get("events", []):
                event_date = event.get("date")
                try:
                    kickoff = datetime.datetime.fromisoformat(event_date.replace("Z", "+00:00"))
                    if kickoff.tzinfo is None:
                        kickoff = kickoff.replace(tzinfo=datetime.timezone.utc)
                    local_date = kickoff.astimezone(datetime.timezone(datetime.timedelta(hours=3))).strftime("%Y-%m-%d")
                    local_time = kickoff.astimezone(datetime.timezone(datetime.timedelta(hours=3))).strftime("%H:%M")
                except (AttributeError, TypeError, ValueError):
                    continue
                if local_date not in target_dates:
                    continue

                competitions = event.get("competitions") or []
                if not competitions:
                    continue
                competition = competitions[0]
                status_container = competition.get("status") or event.get("status") or {}
                status = status_container.get("type") or {}
                status_name = str(status.get("name") or "").upper()
                if "CANCEL" in status_name or "POSTPON" in status_name:
                    continue
                finished = bool(status.get("completed") or status.get("state") == "post")

                home = away = None
                home_score = away_score = None
                for competitor in competition.get("competitors", []):
                    side = competitor.get("homeAway")
                    mapped_name = espn_team_name(competitor.get("team", {}))
                    score = str(competitor.get("score", ""))
                    if side == "home":
                        home, home_score = mapped_name, score
                    elif side == "away":
                        away, away_score = mapped_name, score
                if not home or not away:
                    for competitor in competition.get("competitors", []):
                        raw_team = competitor.get("team", {})
                        if not espn_team_name(raw_team):
                            unmapped.add(str(raw_team.get("displayName") or raw_team.get("name") or "?"))
                    continue
                key = (tid, local_date, home, away)
                if key in seen:
                    continue
                seen.add(key)
                match = next((m for m in tour[tid]["matches"]
                              if m.get("home") == home and m.get("away") == away
                              and m.get("date") == local_date), None)

                if finished and home_score.isdigit() and away_score.isdigit():
                    score = f"{home_score}:{away_score}"
                    if match is None:
                        match = {"date": local_date, "time": local_time, "home": home,
                                 "away": away, "status": "full", "ft": score}
                        tour[tid]["matches"].append(match)
                        added += 1
                    else:
                        match["ft"] = score
                        match["status"] = "full"
                        updated += 1
                    results[home] = score
                elif local_date >= today.isoformat():
                    if match is None:
                        tour[tid]["matches"].append({"date": local_date, "time": local_time,
                            "home": home, "away": away, "status": "fixture"})
                        added += 1
                    elif match.get("status") != "full":
                        match["date"], match["time"], match["status"] = local_date, local_time, "fixture"
                        updated += 1

    print(f"ESPN fallback: responses={responded}/{len(ESPN_LEAGUES) * len(offsets)} updated={updated} added={added} finished_scores={len(results)} unmapped={len(unmapped)} errors={len(failures)}")
    if unmapped:
        print("ESPN UNMAPPED:", sorted(unmapped))
    if failures:
        print("ESPN ERRORS:", " | ".join(failures[:8]))
    return results, responded > 0, updated, added, unmapped


def fetch_open_odds():
    """Обновляет коэффициенты 1X2 из открытого агрегатора букмекерских котировок."""
    if not ODDS_API_KEY:
        print("ODDS: пропуск — секрет ODDS_API_KEY не задан.")
        return 0

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    updated = quotes_total = 0
    unmapped = set()
    failures = []
    remaining = None

    for tid, sport in ODDS_SPORTS.items():
        query = urlencode({
            "apiKey": ODDS_API_KEY,
            "regions": ODDS_REGIONS,
            "markets": "h2h",
            "oddsFormat": "decimal",
            "dateFormat": "iso",
        })
        url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds/?{query}"
        req = urllib.request.Request(url, headers={
            "User-Agent": "FootballForecastCollector/1.0",
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                remaining = response.headers.get("x-requests-remaining", remaining)
                payload = json.loads(response.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:200]
            failures.append(f"{sport}: HTTP {exc.code} {body}")
            if exc.code == 429:
                break
            continue
        except Exception as exc:
            failures.append(f"{sport}: {exc}")
            continue

        if not isinstance(payload, list):
            failures.append(f"{sport}: неожиданный формат ответа")
            continue

        # Удаляем вчерашние значения только для лиги, если API ответил успешно.
        # При сетевой ошибке старые значения сохраняются и видна дата котировки.
        for old_match in tour.get(tid, {}).get("matches", []):
            if not old_match.get("ft") and old_match.get("status") != "full":
                old_match.pop("odds", None)
                old_match.pop("odds_sources", None)
                old_match.pop("odds_updated", None)
                old_match.pop("odds_provider", None)

        for event in payload:
            try:
                kickoff = datetime.datetime.fromisoformat(
                    str(event.get("commence_time", "")).replace("Z", "+00:00")
                )
                if kickoff.tzinfo is None:
                    kickoff = kickoff.replace(tzinfo=datetime.timezone.utc)
                if kickoff <= now_utc:
                    continue
                local_date = kickoff.astimezone(
                    datetime.timezone(datetime.timedelta(hours=3))
                ).strftime("%Y-%m-%d")
            except (AttributeError, TypeError, ValueError):
                continue

            raw_home, raw_away = event.get("home_team"), event.get("away_team")
            home, away = espn_team_name(raw_home), espn_team_name(raw_away)
            if not home or not away:
                if raw_home and not home:
                    unmapped.add(str(raw_home))
                if raw_away and not away:
                    unmapped.add(str(raw_away))
                continue
            match = next((item for item in tour[tid]["matches"]
                          if item.get("date") == local_date
                          and item.get("home") == home
                          and item.get("away") == away), None)
            if not match or match.get("ft"):
                continue

            source_quotes = []
            for bookmaker in event.get("bookmakers") or []:
                values = [None, None, None]
                quote_updated = bookmaker.get("last_update", "")
                for market_data in bookmaker.get("markets") or []:
                    if market_data.get("key") != "h2h":
                        continue
                    quote_updated = market_data.get("last_update") or quote_updated
                    for outcome in market_data.get("outcomes") or []:
                        outcome_name = str(outcome.get("name") or "")
                        outcome_norm = normalized_team_name(outcome_name)
                        mapped_outcome = espn_team_name(outcome_name)
                        if outcome_norm == normalized_team_name(raw_home) or mapped_outcome == home:
                            index = 0
                        elif outcome_norm == normalized_team_name(raw_away) or mapped_outcome == away:
                            index = 2
                        elif outcome_name.casefold().strip() in {"draw", "the draw", "tie", "x"}:
                            index = 1
                        else:
                            continue
                        try:
                            price = float(outcome.get("price"))
                        except (TypeError, ValueError):
                            continue
                        if 1.01 < price < 100:
                            values[index] = round(price, 2)
                if any(value is not None for value in values):
                    source_quotes.append({
                        "name": bookmaker.get("title") or bookmaker.get("key") or "Букмекер",
                        "odds": values,
                        "updated": quote_updated,
                    })

            if not source_quotes:
                continue
            best = []
            for index in range(3):
                available = [quote["odds"][index] for quote in source_quotes
                             if quote["odds"][index] is not None]
                best.append(max(available) if available else None)
            source_quotes.sort(key=lambda quote: quote["name"].casefold())
            match["odds"] = best
            match["odds_sources"] = source_quotes
            match["odds_updated"] = max(
                (quote["updated"] for quote in source_quotes if quote.get("updated")),
                default="",
            )
            match["odds_provider"] = "The Odds API"
            updated += 1
            quotes_total += len(source_quotes)

    if updated:
        data["odds_updated"] = datetime.datetime.now(
            datetime.timezone(datetime.timedelta(hours=3))
        ).strftime("%Y-%m-%dT%H:%M:%S+03:00")
    print(
        f"ODDS: updated_matches={updated} bookmaker_quotes={quotes_total} "
        f"remaining_credits={remaining or 'unknown'} errors={len(failures)}"
    )
    if failures:
        print("ODDS ERRORS:", " | ".join(failures[:8]))
    if unmapped:
        print("ODDS UNMAPPED:", sorted(unmapped))
    return updated

data = json.load(open("data.json"))
tour = {t["id"]: t for t in data["tournaments"]}
original_data = json.loads(json.dumps(data))

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
fallback_ok = False
if errors:
    print("RapidAPI returned errors; restoring the previous schedule and trying ESPN for recent results.")
    data = original_data
    tour = {t["id"]: t for t in data["tournaments"]}
    updated = added = 0
    scores = {}
    espn_scores, fallback_ok, updated, added, espn_unmapped = fetch_espn_matches(today)
    scores.update(espn_scores)
    unmapped.update(espn_unmapped)
    got_response = got_response or fallback_ok
    summary = f"updated={updated} added={added} finished_scores={len(scores)} unmapped={len(unmapped)} errors={len(errors)} espn_fallback={fallback_ok} DRY={DRY}"
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
    if errors and not fallback_ok:
        raise SystemExit("Основной и резервный источники не ответили; см. журнал выше.")
    print("==== DONE5")
elif errors and not fallback_ok:
    print("Обновление отменено: основной и резервный источники не вернули данные; существующие файлы сохранены.")
    raise SystemExit("Сбор данных не завершён — проверьте лимиты API и доступность источников.")
elif not got_response:
    print("Ни одного успешного ответа API — data.json НЕ трогаем (вероятно лимит API).")
    raise SystemExit("API не вернул матчи; существующие данные сохранены.")
else:
    fetch_open_odds()
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

