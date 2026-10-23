#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Собирает опубликованные прогнозы из открытых статей по предстоящим матчам.

Сначала проверяются страницы источников, уже привязанные к лигам в data.json,
затем поиск идёт через публичную RSS-ленту Google News. В data.json попадают
только страницы известных спортивных изданий, где найдены обе команды и явно
указан поддерживаемый рынком прогноз. Поисковые сниппеты не используются.
"""
import ast
import datetime as dt
import email.utils
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET

DATA_FILE = Path("data.json")
MSK = dt.timezone(dt.timedelta(hours=3))
USER_AGENT = "FootballForecastCollector/1.0 (+https://github.com/Dikey123/football-prognozy)"
RSS_URL = "https://news.google.com/rss/search"
LOOKAHEAD_DAYS = 4
MAX_SOURCES_PER_MATCH = 12
MAX_RSS_ITEMS = 30
MAX_PAGE_BYTES = 2_500_000

# Только публичные спортивные сайты с редакционными или модельными прогнозами.
# Для нового сайта достаточно добавить его домен и название; подбор прогноза
# всё равно проходит через проверку матча и явный шаблон выбора.
SITES = {
    "vseprosport.ru": ("ВсеПроСпорт", "ru"),
    "metaratings.ru": ("Metaratings", "ru"),
    "stavka.tv": ("Ставка ТВ", "ru"),
    "theanalyst.com": ("Opta Analyst", "eu"),
    "laligaexpert.com": ("LaLiga Expert", "eu"),
    "betora.app": ("Betora", "eu"),
    "fixture360.com": ("Fixture360", "eu"),
    "luckadjusted.com": ("LuckAdjusted", "eu"),
    "placarhub.com": ("PlacarHub", "eu"),
    "forepitch.com": ("Forepitch", "eu"),
    "forebet.com": ("Forebet", "eu"),
    "predictz.com": ("PredictZ", "eu"),
    "vprognoze.ru": ("Vprognoze", "ru"),
    "livesport.ru": ("LiveSport.ru", "ru"),
    "sport.ua": ("Sport.ua", "ru"),
    "ua-football.com": ("UA-Футбол", "ru"),
    "sports.ru": ("Sports.ru", "ru"),
    "championat.com": ("Чемпионат", "ru"),
    "sport-express.ru": ("Спорт-Экспресс", "ru"),
    "soccer365.ru": ("Soccer365", "ru"),
    "ratingbet.com": ("RatingBet", "eu"),
    "legalbet.ru": ("Legalbet", "ru"),
    "sportsmole.co.uk": ("Sports Mole", "eu"),
    "olbg.com": ("OLBG", "eu"),
    "betclan.com": ("BetClan", "eu"),
    "betimate.com": ("Betimate", "eu"),
    "footballpredictions.com": ("FootballPredictions.com", "eu"),
}

ROBOTS = {}
ARTICLE_CACHE = {}
DOMAIN_LAST_REQUEST = {}


def log(message):
    print(message)


def norm_words(value):
    value = str(value or "").lower().replace("ё", "е")
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = value.replace("ß", "ss").replace("ø", "o").replace("ł", "l")
    return " ".join(re.findall(r"[a-zа-я0-9]+", value))


def load_english_names():
    """Без выполнения fetch_base.py читаем его таблицу официальных имён."""
    try:
        tree = ast.parse(Path("fetch_base.py").read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "TEAM"
                for target in node.targets
            ):
                mapping = ast.literal_eval(node.value)
                result = {}
                for english, russian in mapping.items():
                    result.setdefault(norm_words(russian), []).append(english)
                return result
    except Exception as exc:
        log(f"Не удалось прочитать таблицу имён команд: {exc}")
    return {}


ENGLISH_NAMES = load_english_names()


def aliases_for(team):
    aliases = [str(team or "")]
    aliases.extend(ENGLISH_NAMES.get(norm_words(team), []))
    aliases.extend(re.sub(r"^(?:fc|fk|ac|sc|afc|club)\s+", "", a, flags=re.I) for a in list(aliases))
    return list(dict.fromkeys(a for a in aliases if len(norm_words(a)) >= 4))


def contains_name(text, aliases):
    text_norm = " " + norm_words(text) + " "
    for alias in aliases:
        name = norm_words(alias)
        if name and f" {name} " in text_norm:
            return True
    return False


def host_for(url):
    try:
        host = (urllib.parse.urlsplit(url).hostname or "").lower().rstrip(".")
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def site_for(url):
    host = host_for(url)
    for domain, info in SITES.items():
        if host == domain or host.endswith("." + domain):
            return domain, info
    return None, None


def fetch(url, timeout=10, limit=MAX_PAGE_BYTES, method="GET"):
    domain, _ = site_for(url)
    if domain:
        elapsed = time.monotonic() - DOMAIN_LAST_REQUEST.get(domain, 0)
        if elapsed < 0.5:
            time.sleep(0.5 - elapsed)
        DOMAIN_LAST_REQUEST[domain] = time.monotonic()
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/rss+xml,application/xml;q=0.9,*/*;q=0.5"},
        method=method,
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.geturl(), response.read(limit)


def robots_allow(url):
    parts = urllib.parse.urlsplit(url)
    origin = f"{parts.scheme}://{parts.netloc}"
    if origin not in ROBOTS:
        parser = urllib.robotparser.RobotFileParser()
        robots_url = origin + "/robots.txt"
        try:
            _, body = fetch(robots_url, timeout=5, limit=512_000)
            parser.set_url(robots_url)
            parser.parse(body.decode("utf-8", "replace").splitlines())
            ROBOTS[origin] = parser
        except urllib.error.HTTPError as exc:
            if exc.code in (404, 410):
                parser.parse([])
                ROBOTS[origin] = parser
            else:
                ROBOTS[origin] = False
        except Exception:
            ROBOTS[origin] = False
    parser = ROBOTS[origin]
    return bool(parser and parser.can_fetch(USER_AGENT, url))


def rss_items(home, away, match_date, language):
    start = (dt.date.fromisoformat(match_date) - dt.timedelta(days=4)).isoformat()
    end = (dt.date.fromisoformat(match_date) + dt.timedelta(days=1)).isoformat()
    if language == "ru":
        hl, gl, ceid = "ru", "RU", "RU:ru"
        query = f'"{home}" "{away}" (прогноз OR ставки OR прогнозы) after:{start} before:{end}'
    else:
        hl, gl, ceid = "en-GB", "GB", "GB:en"
        query = f'"{home}" "{away}" (prediction OR predictions OR tips OR forecast) after:{start} before:{end}'
    url = RSS_URL + "?" + urllib.parse.urlencode({"q": query, "hl": hl, "gl": gl, "ceid": ceid})
    try:
        _, body = fetch(url, timeout=12, limit=2_000_000)
        root = ET.fromstring(body)
    except Exception as exc:
        log(f"RSS {language} {home} — {away}: {exc}")
        return []
    items = []
    for item in root.findall(".//item")[:MAX_RSS_ITEMS]:
        source = item.find("source")
        pub = item.findtext("pubDate", "")
        try:
            published = email.utils.parsedate_to_datetime(pub).astimezone(MSK) if pub else None
        except Exception:
            published = None
        items.append({
            "title": html.unescape(item.findtext("title", "")),
            "link": item.findtext("link", ""),
            "source_url": source.attrib.get("url", "") if source is not None else "",
            "published": published,
        })
    return items


class ArticleText(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "iframe", "nav", "footer", "header", "form"}
    BREAKS = {"br", "p", "div", "li", "h1", "h2", "h3", "h4", "blockquote", "tr", "td", "th"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.meta = {}
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in self.SKIP:
            self.skip += 1
            return
        if tag == "meta":
            key = (attrs.get("property") or attrs.get("name") or "").lower()
            if key and attrs.get("content"):
                self.meta[key] = attrs["content"]
        if not self.skip and tag in self.BREAKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        elif not self.skip and tag in self.BREAKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def published_time(meta):
    value = next((meta[k] for k in ("article:published_time", "datepublished", "date") if meta.get(k)), "")
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=MSK) if parsed.tzinfo is None else parsed.astimezone(MSK)
    except Exception:
        return None


def load_article(url):
    if url in ARTICLE_CACHE:
        return ARTICLE_CACHE[url]
    try:
        final_url, body = fetch(url, timeout=10)
        if not robots_allow(final_url):
            ARTICLE_CACHE[url] = None
            return None
        _, info = site_for(final_url)
        if not info:
            ARTICLE_CACHE[url] = None
            return None
        parser = ArticleText()
        parser.feed(body.decode("utf-8", "replace"))
        text = html.unescape(" ".join(parser.parts))
        text = re.sub(r"[ \t\r\f\v]+", " ", text)
        text = re.sub(r" *\n *", "\n", text)
        data = {"url": final_url, "text": text, "published": published_time(parser.meta), "site": info}
        ARTICLE_CACHE[url] = data
        return data
    except Exception as exc:
        log(f"Страница {url}: {exc}")
        ARTICLE_CACHE[url] = None
        return None


def source_paragraphs(text):
    # Не разделяем десятичные числа вроде 43.2% и ТБ 2.5.
    return [re.sub(r"\s+", " ", p).strip() for p in re.split(r"[\n!?]+|(?<!\d)\.(?!\d)", text) if p.strip()]


def identify_side(text, home_aliases, away_aliases):
    home = contains_name(text, home_aliases)
    away = contains_name(text, away_aliases)
    if home and not away:
        return "1"
    if away and not home:
        return "2"
    return None


def canonical_pick(candidate, home_aliases, away_aliases):
    raw = html.unescape(candidate).strip(" \t\r\n:;,.–—-")
    raw = re.sub(r"\s+", " ", raw)
    if not raw:
        return None
    lower = raw.lower().replace("ё", "е").replace("х", "x")
    if re.fullmatch(r"[12]", lower):
        return "П1" if lower == "1" else "П2"
    if "victoria local" in lower or "local win" in lower:
        return "П1"
    if "victoria visitante" in lower or "away win" in lower:
        return "П2"
    if "empate" in lower or "draw" in lower:
        return "Х"
    if "doble oportunidad" in lower:
        if re.search(r"1\s*x", lower):
            return "1Х"
        if re.search(r"x\s*2", lower):
            return "Х2"
    if "ambos marcan" in lower or "both teams to score" in lower:
        return "ОЗ нет" if re.search(r"\bno\b|no marcan", lower) else "ОЗ да"
    if "mas de" in lower or "más de" in lower:
        number = re.search(r"(\d+(?:[.,]\d+)?)", lower)
        if number:
            return "ТБ " + number.group(1).replace(",", ".")
    if "menos de" in lower:
        number = re.search(r"(\d+(?:[.,]\d+)?)", lower)
        if number:
            return "ТМ " + number.group(1).replace(",", ".")
    code = re.search(r"(?<![a-zа-я0-9])(1x|x2|12|п1|п2|победа 1|победа 2|ничья|draw|home win|away win)(?![a-zа-я0-9])", lower)
    if code:
        value = code.group(1)
        return {"1x": "1Х", "x2": "Х2", "12": "12", "п1": "П1", "п2": "П2",
                "победа 1": "П1", "победа 2": "П2", "ничья": "Х", "draw": "Х",
                "home win": "П1", "away win": "П2"}[value]
    if re.search(r"обе команды забьют|обе забьют|оба забьют|both teams to score|btts", lower):
        return "ОЗ нет" if re.search(r"\bнет\b|\bno\b|не забьют|not to score", lower) else "ОЗ да"
    total = re.search(r"(?:тотал\s+(больше|меньше)|\b(тб|тм)|\b(over|under))[^0-9]{0,8}(\d+(?:[.,]\d+)?)", lower)
    if total:
        side = total.group(1) or total.group(2) or total.group(3)
        number = total.group(4).replace(",", ".")
        over = side in ("больше", "тб", "over")
        return ("ТБ " if over else "ТМ ") + number
    if re.search(r"фора|handicap|\b0\s*\(0\)", lower):
        side = identify_side(raw, home_aliases, away_aliases)
        line = re.search(r"(?:фора|handicap)\s*\(?\s*([+-]?\d+(?:[.,]\d+)?)\s*\)?", lower)
        if side and line:
            number = line.group(1).replace(",", ".")
            if float(number) * 2 == round(float(number) * 2):
                return f"Ф{side}({number})"
    if re.search(r"побед|выиграет|to win|win the match", lower):
        side = identify_side(raw, home_aliases, away_aliases)
        if side:
            return "П1" if side == "1" else "П2"
    side = identify_side(raw, home_aliases, away_aliases)
    if side:
        return "П1" if side == "1" else "П2"
    if re.search(r"\bх\b|draw", lower):
        return "Х"
    return None


def extract_explicit_pick(text, home_aliases, away_aliases):
    marker = re.compile(
        r"(?:наш\s+прогноз(?:\s+на\s+матч)?|прогноз\s+(?:редакции|автора)|выбор\s+(?:редакции|редактора)|"
        r"наш\s+(?:выбор|вариант)|основной\s+прогноз|прогноз(?=\s*[:—–-])|ставка\s+дня|our\s+prediction|our\s+pick|"
        r"editor(?:'s)?\s+pick|best\s+bet|prediction\s+is|prediction(?=\s*[:—–-])|our\s+tip|pron[oó]stico)\s*(?:[:—–-]\s*|\s+)([^\n]{3,220})",
        re.IGNORECASE,
    )
    for match in marker.finditer(text):
        candidate = re.split(r"(?: коэффициент| кэф(?:фициент)?| за кэф| odds?\s*[:=])", match.group(1), maxsplit=1, flags=re.I)[0]
        pick = canonical_pick(candidate, home_aliases, away_aliases)
        if pick:
            return pick, match.group(1).strip()
    # Короткие англоязычные блоки иногда маркируют выбор как "Tip:".
    for paragraph in source_paragraphs(text):
        if re.match(r"^(?:tip|pick|selection|pron[oó]stico)\s*:", paragraph, re.I):
            candidate = paragraph.split(":", 1)[1].strip()
            pick = canonical_pick(candidate, home_aliases, away_aliases)
            if pick:
                return pick, candidate
    return None


def extract_opta_pick(text, home_aliases, away_aliases):
    scores = {}
    for sentence in source_paragraphs(text):
        percentages = re.findall(r"\b(\d{1,2}(?:\.\d+)?)\s*%", sentence)
        if not percentages:
            continue
        lower = sentence.lower()
        if re.search(r"\bdraws?\b", lower):
            side = "Х"
        else:
            identified = identify_side(sentence, home_aliases, away_aliases)
            side = {"1": "П1", "2": "П2"}.get(identified)
            if not side and contains_name(sentence, home_aliases) and contains_name(sentence, away_aliases):
                normalized = norm_words(sentence)
                home_pos = min((normalized.find(norm_words(a)) for a in home_aliases
                                if norm_words(a) in normalized), default=-1)
                away_pos = min((normalized.find(norm_words(a)) for a in away_aliases
                                if norm_words(a) in normalized), default=-1)
                if home_pos >= 0 and away_pos >= 0:
                    side = "П1" if home_pos < away_pos else "П2"
        if side:
            scores[side] = max(scores.get(side, 0), max(float(p) for p in percentages))
    if scores:
        winner = max(scores, key=scores.get)
        return winner, f"Модель Opta: {scores[winner]:g}%"
    return None


def match_block(text, home_aliases, away_aliases):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for start in range(len(lines)):
        for stop in range(start, min(len(lines), start + 10)):
            fragment = "\n".join(lines[start:stop + 1])
            if contains_name(fragment, home_aliases) and contains_name(fragment, away_aliases):
                return "\n".join(lines[max(0, start - 1):min(len(lines), stop + 10)])
    return ""


def extract_probabilistic_pick(text, home_aliases, away_aliases):
    explicit = extract_explicit_pick(text, home_aliases, away_aliases)
    if explicit:
        return explicit
    percentages = re.findall(r"\b(\d{1,2}(?:\.\d+)?)\s*%", text)
    if len(percentages) >= 3:
        outcomes = ("П1", "Х", "П2")
        values = [float(value) for value in percentages[:3]]
        i = max(range(3), key=lambda index: values[index])
        return outcomes[i], f"Модель: {values[i]:g}%"
    return None


def extract_pick(article, home_aliases, away_aliases, match_page=False):
    text = article["text"]
    if not contains_name(text, home_aliases) or not contains_name(text, away_aliases):
        return None
    if article["site"][0] in {"Opta Analyst", "LaLiga Expert", "Betora", "Fixture360",
                              "LuckAdjusted", "PlacarHub", "Forepitch", "Forebet", "PredictZ"}:
        match_page = True
    block = match_block(text, home_aliases, away_aliases)
    if match_page:
        if not block:
            return None
        if article["site"][0] == "Opta Analyst":
            result = extract_opta_pick(block, home_aliases, away_aliases)
            if result:
                return result
        result = extract_probabilistic_pick(block, home_aliases, away_aliases)
        if result:
            return result
        return None
    elif article["site"][0] == "Opta Analyst":
        result = extract_opta_pick(block or text, home_aliases, away_aliases)
        if result:
            return result
    return extract_explicit_pick(text, home_aliases, away_aliases)


def page_match_score(url, home_aliases, away_aliases):
    decoded = urllib.parse.unquote(url)
    return int(contains_name(decoded, home_aliases)) + int(contains_name(decoded, away_aliases))


def kickoff_for(match):
    try:
        return dt.datetime.strptime(f"{match['date']} {match.get('time', '23:59')}", "%Y-%m-%d %H:%M").replace(tzinfo=MSK)
    except Exception:
        return None


def parse_odds(candidate):
    match = re.search(r"(?:коэффициент|кэф(?:фициент)?|odds?)\D{0,12}([1-9]\d?(?:[.,]\d{1,2})?)", candidate, re.I)
    if not match:
        match = re.search(r"\bза\s+([1-9]\d?(?:[.,]\d{1,2})?)\b", candidate, re.I)
    return match.group(1).replace(",", ".") if match else ""


def article_url(item):
    url = item.get("link", "")
    if not url:
        return ""
    # Google News links redirect to the publisher. Redirects are followed by urllib.
    if host_for(url) == "news.google.com":
        try:
            final, _ = fetch(url, timeout=8, limit=1)
            return final
        except Exception:
            return ""
    return url


def store_tip(match, article, pick_info, now, kickoff, current):
    pick, candidate = pick_info
    published = article.get("published") or now
    if published >= kickoff:
        return False
    source_name, region = article["site"]
    tip = {
        "src": source_name,
        "reg": region,
        "pick": pick,
        "k": parse_odds(candidate),
        "url": article["url"],
        "published_at": published.isoformat(timespec="minutes"),
        "collected_at": now.isoformat(timespec="minutes"),
    }
    tip["lean"] = {"П1": "1", "П2": "2", "Х": "X"}.get(pick, "")
    existing = next((i for i, old in enumerate(current) if old.get("src") == source_name), None)
    if existing is None:
        current.append(tip)
        return True
    old = current[existing]
    same_prediction = all(old.get(field, "") == tip.get(field, "")
                          for field in ("url", "pick", "k", "published_at"))
    replace_old = old.get("url", "") == tip["url"] or not old.get("collected_at")
    if not replace_old and old.get("published_at") and tip.get("published_at"):
        replace_old = tip["published_at"] > old["published_at"]
    if replace_old and not same_prediction:
        current[existing] = tip
        return True
    return False


def collect_for_match(match, now, source_pages):
    kickoff = kickoff_for(match)
    if not kickoff or kickoff <= now:
        return 0
    home_aliases = aliases_for(match.get("home", ""))
    away_aliases = aliases_for(match.get("away", ""))
    if not home_aliases or not away_aliases:
        return 0
    current = match.setdefault("tips", [])
    added = 0
    domains_seen = set()
    # Сначала читаем уже используемые модельные/редакционные страницы турнира.
    for domain, urls in source_pages.items():
        ranked_urls = sorted(urls, key=lambda url: page_match_score(url, home_aliases, away_aliases), reverse=True)
        for url in ranked_urls[:3]:
            article = load_article(url)
            if not article:
                continue
            site_domain, _ = site_for(article["url"])
            if not site_domain:
                continue
            pick_info = extract_pick(article, home_aliases, away_aliases, match_page=True)
            if not pick_info:
                continue
            if store_tip(match, article, pick_info, now, kickoff, current):
                added += 1
            domains_seen.add(site_domain)
            break
        if len(domains_seen) >= MAX_SOURCES_PER_MATCH:
            return added

    queries = [(match["home"], match["away"], "ru")]
    english_home = next((x for x in home_aliases if re.search(r"[A-Za-z]", x)), "")
    english_away = next((x for x in away_aliases if re.search(r"[A-Za-z]", x)), "")
    if english_home and english_away:
        queries.append((english_home, english_away, "en"))
    for qhome, qaway, language in queries:
        items = rss_items(qhome, qaway, match["date"], language)
        for item in items:
            domain, info = site_for(item.get("source_url", ""))
            if not domain:
                domain, info = site_for(item.get("link", ""))
            if not domain or domain in domains_seen:
                continue
            final_url = article_url(item)
            final_domain, final_info = site_for(final_url)
            if not final_domain or not final_info or not robots_allow(final_url):
                continue
            article = load_article(final_url)
            if not article:
                continue
            pick_info = extract_pick(article, home_aliases, away_aliases)
            if not pick_info:
                continue
            if item.get("published"):
                article["published"] = article.get("published") or item["published"]
            if store_tip(match, article, pick_info, now, kickoff, current):
                added += 1
            domains_seen.add(final_domain)
            if len(domains_seen) >= MAX_SOURCES_PER_MATCH:
                return added
        time.sleep(0.15)
        if len(domains_seen) >= MAX_SOURCES_PER_MATCH:
            break
    return added


def main():
    if not DATA_FILE.exists():
        raise SystemExit("data.json не найден")
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    today = dt.datetime.now(MSK).date()
    end = today + dt.timedelta(days=LOOKAHEAD_DAYS)
    now = dt.datetime.now(MSK).replace(second=0, microsecond=0)
    processed = added = 0
    for tournament in data.get("tournaments", []):
        source_pages = {}
        for listed_match in tournament.get("matches", []):
            for tip in listed_match.get("tips", []):
                domain, _ = site_for(tip.get("url", ""))
                if domain and tip.get("url"):
                    source_pages.setdefault(domain, [])
                    if tip["url"] not in source_pages[domain]:
                        source_pages[domain].append(tip["url"])
        for match in tournament.get("matches", []):
            try:
                match_date = dt.date.fromisoformat(match.get("date", ""))
            except ValueError:
                continue
            if not today <= match_date <= end or match.get("status") == "full":
                continue
            processed += 1
            count = collect_for_match(match, now, source_pages)
            added += count
            log(f"{match['date']} {match.get('home')} — {match.get('away')}: новых/обновлённых источников {count}")
    if added:
        data["tips_updated"] = now.isoformat(timespec="minutes")
        DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    log(f"Итог: матчей {processed}, прогнозов добавлено/обновлено {added}")


if __name__ == "__main__":
    main()
