#!/usr/bin/env python3
# Движок расчёта прогнозов: settle.py data.json scores.json results.json [airesults.json]
# scores.json: {"<home>": "h:a", ...}  (ключ — имя хозяев)
# airesults.json (необяз., для сида): {"<home>": "win|lose|push"} — готовый итог ИИ
# results.json читается и дополняется (накопление по дням). Пушы в % не учитываются.
import json, re, sys, datetime

def norm(s): return re.sub(r'[^а-яёa-z0-9]', '', str(s).lower())

def team_side(q, home, away):
    q, H, A = norm(q), norm(home), norm(away)
    for L in (6,5,4,3):
        if len(q)>=L and len(H)>=L and H[:L]==q[:L]: return '1'
        if len(q)>=L and len(A)>=L and A[:L]==q[:L]: return '2'
    if len(H)>=4 and H[:4] in q: return '1'
    if len(A)>=4 and A[:4] in q: return '2'
    return None

def num(p):
    m = re.search(r'([+-]?\d+(?:\.\d+)?)', p)
    return float(m.group(1)) if m else None

def settle_token(tok, h, a, home, away):
    """win / lose / push / None(=не учтено)"""
    p = tok.strip().lower().replace('−','-').replace('–','-').replace(',', '.')
    tot = h + a
    out = '1' if h>a else ('2' if h<a else 'x')
    btts = h>0 and a>0
    # обе забьют
    if 'обе заб' in p or 'оба заб' in p or re.search(r'(^| )оз( |$)', p):
        yes = not ('нет' in p or 'не заб' in p)
        return 'win' if (btts==yes) else 'lose'
    # тоталы
    if 'тотал больш' in p or re.search(r'(^| )тб[ 0-9(]', p) or 'больше' in p:
        n = num(p)
        if n is None: return None
        return 'push' if tot==n else ('win' if tot>n else 'lose')
    if 'тотал мен' in p or re.search(r'(^| )тм[ 0-9(]', p) or 'меньше' in p:
        n = num(p)
        if n is None: return None
        return 'push' if tot==n else ('win' if tot<n else 'lose')
    # форы Ф1 / Ф2 (значение)
    mh = re.search(r'ф\s*1\D*([+-]?\d+(?:\.\d+)?)', p)
    ma = re.search(r'ф\s*2\D*([+-]?\d+(?:\.\d+)?)', p)
    if mh:
        v=float(mh.group(1)); d=(h+v)-a
        return 'push' if abs(d)<1e-9 else ('win' if d>0 else 'lose')
    if ma:
        v=float(ma.group(1)); d=(a+v)-h
        return 'push' if abs(d)<1e-9 else ('win' if d>0 else 'lose')
    # двойной шанс
    if re.search(r'1\s*[хx]', p): return 'win' if out in ('1','x') else 'lose'
    if re.search(r'[хx]\s*2', p): return 'win' if out in ('x','2') else 'lose'
    if p.strip() in ('12','1-2','1/2'): return 'win' if out in ('1','2') else 'lose'
    # точный счёт
    ms = re.search(r'(\d+)\s*:\s*(\d+)', p)
    if ms and ('счёт' in p or 'счет' in p):
        return 'win' if (int(ms.group(1))==h and int(ms.group(2))==a) else 'lose'
    # не проиграет / не уступит
    if 'не проигр' in p or 'не уступ' in p:
        s=team_side(p,home,away)
        if s=='1': return 'win' if out in ('1','x') else 'lose'
        if s=='2': return 'win' if out in ('2','x') else 'lose'
        return None
    # чистые коды исхода
    ps=p.strip()
    if ps in ('п1','1','победа 1'): return 'win' if out=='1' else 'lose'
    if ps in ('п2','2','победа 2'): return 'win' if out=='2' else 'lose'
    if ps in ('х','x','ничья'): return 'win' if out=='x' else 'lose'
    # победа «команда» / выигрыш
    if 'побед' in p or 'выигр' in p:
        q=re.search(r'[«"]([^»"]+)[»"]', tok)
        s=team_side(q.group(1) if q else p, home, away)
        if s: return 'win' if out==s else 'lose'
    return None

