#!/usr/bin/env python3
"""Render the animated black & white SVG cards for the GitHub profile README.

Usage:  GITHUB_TOKEN=... python scripts/render_cards.py [--static]
--static renders the final frame without animation (for previewing).
Needs: fonttools + brotli (font subsetting). Falls back to data/cache.json if the API is unreachable.
"""
import base64, io, json, os, sys, urllib.request, datetime as dt
from html import escape
from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USER = os.environ.get("PROFILE_USER", "Dhao1601")
STATIC = "--static" in sys.argv
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")

BG, CARD, LINE, INK, MUTED, DIM = "#0a0a0a", "#0f0f0f", "#262626", "#fafafa", "#8b8b8b", "#3a3a3a"
GREEN = "#39d353"

# ------------------------------------------------------------------ data
def api(path, query=None):
    url = "https://api.github.com" + (path if query is None else "/graphql")
    data = None if query is None else json.dumps({"query": query}).encode()
    req = urllib.request.Request(url, data=data, headers={"Accept": "application/vnd.github+json", "User-Agent": "profile-cards"})
    if TOKEN: req.add_header("Authorization", "Bearer " + TOKEN)
    with urllib.request.urlopen(req, timeout=30) as r: return json.load(r)

def fetch():
    user = api(f"/users/{USER}")
    repos, page = [], 1
    while True:
        batch = api(f"/users/{USER}/repos?per_page=100&type=owner&page={page}")
        repos += batch
        if len(batch) < 100: break
        page += 1
    repos = [r for r in repos if not r["private"] and not r["fork"]]
    langs = {}
    for r in repos:
        for k, v in api(f"/repos/{USER}/{r['name']}/languages").items(): langs[k] = langs.get(k, 0) + v
    cal = api(None, 'query{user(login:"%s"){contributionsCollection{contributionCalendar{totalContributions weeks{contributionDays{date contributionCount}}}}}}' % USER)
    cal = cal["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    days = [d for w in cal["weeks"] for d in w["contributionDays"]]
    return {
        "name": user.get("name") or USER, "followers": user["followers"], "public_repos": len(repos),
        "stars": sum(r["stargazers_count"] for r in repos), "forks": sum(r["forks_count"] for r in repos),
        "contributions": cal["totalContributions"], "days": days, "langs": langs,
        "repos": {r["name"]: {"stars": r["stargazers_count"], "forks": r["forks_count"], "lang": r["language"] or "—"} for r in repos},
        "updated": dt.date.today().isoformat(),
    }

cache = os.path.join(ROOT, "data", "cache.json")
try:
    D = fetch(); json.dump(D, open(cache, "w"), ensure_ascii=False, indent=1)
except Exception as e:
    print("API failed, using cache:", e); D = json.load(open(cache))
P = json.load(open(os.path.join(ROOT, "data", "projects.json")))

# ------------------------------------------------------------------ fonts (subset per card, embedded as base64 woff2)
_vf = TTFont(os.path.join(ROOT, "fonts", "JetBrainsMono-VF.ttf"))
FONTS = {
    "mono": instancer.instantiateVariableFont(TTFont(os.path.join(ROOT, "fonts", "JetBrainsMono-VF.ttf")), {"wght": 400}),
    "monob": instancer.instantiateVariableFont(_vf, {"wght": 700}),
    "serif": TTFont(os.path.join(ROOT, "fonts", "InstrumentSerif-Regular.ttf")),
    "serifi": TTFont(os.path.join(ROOT, "fonts", "InstrumentSerif-Italic.ttf")),
}
def font_face(name, text):
    buf = io.BytesIO(); FONTS[name].save(buf); buf.seek(0)
    f = TTFont(buf)
    opts = subset.Options(); opts.flavor = "woff2"; opts.layout_features = ["kern", "liga", "ccmp", "mark", "mkmk"]
    s = subset.Subsetter(opts); s.populate(text=text + " "); s.subset(f)
    out = io.BytesIO(); f.flavor = "woff2"; f.save(out)
    fam = {"mono": "M", "monob": "MB", "serif": "S", "serifi": "SI"}[name]
    return "@font-face{font-family:%s;src:url(data:font/woff2;base64,%s) format('woff2')}" % (fam, base64.b64encode(out.getvalue()).decode())

ANIM = """
@keyframes up{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
@keyframes fade{from{opacity:0}to{opacity:1}}
@keyframes grow{from{transform:scaleY(0)}to{transform:scaleY(1)}}
@keyframes growx{from{transform:scaleX(0)}to{transform:scaleX(1)}}
@keyframes draw{from{stroke-dashoffset:1}to{stroke-dashoffset:0}}
@keyframes blink{0%,49%{opacity:1}50%,100%{opacity:0}}
@keyframes pulse{0%,100%{opacity:.25}50%{opacity:1}}
@keyframes pop{from{transform:scale(0);opacity:0}to{transform:scale(1);opacity:1}}
.pop{transform-box:fill-box;transform-origin:50% 50%;animation:pop .45s cubic-bezier(.3,1.4,.5,1) both}
@keyframes glow{0%,100%{opacity:1}50%{opacity:.4}}
.tile{transform-box:fill-box;transform-origin:50% 50%}
@keyframes flash{0%,100%{opacity:1}}
@keyframes show{from{opacity:1}to{opacity:1}}
@keyframes type{from{transform:scaleX(0)}to{transform:scaleX(1)}}
@keyframes shine{0%,55%{transform:translateX(-260px)}100%{transform:translateX(560px)}}
.up{animation:up .8s cubic-bezier(.2,.7,.2,1) both}.fade{animation:fade 1s ease both}
.bar{transform-box:fill-box;transform-origin:50% 100%;animation:grow .9s cubic-bezier(.2,.7,.2,1) both}
.seg{transform-box:fill-box;transform-origin:0 50%;animation:growx 1s cubic-bezier(.2,.7,.2,1) both}
.draw{stroke-dasharray:1;animation:draw 1.4s cubic-bezier(.6,0,.2,1) both}
.cur{animation:blink 1s step-end infinite}.pulse{animation:pulse 2.4s ease-in-out infinite}
@media (prefers-reduced-motion:reduce){*{animation:none!important}.fin{opacity:1!important}}
"""
def svg(w, h, body, fonts, text):
    css = "".join(font_face(n, text) for n in fonts)
    css += ".M{font-family:M,ui-monospace,Menlo,monospace}.MB{font-family:MB,ui-monospace,Menlo,monospace;font-weight:700}.S{font-family:S,Georgia,serif}.SI{font-family:SI,Georgia,serif;font-style:italic}"
    if not STATIC: css += ANIM
    else: body = body.replace("<animate", "<!--a").replace("</animate>", "-->")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img">'
            f'<style>{css}</style>{body}</svg>')

