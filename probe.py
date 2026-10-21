#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DRY-RUN: сверка матчей API с data.json. Ничего не пишет, только отчёт."""
import os, json, urllib.request, urllib.error, datetime

KEY = os.environ.get("API_FOOTBALL_KEY", "")
HOST = "free-api-live-football-data.p.rapidapi.com"
LEAGUES = {47:"epl",87:"laliga",55:"seriea",54:"bundesliga",53:"ligue1",63:"rpl",943230:"ucl",943229:"uel"}

TEAM = {
 # euro + overlaps
 "Arsenal":"Арсенал","Aston Villa":"Астон Вилла","Bayern München":"Бавария","Real Betis":"Бетис",
 "Club Brugge":"Брюгге","Viking":"Викинг","Galatasaray":"Галатасарай","Inter":"Интер","Como":"Комо",
 "LASK":"ЛАСК","Lens":"Ланс","RB Leipzig":"Лейпциг","Lille":"Лилль","Manchester United":"Манчестер Юнайтед",
 "Real Madrid":"Реал Мадрид","Sporting CP":"Спортинг","Feyenoord":"Фейеноорд","Shakhtar Donetsk":"Шахтёр",
 "AEK Athens":"АЕК","Atlético Madrid":"Атлетико Мадрид","Barcelona":"Барселона","Bodø/Glimt":"Буде-Глимт",
 "FC Porto":"Порту","Liverpool":"Ливерпуль","Manchester City":"Манчестер Сити","Napoli":"Наполи",
 "PSV Eindhoven":"ПСВ","Paris Saint-Germain":"ПСЖ","Roma":"Рома","Slovan Bratislava":"Слован",
 "VfB Stuttgart":"Штутгарт","Villarreal":"Вильярреал",
 # UEL (часть названий — предположения, dry-run покажет недостающие)
 "AZ Alkmaar":"Алкмаар","Anderlecht":"Андерлехт","Ararat Armenia":"Арарат-Армения","Bayer Leverkusen":"Байер",
 "Benfica":"Бенфика","Beşiktaş":"Бешикташ","AFC Bournemouth":"Борнмут","Dinamo Zagreb":"Динамо Загреб",
 "Crystal Palace":"Кристал Пэлас","Lyon":"Лион","Marseille":"Марсель","Milan":"Милан",
 "NEC Nijmegen":"Неймеген","Olympiacos":"Олимпиакос","Real Sociedad":"Реал Сосьедад","Rennes":"Ренн",
 "Sunderland":"Сандерленд","Celtic":"Селтик","Celta Vigo":"Сельта","Torreense":"Торреенсе",
 "Ferencváros":"Ференцварош","Hoffenheim":"Хоффенхайм","Sturm Graz":"Штурм","Juventus":"Ювентус",
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
    except Exception as e:
        return {"_err": str(e)}

def norm(s):
    return s.replace("РБ ","").replace("ФК ","").lower().replace(" ","").replace("-","").replace("ё","е")

data = json.load(open("data.json"))
existing = {}
for t in data["tournaments"]:
    for m in t["matches"]:
        existing[(t["id"], norm(m["home"]), norm(m["away"]))] = m

today = datetime.date.today()
unmapped = {}
byl = {}
for i in range(7):
    d = (today + datetime.timedelta(days=i)).strftime("%Y%m%d")
    resp = get(f"/football-get-matches-by-date?date={d}")
    for m in resp.get("response", {}).get("matches", []):
        tid = LEAGUES.get(m.get("leagueId"))
        if not tid:
            continue
        he, ae = m["home"]["name"], m["away"]["name"]
        hr, ar = TEAM.get(he), TEAM.get(ae)
        if not hr:
            unmapped.setdefault(tid, set()).add(he)
        if not ar:
            unmapped.setdefault(tid, set()).add(ae)
        if not hr or not ar:
            continue
        byl.setdefault(tid, {"matched":0,"new":0,"new_ex":[]})
        if (tid, norm(hr), norm(ar)) in existing:
            byl[tid]["matched"] += 1
        else:
            byl[tid]["new"] += 1
            if len(byl[tid]["new_ex"]) < 4:
                byl[tid]["new_ex"].append(f"{hr} — {ar} ({d})")

print("=== DRY RUN REPORT ===")
for tid in ["ucl","uel","epl","laliga","seriea","bundesliga","ligue1","rpl"]:
    c = byl.get(tid, {"matched":0,"new":0,"new_ex":[]})
    print(f"  {tid}: matched {c['matched']}, new {c['new']}  примеры новых: {c.get('new_ex',[])}")
print("\nUNMAPPED (нет в таблице англ->рус):")
for tid, s in unmapped.items():
    print(f"  {tid}: {sorted(s)}")
print("\n==== DONE4")