def settle_pick(pick, h, a, home, away):
    # комбо: все части должны зайти
    parts = re.split(r'[+·&]| и ', str(pick))
    parts = [x for x in parts if x.strip()]
    if len(parts) > 1:
        res=[settle_token(x,h,a,home,away) for x in parts]
        if any(r is None for r in res): return None
        if any(r=='lose' for r in res): return 'lose'
        if all(r in ('win','push') for r in res): return 'win' if any(r=='win' for r in res) else 'push'
        return None
    return settle_token(pick, h, a, home, away)

def load(path, default):
    try:
        with open(path, encoding='utf-8') as f: return json.load(f)
    except Exception: return default

def main():
    data = load(sys.argv[1], {})
    scores = load(sys.argv[2], {})
    res_path = sys.argv[3]
    aires = load(sys.argv[4], {}) if len(sys.argv)>4 else {}
    R = load(res_path, {"updated":"","sources":{},"ai":{"win":0,"lose":0,"push":0},"recent":[],"done":[]})
    R.setdefault("sources",{}); R.setdefault("ai",{"win":0,"lose":0,"push":0}); R.setdefault("recent",[]); R.setdefault("done",[]); R.setdefault("matches",0)
    done=set(R["done"])
    added=0
    for t in data.get("tournaments",[]):
        for m in t.get("matches",[]):
            if m.get("status")!="full": continue
            sc = scores.get(m["home"])
            if not sc: continue
            key = m["date"]+"|"+m["home"]+"|"+m["away"]
            if key in done: continue
            mm=re.match(r'\s*(\d+)\s*[:\-]\s*(\d+)', str(sc))
            if not mm: continue
            h,a=int(mm.group(1)),int(mm.group(2))
            out='1' if h>a else ('2' if h<a else 'x')
            picklog=[]
            for tp in m.get("tips",[]):
                r=settle_pick(tp.get("pick",""), h, a, m["home"], m["away"])
                src=tp.get("src","?"); reg=tp.get("reg","ru")
                S=R["sources"].setdefault(src,{"reg":reg,"win":0,"lose":0,"push":0})
                if r in ("win","lose","push"): S[r]+=1
                picklog.append({"src":src,"reg":reg,"pick":tp.get("pick",""),"res":r or "skip"})
            # ИИ
            air=None
            if m.get("ai",{}).get("pick"):
                air=settle_pick(m["ai"]["pick"], h, a, m["home"], m["away"])
            if air is None and m["home"] in aires:
                air=aires[m["home"]]
            if air is None and m.get("ai",{}).get("score"):
                aim=re.match(r'\s*(\d+)\s*:\s*(\d+)', m["ai"]["score"])
                if aim:
                    ao='1' if int(aim.group(1))>int(aim.group(2)) else ('2' if int(aim.group(1))<int(aim.group(2)) else 'x')
                    air='win' if ao==out else 'lose'
            if air in ("win","lose","push"): R["ai"][air]+=1
            R["recent"].insert(0, {"date":m["date"],"home":m["home"],"away":m["away"],"score":f"{h}:{a}",
                                   "tour":t.get("short",t.get("name","")),"ai":air or "skip","picks":picklog})
            done.add(key); added+=1
    R["matches"]=R.get("matches",0)+added
    R["recent"]=R["recent"][:60]
    R["done"]=list(done)[-500:]
    R["updated"]=datetime.datetime.now().isoformat()
    with open(res_path,"w",encoding='utf-8') as f: json.dump(R,f,ensure_ascii=False,indent=1)
    print("settled matches:",added,"| sources:",len(R["sources"]))

if __name__=="__main__": main()
