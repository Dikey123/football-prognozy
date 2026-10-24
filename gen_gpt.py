#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генерация локального ИИ-мнения по матчам для сервиса «Капер ИИ».

Читает data.json и results.json, для каждого предстоящего матча без прогноза
вызывает Ollama на этом компьютере с формой по подтверждённым результатам.
Скрипт не отправляет запросы в OpenAI и не использует облачный веб-поиск.
Результат — gpt.json,
ключ матча: "date|home|away" (ровно как поля в data.json).

Прогноз обновляется не чаще раза в день и при поступлении новых результатов.
После начала матча он фиксируется. Чтобы пересчитать предстоящие матчи — FORCE=1.

ENV:
  OLLAMA_MODEL    — локальная модель (по умолчанию qwen3:4b)
  OLLAMA_URL      — локальный адрес Ollama (по умолчанию 127.0.0.1:11434)
  DATA_FILE       — путь к data.json (по умолчанию data.json)
  OUT_FILE        — путь к gpt.json  (по умолчанию gpt.json)
  RES_FILE        — путь к results.json (по умолчанию results.json)
  FORCE           — "1" → перегенерировать прогнозы предстоящих матчей
"""
import os, sys, json, datetime, re, urllib.request, urllib.error

DATA_FILE = os.environ.get("DATA_FILE", "data.json")
OUT_FILE  = os.environ.get("OUT_FILE", "gpt.json")
RES_FILE  = os.environ.get("RES_FILE", "results.json")
MODEL     = os.environ.get("OLLAMA_MODEL", "qwen3:4b")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
FORCE     = os.environ.get("FORCE", "") == "1"
MIN_PROBABILITY = 60
MAX_DAYS_AHEAD = 4
MSK = datetime.timezone(datetime.timedelta(hours=3))

SYSTEM = (
    "Ты — футбольный аналитик-прогнозист сервиса «Капер ИИ». Дай СВОЙ независимый "
    "прогноз и опирайся прежде всего на последние подтверждённые результаты и форму "
    "обеих команд из контекста, домашнюю/гостевую форму, составы и фактор поля. "
    "Коэффициенты и чужие прогнозы используй только как дополнительную проверку, "
    "не копируй их. Используй только переданные факты; не выдумывай форму, травмы, "
    "составы, очные встречи и статистику. Не ищи информацию в интернете: используй только "
    "переданные факты из локальных файлов, включая форму, новости, составы, котировки и "
    "прогнозы источников. Если каких-то данных нет, прямо укажи это и не додумывай. "
    "При нехватке надёжных данных или конфликте источников укажи ограничения. Всегда дай собственное "
    "мнение, наиболее вероятный счёт и выбери наиболее подходящий исход из допустимых "
    "вариантов, даже если уверенность ниже 75%: порог влияет только на статистическую "
    "категорию, а не на публикацию прогноза. Оцени вероятность выбранного исхода "
    "консервативно, как оценку модели, а не гарантию; учитывай базовую вероятность "
    "по коэффициентам и не завышай её. Допустимые варианты: П1, Х, П2, 1Х, Х2. "
    "Не выдумывай коэффициент: используй котировку только из переданных данных. "
    "Верни JSON: score (наиболее вероятный счёт), text (короткое обоснование по-русски), "
    "probability (целое 0–100), bet (обязательно один из допустимых вариантов). Никакого "
    "текста вне JSON."
)

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "string"},
        "text": {"type": "string"},
        "probability": {"type": "integer"},
        "bet": {"type": "string", "enum": ["П1", "Х", "П2", "1Х", "Х2"]},
    },
    "required": ["score", "text", "probability", "bet"],
    "additionalProperties": False,
}

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

def parse_timestamp(value):
    if not value:
        return None
    try:
        stamp = datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        # Source timestamps without an offset are written in Moscow local time.
        return stamp.replace(tzinfo=MSK) if stamp.tzinfo is None else stamp
    except ValueError:
        return None

def local_forecast(context):
    """Call only the Ollama server bound to this computer; reject remote URLs."""
    from urllib.parse import urlparse
    parsed = urlparse(OLLAMA_URL)
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise RuntimeError("OLLAMA_URL должен указывать только на локальный компьютер")
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": context},
        ],
        "format": OUTPUT_SCHEMA,
        "stream": False,
        "think": False,
        "options": {"temperature": 0.2, "num_ctx": 8192},
    }
    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        body = json.load(response)
    content = (body.get("message") or {}).get("content")
    if not content:
        raise RuntimeError("Локальная модель вернула пустой ответ")
    return json.loads(content)

def ensure_local_model():
    """Fail once, with a useful message, if the local Ollama model is unavailable."""
    from urllib.parse import urlparse
    parsed = urlparse(OLLAMA_URL)
    tags_url = f"{parsed.scheme}://{parsed.netloc}/api/tags"
    try:
        with urllib.request.urlopen(tags_url, timeout=10) as response:
            installed = json.load(response).get("models", [])
    except Exception as ex:
        sys.exit(
            "Локальная Ollama не отвечает. Запустите её на этом компьютере "
            f"и повторите попытку. Причина: {ex!r}"
        )
    names = {str(item.get("name", "")) for item in installed}
    if MODEL not in names:
        sys.exit(f"Локальная модель {MODEL} не установлена. Выполните: ollama pull {MODEL}")

def needs_generation(key, matches, previous_generated, source_updates, now):
    if FORCE or key not in matches:
        return True
    existing = matches[key]
    generated = parse_timestamp(existing.get("generated_at") if isinstance(existing, dict) else None)
    generated = generated or parse_timestamp(previous_generated)
    if not generated:
        return True
    if generated.astimezone(MSK).date() < now.date():
        return True
    return any(stamp and stamp > generated for stamp in source_updates)

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

def pick_coefficient(match, bet):
    """Return a quoted 1X2 price or an explicitly estimated double-chance price."""
    code = re.sub(r"\s+", "", str(bet or "").upper()).replace("Х", "X")
    odds = match.get("odds") or []
    direct = {"П1": 0, "1": 0, "X": 1, "Х": 1, "П2": 2, "2": 2}
    if code in direct:
        try:
            value = float(odds[direct[code]])
            return (round(value, 2), False) if 1.01 < value < 100 else (None, False)
        except (IndexError, TypeError, ValueError):
            return None, False

    indices = {"1X": (0, 1), "X2": (1, 2)}.get(code)
    if not indices:
        return None, False
    prices = []
    for source in match.get("odds_sources") or []:
        values = source.get("odds") or []
        try:
            a, b = float(values[indices[0]]), float(values[indices[1]])
        except (IndexError, TypeError, ValueError):
            continue
        if a > 1.01 and b > 1.01:
            prices.append(1 / (1 / a + 1 / b))
    if not prices:
        try:
            a, b = float(odds[indices[0]]), float(odds[indices[1]])
        except (IndexError, TypeError, ValueError):
            return None, False
        if a > 1.01 and b > 1.01:
            prices.append(1 / (1 / a + 1 / b))
    return (round(max(prices), 2), True) if prices else (None, False)

def main():
    from urllib.parse import urlparse
    if urlparse(OLLAMA_URL).hostname not in ("127.0.0.1", "localhost", "::1"):
        sys.exit("Запрещён удалённый ИИ-сервис: разрешён только Ollama на этом компьютере")
    ensure_local_model()
    with open(DATA_FILE, encoding="utf-8") as f:
        data = json.load(f)
    try:
        with open(RES_FILE, encoding="utf-8") as f:
            results = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        results = {}
    history = completed_matches(data, results)
    previous_generated = ""
    try:
        with open(OUT_FILE, encoding="utf-8") as f:
            prev = json.load(f)
        matches = prev.get("matches") if isinstance(prev.get("matches"), dict) else {}
        previous_generated = prev.get("generated", "")
    except (FileNotFoundError, json.JSONDecodeError):
        matches = {}

    now_msk = datetime.datetime.now(MSK)
    source_updates = [parse_timestamp(data.get("updated")), parse_timestamp(results.get("updated"))]
    added = 0
    attempted = 0
    first_error = None
    for t in data.get("tournaments", []):
        for m in t.get("matches", []):
            if m.get("status") not in ("full", "fixture") or m.get("ft") or m.get("score"):
                continue
            if not is_upcoming(m):
                continue
            try:
                match_day = datetime.date.fromisoformat(m.get("date", ""))
            except ValueError:
                continue
            if match_day > now_msk.date() + datetime.timedelta(days=MAX_DAYS_AHEAD):
                continue
            k = mkey(m)
            if not needs_generation(k, matches, previous_generated, source_updates, now_msk):
                continue
            attempted += 1
            try:
                op = local_forecast(match_context(t, m, history))
                probability = max(0, min(100, int(op.get("probability", 0) or 0)))
                candidate_bet = str(op.get("bet", "")).strip()
                sources = []
                coefficient, coefficient_estimated = pick_coefficient(m, candidate_bet)
                # 60% — оценка модели, а не фильтр публикации. Сохраняем мнение и ставку,
                # даже если котировки пока нет; приложение не должно придумывать коэффициент.
                eligible = bool(candidate_bet) and coefficient is not None
                score = str(op.get("score", "")).strip() or "Счёт не определён"
                opinion_text = str(op.get("text", "")).strip() or "Обоснование модели не указано."
                matches[k] = {
                    "score": score,
                    "text":  opinion_text,
                    "probability": probability,
                    "threshold": MIN_PROBABILITY,
                    "eligible": eligible,
                    "bet": candidate_bet,
                    "coefficient": coefficient if candidate_bet else None,
                    "coefficient_estimated": coefficient_estimated if candidate_bet and coefficient else False,
                    "skip_reason": "" if eligible else (
                        "модель не выбрала исход" if not candidate_bet else
                        "котировка выбранного исхода недоступна"
                    ),
                    "sources": sources,
                    "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                }
                added += 1
                print("OK  ", k, "→", matches[k]["bet"] or "нет выбранного исхода", f"({probability}%, источников {len(sources)})")
            except Exception as ex:
                if first_error is None:
                    first_error = ex
                print("SKIP", k, repr(ex))

    print(f"Итог: попыток {attempted}, успешно {added}, всего в файле {len(matches)}")

    # Если пытались, но не получили НИ ОДНОГО мнения и писать нечего — падаем с ясной
    # причиной (job станет красным) и НЕ публикуем пустой файл.
    if added == 0 and attempted > 0 and not matches:
        sys.exit(
            "Локальная модель не сгенерировала прогнозы. Убедитесь, что Ollama запущена "
            f"и модель {MODEL} установлена. Первая ошибка: {first_error!r}"
        )

    if added == 0:
        print("Нет новых или требующих обновления прогнозов — файл не меняю.")
        return

    out = {"generated": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
           "model": MODEL,
           "minimum_probability": MIN_PROBABILITY,
           "matches": matches}
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"Записан {OUT_FILE}: добавлено {added}, всего {len(matches)}")

if __name__ == "__main__":
    main()

