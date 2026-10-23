#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генерация «мнения ChatGPT» по матчам для сервиса «Капер ИИ».

Читает data.json и results.json, для каждого предстоящего матча без прогноза
вызывает OpenAI с формой команд по подтверждённым предыдущим результатам.
Результат — gpt.json,
ключ матча: "date|home|away" (ровно как поля в data.json).

Инкрементально: однажды сгенерированное мнение не переписывается (пик
«замораживается» до матча — важно для честного подсчёта проходимости).
Чтобы пересчитать предстоящие матчи — запусти с FORCE=1.

ENV:
  OPENAI_API_KEY  — обязателен
  OPENAI_MODEL    — модель (по умолчанию gpt-4o-mini)
  DATA_FILE       — путь к data.json (по умолчанию data.json)
  OUT_FILE        — путь к gpt.json  (по умолчанию gpt.json)
  RES_FILE        — путь к results.json (по умолчанию results.json)
  FORCE           — "1" → перегенерировать прогнозы предстоящих матчей
"""
import os, sys, json, datetime, re
from openai import OpenAI

DATA_FILE = os.environ.get("DATA_FILE", "data.json")
OUT_FILE  = os.environ.get("OUT_FILE", "gpt.json")
RES_FILE  = os.environ.get("RES_FILE", "results.json")
MODEL     = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
FORCE     = os.environ.get("FORCE", "") == "1"
MSK = datetime.timezone(datetime.timedelta(hours=3))

SYSTEM = (
    "Ты — футбольный аналитик-прогнозист сервиса «Капер ИИ». Дай СВОЙ независимый "
    "прогноз и опирайся прежде всего на последние подтверждённые результаты и форму "
    "обеих команд из контекста, домашнюю/гостевую форму, составы и фактор поля. "
    "Коэффициенты и чужие прогнозы используй только как дополнительную проверку, "
    "не копируй их. Используй только переданные факты; не выдумывай форму, травмы, "
    "составы, очные встречи и статистику. Если данных о форме мало, прямо укажи это "
    "и снизь уверенность. Верни ТОЛЬКО JSON-объект со схемой: "
    '{"score":"X:Y","text":"1–2 предложения по-русски","conf":0-5 (целое),"bet":"ставка"}. '
    "score — наиболее вероятный точный счёт, bet — наиболее вероятный исход и только "
    "из вариантов П1, Х, П2, 1Х или Х2; score и bet должны быть согласованы. "
    "conf: 0–1 почти равный матч, 2–3 умеренно, 4–5 высоко; не завышай. "
    "Это аналитика, без обещаний. Никакого текста вне JSON."
)

def mkey(m):
    return f'{m.get("date","")}|{m.get("home","")}|{m.get("away","")}'

def norm_team(s):
    return re.sub(r"[^а-яa-z0-9]", "", str(s or "").lower().replace("ё", "е"))

def score_pair(score):
    match = re.search(r"(\d+)\s*[-:–—]\s*(\d+)", str(score or ""))
    return (int(match.group(1)), int(match.group(2))) if match else None

def completed_matches(data, results):
    found = {}
    for tournament in data.get("tournaments", []):
        for match in tournament.get("matches", []):
            score = match.get("ft") or match.get("score")
            if not score_pair(score):
                continue
            key = (match.get("date", ""), norm_team(match.get("home")), norm_team(match.get("away")))
            found[key] = {
                "date": match.get("date", ""), "time": match.get("time", ""),
                "home": match.get("home", ""), "away": match.get("away", ""),
                "score": str(score), "tour": tournament.get("short") or tournament.get("name", ""),
            }
    recent_results = results.get("recent", []) if isinstance(results, dict) else []
    for result in recent_results:
        score = result.get("score") or result.get("ft")
        if not score_pair(score):
            continue
        key = (result.get("date", ""), norm_team(result.get("home")), norm_team(result.get("away")))
        found.setdefault(key, {
            "date": result.get("date", ""), "time": result.get("time", ""),
            "home": result.get("home", ""), "away": result.get("away", ""),
            "score": str(score), "tour": result.get("tour", ""),
        })
    return list(found.values())

def team_form(team, matches, target_date, venue=None):
    key = norm_team(team)
    games = []
    for match in matches:
        if not match.get("date") or match["date"] >= target_date:
            continue
        score = score_pair(match.get("score"))
        if not score:
            continue
        home = norm_team(match.get("home")) == key
        away = norm_team(match.get("away")) == key
        if not home and not away:
            continue
        goals_for, goals_against = score if home else (score[1], score[0])
        opponent = match.get("away") if home else match.get("home")
        outcome = "В" if goals_for > goals_against else ("Н" if goals_for == goals_against else "П")
        games.append({
            "date": match["date"], "time": match.get("time", ""),
            "opponent": opponent, "site": "дома" if home else "в гостях",
            "score": f"{goals_for}:{goals_against}", "outcome": outcome,
            "gf": goals_for, "ga": goals_against,
        })
    games.sort(key=lambda game: (game["date"], game["time"]), reverse=True)
    recent = games[:5]
    if not recent:
        return f"{team}: в доступных данных нет подтверждённых результатов до даты матча."
    wins = sum(game["outcome"] == "В" for game in recent)
    draws = sum(game["outcome"] == "Н" for game in recent)
    losses = sum(game["outcome"] == "П" for game in recent)
    gf = sum(game["gf"] for game in recent)
    ga = sum(game["ga"] for game in recent)
    lines = [f"{team}, последние {len(recent)} игр: {wins}В-{draws}Н-{losses}П, голы {gf}:{ga}."]
    lines.append("Недавние матчи: " + "; ".join(
        f'{game["date"]} {game["site"]} с {game["opponent"]} {game["score"]} ({game["outcome"]})'
        for game in recent
    ))
    if venue:
        venue_games = [game for game in games if game["site"] == venue][:3]
        if venue_games:
            venue_wins = sum(game["outcome"] == "В" for game in venue_games)
            venue_draws = sum(game["outcome"] == "Н" for game in venue_games)
            venue_losses = sum(game["outcome"] == "П" for game in venue_games)
            lines.append(
                f"Форма {venue}: {len(venue_games)} игр, "
                f"{venue_wins}В-{venue_draws}Н-{venue_losses}П."
            )
    return "\n".join(lines)

def is_upcoming(match, now=None):
    now = now or datetime.datetime.now(MSK)
    try:
        day = datetime.date.fromisoformat(match.get("date", ""))
    except ValueError:
        return False
    if day > now.date():
        return True
    if day < now.date():
        return False
    if not match.get("time"):
        return True
    try:
        kickoff = datetime.datetime.combine(day, datetime.time.fromisoformat(match["time"]), MSK)
        return kickoff > now
    except ValueError:
        return True

def match_context(t, m, history):
    L = [f'Матч: {m.get("home","")} — {m.get("away","")}',
         f'Турнир: {t.get("name","")}, {t.get("round","")}',
         f'Дата/время: {m.get("date","")} {m.get("time","")}',
         "Форма по фактическим результатам до даты этого матча:",
         team_form(m.get("home", ""), history, m.get("date", ""), "дома"),
         team_form(m.get("away", ""), history, m.get("date", ""), "в гостях")]
    o = m.get("odds") or []
    if len(o) >= 3 and any(x is not None for x in o[:3]):
        f = lambda x: "—" if x is None else x
        L.append(f'Коэффициенты: П1 {f(o[0])} · Х {f(o[1])} · П2 {f(o[2])}')
    lu = m.get("lineups") or {}
    for side, label in (("home", m.get("home","")), ("away", m.get("away",""))):
        s = lu.get(side) or {}
        outs = s.get("out") or []
        if s.get("formation") or outs:
            L.append(f'{label}: схема {s.get("formation","?")}' +
                     (f', нет: {", ".join(outs)}' if outs else ""))
    news = m.get("news") or []
    if news:
        L.append("Новости: " + "; ".join(n.get("t","") for n in news[:3]))
    cnt = {"1": 0, "X": 0, "2": 0}
    for tp in m.get("tips") or []:
        if tp.get("lean") in cnt:
            cnt[tp["lean"]] += 1
    if sum(cnt.values()):
        L.append(f'Эксперты склоняются: П1={cnt["1"]}, Х={cnt["X"]}, П2={cnt["2"]}')
    return "\n".join(L)

def main():
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY не задан")
    with open(DATA_FILE, encoding="utf-8") as f:
        data = json.load(f)
    try:
        with open(RES_FILE, encoding="utf-8") as f:
            results = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        results = {}
    history = completed_matches(data, results)
    try:
        with open(OUT_FILE, encoding="utf-8") as f:
            prev = json.load(f)
        matches = prev.get("matches") if isinstance(prev.get("matches"), dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        matches = {}

    client = OpenAI()
    added = 0
    attempted = 0
    first_error = None
    for t in data.get("tournaments", []):
        for m in t.get("matches", []):
            if m.get("status") not in ("full", "fixture") or m.get("ft") or m.get("score"):
                continue
            if not is_upcoming(m):
                continue
            k = mkey(m)
            if k in matches and not FORCE:
                continue
            attempted += 1
            try:
                r = client.chat.completions.create(
                    model=MODEL,
                    messages=[{"role": "system", "content": SYSTEM},
                              {"role": "user", "content": match_context(t, m, history)}],
                    response_format={"type": "json_object"},
                    temperature=0.7,
                )
                op = json.loads(r.choices[0].message.content)
                try:
                    conf = max(0, min(5, int(op.get("conf", 0) or 0)))
                except (TypeError, ValueError):
                    conf = 0
                matches[k] = {
                    "score": str(op.get("score", "")),
                    "text":  str(op.get("text", "")),
                    "conf":  conf,
                    "bet":   str(op.get("bet", "")),
                }
                added += 1
                print("OK  ", k, "→", matches[k]["bet"])
            except Exception as ex:
                if first_error is None:
                    first_error = ex
                print("SKIP", k, repr(ex))

    print(f"Итог: попыток {attempted}, успешно {added}, всего в файле {len(matches)}")

    # Если пытались, но не получили НИ ОДНОГО мнения и писать нечего — падаем с ясной
    # причиной (job станет красным) и НЕ публикуем пустой файл.
    if added == 0 and attempted > 0 and not matches:
        sys.exit(
            "Ни одно мнение не сгенерировано — все вызовы OpenAI упали.\n"
            f"Первая ошибка: {first_error!r}\n"
            "Частые причины: на аккаунте OpenAI нет кредитов / не настроен биллинг, "
            "либо OPENAI_API_KEY неверный. Проверь platform.openai.com/account/billing."
        )

    if not matches:
        print("Нет мнений для записи — файл не меняю.")
        return

    out = {"generated": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
           "model": MODEL,
           "matches": matches}
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"Записан {OUT_FILE}: добавлено {added}, всего {len(matches)}")

if __name__ == "__main__":
    main()
