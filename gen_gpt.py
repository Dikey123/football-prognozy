#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генерация «мнения ChatGPT» по матчам для сервиса «Капер ИИ».

Читает data.json, для каждого матча со статусом "full", у которого ещё НЕТ
мнения в gpt.json, вызывает OpenAI и дописывает мнение. Результат — gpt.json,
ключ матча: "date|home|away" (ровно как поля в data.json).

Инкрементально: однажды сгенерированное мнение не переписывается (пик
«замораживается» до матча — важно для честного подсчёта проходимости).
Чтобы перегенерировать всё заново — запусти с FORCE=1.

ENV:
  OPENAI_API_KEY  — обязателен
  OPENAI_MODEL    — модель (по умолчанию gpt-4o-mini)
  DATA_FILE       — путь к data.json (по умолчанию data.json)
  OUT_FILE        — путь к gpt.json  (по умолчанию gpt.json)
  FORCE           — "1" → перегенерировать все full-матчи
"""
import os, sys, json, datetime
from openai import OpenAI

DATA_FILE = os.environ.get("DATA_FILE", "data.json")
OUT_FILE  = os.environ.get("OUT_FILE", "gpt.json")
MODEL     = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
FORCE     = os.environ.get("FORCE", "") == "1"

SYSTEM = (
    "Ты — футбольный аналитик-прогнозист сервиса «Капер ИИ». По данным матча дай "
    "СВОЁ независимое мнение. Верни ТОЛЬКО JSON-объект со схемой: "
    '{"score":"X:Y","text":"1–2 предложения по-русски","conf":0-5 (целое),"bet":"ставка"}. '
    "Ты — второе, независимое мнение: не копируй фаворита по коэффициентам вслепую, "
    "учитывай составы, травмы, форму, важность матча, фактор поля. score и bet согласованы. "
    "conf: 0–1 почти равный матч, 2–3 умеренно, 4–5 высоко; не завышай. "
    "bet — один стандартный рынок: П1/Х/П2, 1X/12/X2, ТБ/ТМ 2.5, "
    "«Обе забьют — да»/«Обе забьют — нет», Ф1(-1)/Ф2(+1) и т.п. "
    "Это аналитика, без обещаний. Никакого текста вне JSON."
)

def mkey(m):
    return f'{m.get("date","")}|{m.get("home","")}|{m.get("away","")}'

def match_context(t, m):
    L = [f'Матч: {m.get("home","")} — {m.get("away","")}',
         f'Турнир: {t.get("name","")}, {t.get("round","")}',
         f'Дата/время: {m.get("date","")} {m.get("time","")}']
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
            if m.get("status") != "full":
                continue
            k = mkey(m)
            if k in matches and not FORCE:
                continue
            attempted += 1
            try:
                r = client.chat.completions.create(
                    model=MODEL,
                    messages=[{"role": "system", "content": SYSTEM},
                              {"role": "user", "content": match_context(t, m)}],
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

    out = {"generated": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
           "matches": matches}
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"Записан {OUT_FILE}: добавлено {added}, всего {len(matches)}")

if __name__ == "__main__":
    main()