def frame(w, h, r=14):
    return (f'<rect x=".5" y=".5" width="{w-1}" height="{h-1}" rx="{r}" fill="{CARD}"/>'
            f'<rect x=".5" y=".5" width="{w-1}" height="{h-1}" rx="{r}" fill="none" stroke="{LINE}"/>')

def dots(w, h, step=22, op=.09):
    return f'<pattern id="d" width="{step}" height="{step}" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="1" fill="{INK}" opacity="{op}"/></pattern><rect width="{w}" height="{h}" fill="url(#d)"/>'

def d(s): return "" if STATIC else f' style="animation-delay:{s:.2f}s"'

def counter(x, y, value, cls, size, delay, anchor="start", frames=18):
    """count up: stacked text frames, each shown for one step by a CSS animation (CSS cannot change text)"""
    if STATIC or value == 0:
        return f'<text x="{x}" y="{y}" class="{cls}" font-size="{size}" fill="{INK}" text-anchor="{anchor}">{value}</text>'
    out, step = [], .055
    for i in range(1, frames + 1):
        v = round(value * (1 - (1 - i / frames) ** 3)); last = i == frames; b = delay + i * step
        anim = (f"animation:show 1s linear {b:.3f}s both" if last else f"animation:flash {step:.3f}s step-end {b:.3f}s")
        out.append(f'<text x="{x}" y="{y}" class="{cls}{" fin" if last else ""}" font-size="{size}" fill="{INK}" text-anchor="{anchor}" opacity="0" style="{anim}">{v}</text>')
    return "".join(out)

def star(x, y, s=12, fill=MUTED):
    import math
    pts = []
    for i in range(10):
        r = s / 2 if i % 2 == 0 else s / 4.6; a = -math.pi / 2 + i * math.pi / 5
        pts.append(f"{x + r * math.cos(a):.2f},{y + r * math.sin(a):.2f}")
    return f'<polygon points="{" ".join(pts)}" fill="{fill}"/>'

def fork(x, y, fill=MUTED):
    return (f'<g fill="none" stroke="{fill}" stroke-width="1.5" stroke-linecap="round">'
            f'<circle cx="{x-4}" cy="{y-5}" r="1.8"/><circle cx="{x+4}" cy="{y-5}" r="1.8"/><circle cx="{x}" cy="{y+5.5}" r="1.8"/>'
            f'<path d="M{x-4} {y-3}v1.5q0 2.5 4 2.5t4-2.5v-1.5M{x} {y+1}v2.7"/></g>')

def write(name, content):
    out = os.environ.get("CARDS_DIR", os.path.join(ROOT, "cards")); os.makedirs(out, exist_ok=True); open(os.path.join(out, name), "w").write(content); print("wrote", name, len(content) // 1024, "KB")

# ------------------------------------------------------------------ hero
W = 1000
name = D["name"]; tag = "> " + P["tagline"]; hand = P["handles"]
cw = 15 * .6
steps = len(tag); tw = steps * cw; tdur = steps * .035
type_css = "" if STATIC else f"animation:type {tdur:.2f}s steps({steps}) 1.1s both;transform-box:fill-box;transform-origin:0 50%"
cur_css = "" if STATIC else f"@keyframes curmv{{from{{transform:translateX(0)}}to{{transform:translateX({tw:.1f}px)}}}}"
body = (frame(W, 270) + dots(W, 270) +
  '<defs><linearGradient id="sh" x1="0" x2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".5" stop-color="#fff" stop-opacity=".95"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>'
  f'<clipPath id="nm"><text x="52" y="132" class="S" font-size="88" letter-spacing="-1">{escape(name)}</text></clipPath>'
  f'<clipPath id="ty"><rect x="56" y="150" width="{tw:.1f}" height="26" style="{type_css}"/></clipPath></defs>'
  +
  f'<g class="up"{d(.1)}><text x="56" y="56" class="M" font-size="13" fill="{MUTED}" letter-spacing="2">~/{USER.upper()}</text>'
  f'<circle cx="{W-160}" cy="51" r="4" fill="{GREEN}" class="pulse"/><text x="{W-146}" y="56" class="M" font-size="13" fill="{MUTED}" letter-spacing="2">ONLINE</text></g>'
  f'<g class="up"{d(.35)}><text x="52" y="132" class="S" font-size="88" fill="#d9d9d9" letter-spacing="-1">{escape(name)}</text>'
  + ("" if STATIC else f'<g clip-path="url(#nm)"><rect x="0" y="50" width="200" height="100" fill="url(#sh)" style="animation:shine 6s cubic-bezier(.5,0,.3,1) 1.2s infinite both;transform:translateX(-260px)"/></g>')
  + '</g>'
  f'<text x="56" y="168" class="M" font-size="15" fill="{INK}" clip-path="url(#ty)"><tspan fill="{GREEN}">&gt;</tspan>{escape(tag[1:])}</text>'
  f'<g class="fade"{d(1.1+tdur)}><g class="cur"><rect x="{56+tw+3:.1f}" y="154" width="9" height="17" fill="{GREEN}"/></g></g>'
  f'<line x1="56" y1="206" x2="{W-56}" y2="206" stroke="{LINE}"/>'
  f'<g class="fade"{d(2.6)}><text x="56" y="236" class="M" font-size="13" fill="{MUTED}">{escape(hand)}</text>'
  '</g>')
write("hero.svg", svg(W, 270, body, ["mono", "serif"], name + tag + hand + USER.upper() + "~/ONLINE updated 0123456789-"))

# ------------------------------------------------------------------ stats
items = [("PUBLIC REPOS", D["public_repos"]), ("STARS", D["stars"]), ("FORKS", D["forks"]), ("CONTRIBUTIONS · 1Y", D["contributions"]), ("FOLLOWERS", D["followers"])]
cw2 = W / len(items); body = frame(W, 150)
for i, (lab, val) in enumerate(items):
    x = cw2 * i + 36
    if i: body += f'<line x1="{cw2*i:.1f}" y1="32" x2="{cw2*i:.1f}" y2="118" stroke="{LINE}"/>'
    body += f'<g class="up"{d(.15+i*.12)}><text x="{x:.1f}" y="58" class="M" font-size="11" fill="{MUTED}" letter-spacing="1.6">{lab}</text>'
    body += counter(round(x, 1), 108, val, "S", 52, .4 + i * .12) + f'<rect x="{x:.1f}" y="120" width="22" height="2" rx="1" fill="{GREEN}"/></g>'
write("stats.svg", svg(W, 150, body, ["mono", "serif"], "".join(l for l, _ in items) + "0123456789"))

# ------------------------------------------------------------------ green pattern (decorative, not data)
import math, random
GREENS = ["#14211a", "#0e4429", "#006d32", "#26a641", "#39d353"]
rnd = random.Random(1601)
ncol, nrow = 53, 7
x0, y0, c, gap = 40, 112, 14, 3.5
H4 = int(y0 + nrow * (c + gap) + 34)
body = frame(W, H4) + dots(W, H4, op=.05)
body += (f'<g class="up"{d(.1)}><text x="36" y="76" font-size="50" fill="{INK}"><tspan class="S">Always building, </tspan>'
         f'<tspan class="SI" fill="{GREENS[4]}">in green</tspan></text></g>')
for col in range(ncol):
    for row in range(nrow):
        f = (math.sin(col * .31 + row * .55) + .7 * math.sin(col * .12 - row * .8 + 1.3) + .45 * math.sin(col * .53 + 2.1)) / 2.15
        v = .5 + .5 * f + rnd.uniform(-.18, .18)
        lv = max(0, min(4, int(v * 5.2)))
        x, y = x0 + col * (c + gap), y0 + row * (c + gap)
        anim = "" if STATIC else (f' style="animation:pop .45s cubic-bezier(.3,1.4,.5,1) {.2+col*.014+row*.01:.2f}s both,'
                                  f'glow 3.6s ease-in-out {1.4+(col*.07+row*.05)%3.6:.2f}s infinite"')
        body += f'<rect class="tile" x="{x:.1f}" y="{y:.1f}" width="{c}" height="{c}" rx="3.5" fill="{GREENS[lv]}"{anim}/>'
write("heatmap.svg", svg(W, H4, body, ["serif", "serifi"], "Always building, in green"))

# ------------------------------------------------------------------ stack (languages by bytes)
tot = sum(D["langs"].values()) or 1
L = sorted(D["langs"].items(), key=lambda kv: -kv[1])[:5]
shades = [GREEN, INK, "#9a9a9a", "#5c5c5c", "#3d3d3d"]
H3 = 130; body = frame(W, H3) + f'<text x="36" y="44" class="M up" font-size="11" fill="{MUTED}" letter-spacing="1.6"{d(.1)}>LANGUAGES · PUBLIC REPOS</text>'
x, bw = 36, W - 72
body += f'<clipPath id="bar"><rect x="36" y="62" width="{bw}" height="10" rx="5"/></clipPath><g clip-path="url(#bar)"><rect x="36" y="62" width="{bw}" height="10" fill="{DIM}"/>'
for i, (k, v) in enumerate(L):
    w = bw * v / tot
    body += f'<rect class="seg" x="{x:.1f}" y="62" width="{w+.6:.1f}" height="10" fill="{shades[i]}"{d(.3+i*.12)}/>'
    x += w
body += '</g>'
lx = 36
for i, (k, v) in enumerate(L):
    lab = f"{k} {100*v/tot:.1f}%"
    body += f'<g class="up"{d(.6+i*.1)}><rect x="{lx}" y="92" width="10" height="10" rx="2" fill="{shades[i]}" stroke="{LINE}"/><text x="{lx+18}" y="101" class="M" font-size="12" fill="{MUTED}">{escape(lab)}</text></g>'
    lx += 18 + len(lab) * 7.2 + 30
write("stack.svg", svg(W, H3, body, ["mono"], "LANGUAGES·PUBLICREPOS" + "".join(k for k, _ in L) + "0123456789.%"))

# ------------------------------------------------------------------ project cards
def wrap(t, n):
    out, line = [], ""
    for w in t.split():
        if len(line) + len(w) + 1 > n: out.append(line); line = w
        else: line = (line + " " + w).strip()
    return out + [line]
for i, p in enumerate(P["projects"]):
    r = D["repos"].get(p["repo"], {"stars": 0, "forks": 0, "lang": "—"})
    w, h = 490, 210
    host = p["link"].split("//")[1].rstrip("/")
    body = (frame(w, h) +
      f'<rect class="draw" x="1" y="1" width="{w-2}" height="{h-2}" rx="13" fill="none" stroke="{GREEN}" stroke-width="1.2" pathLength="1"{d(.1+i*.15)} opacity=".7"/>'
      f'<g class="up"{d(.35+i*.15)}><text x="28" y="44" class="M" font-size="12" fill="{MUTED}" letter-spacing="1.6">{i+1:02d} / {escape(p["repo"])}</text>'
      f'<text x="{w-28}" y="44" class="M" font-size="12" fill="{GREEN}" text-anchor="end">live ↗</text></g>'
      f'<g class="up"{d(.5+i*.15)}><text x="26" y="92" class="S" font-size="40" fill="{INK}">{escape(p["title"])}</text></g>')
    for j, line in enumerate(wrap(p["desc"], 52)[:2]):
        body += f'<text x="28" y="{124+j*20}" class="M up" font-size="13" fill="{MUTED}"{d(.65+i*.15)}>{escape(line)}</text>'
    yb = 182
    body += f'<g class="up"{d(.8+i*.15)}><line x1="28" y1="160" x2="{w-28}" y2="160" stroke="{LINE}"/>'
    body += f'<rect x="28" y="{yb-13}" width="{len(r["lang"])*7.4+20:.0f}" height="20" rx="10" fill="none" stroke="{LINE}"/><text x="{38}" y="{yb+1}" class="M" font-size="11" fill="{INK}">{escape(r["lang"])}</text>'
    sx = 28 + len(r["lang"]) * 7.4 + 40
    body += star(sx, yb - 3, 12, GREEN if r["stars"] else MUTED) + f'<text x="{sx+11:.0f}" y="{yb+1}" class="M" font-size="12" fill="{INK}">{r["stars"]}</text>'
    fx = sx + 26 + len(str(r["stars"])) * 7.2 + 18
    body += fork(fx, yb - 3, INK if r["forks"] else MUTED) + f'<text x="{fx+11:.0f}" y="{yb+1}" class="M" font-size="12" fill="{INK}">{r["forks"]}</text>'
    body += f'<text x="{w-28}" y="{yb+1}" class="M" font-size="11" fill="{DIM}" text-anchor="end">{escape(host[:34])}</text></g>'
    text = p["title"] + p["desc"] + p["repo"] + r["lang"] + host + "0123456789/ live↗"
    write(f"project-{i+1}.svg", svg(w, h, body, ["mono", "serif"], text))
print("done", "static" if STATIC else "animated")
