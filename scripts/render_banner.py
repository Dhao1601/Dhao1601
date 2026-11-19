#!/usr/bin/env python3
"""Animated ASCII banner: smoking cat with a glowing ember, drifting smoke and blinking eyes.

Usage: python scripts/render_banner.py [--static]      (needs numpy, opencv-python, fonttools, brotli)
"""
import base64, io, math, os, random, sys
from html import escape
import cv2, numpy as np
from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = "--static" in sys.argv
OUT = os.environ.get("CARDS_DIR", os.path.join(ROOT, "cards"))
W, H = 1000, 640
CARD, LINE, INK, MUTED, DIM, GREEN = "#0f0f0f", "#262626", "#fafafa", "#8b8b8b", "#3a3a3a", "#39d353"
EMBER, CORE = "#ff7a1a", "#ffd27a"

CROP = (40, 70)                                              # trim empty left/top so the face is bigger
img = cv2.imread(os.path.join(ROOT, "assets", "cat.png"), 0).astype(np.float32)[CROP[1]:, CROP[0]:] / 255
IH, IW = img.shape
EYES = [((130 - CROP[0], 296 - CROP[1]), (62, 46)), ((452 - CROP[0], 204 - CROP[1]), (86, 58))]      # (centre, radii) in image pixels
TIP = (632 - CROP[0], 716 - CROP[1])                                             # burning end of the cigarette

def closed_eyes(src):
    """same picture with the eyelids shut: fill each eye with fur from just above it, then draw the lid"""
    out = src.copy()
    for (cx, cy), (rx, ry) in EYES:
        m = np.zeros_like(src, np.uint8); cv2.ellipse(m, (cx, cy), (rx, ry), 0, 0, 360, 1, -1)
        dy = int(ry * 1.55)
        shifted = np.roll(src, dy, axis=0)
        out[m > 0] = shifted[m > 0]
        pts = np.array([(cx - rx, cy - 4), (cx - rx // 2, cy + ry // 5), (cx, cy + ry // 4), (cx + rx // 2, cy + ry // 6), (cx + rx, cy - 6)], np.int32)
        cv2.polylines(out, [pts], False, 0.0, max(5, ry // 6), cv2.LINE_AA)
        cv2.polylines(out, [pts - [0, max(5, ry // 6)]], False, 1.0, 2, cv2.LINE_AA)
    return out

# ---- grid
ROWS = 104; ph = IH / ROWS; FS = H / ROWS; CW = FS * .6; pw = ph * CW / FS; COLS = int(IW / pw)
X0 = W - COLS * CW - 26
RAMP = " .:-=+*#%@"
TONES = ["#5e5e5e", "#9a9a9a", "#d6d6d6", "#ffffff"]
def ascii_grid(src):
    """high-contrast mapping that follows the black & white source: empty where dark, dense white where light"""
    small = cv2.resize(src, (COLS, ROWS), interpolation=cv2.INTER_AREA)
    out = []
    for row in small:
        line = []
        for v in row:
            if v < .2: line.append((" ", 0)); continue
            if v < .42: line.append(((".", ":", "-")[int((v - .2) / .074)], 0)); continue
            if v < .62: line.append((("=", "+", "*")[min(2, int((v - .42) / .067))], 1)); continue
            if v < .82: line.append((("#", "%")[min(1, int((v - .62) / .1))], 2)); continue
            line.append(("@", 3))
        out.append(line)
    return out
A = ascii_grid(img); B = ascii_grid(closed_eyes(img))
tipc, tipr = TIP[0] / pw, TIP[1] / ph

def cx(c): return X0 + c * CW
def ry(r): return (r + .82) * FS

# ember cells come out of the base text and get their own colour
ember, core = [], []
for r in range(ROWS):
    for c in range(COLS):
        dd = math.hypot((c - tipc) * pw, (r - tipr) * ph)
        if dd < 30 and A[r][c][0] != " ":
            (core if dd < 13 else ember).append((r, c, A[r][c][0])); A[r][c] = (" ", 0); B[r][c] = (" ", 0)

def runs(cells_, c0=0):
    """row of (char, tone) -> tspans with explicit x, grouped by tone; spaces are skipped, never relied on"""
    out, i, n = [], 0, len(cells_)
    while i < n:
        ch, t = cells_[i]
        if ch == " ": i += 1; continue
        j = i
        while j < n and cells_[j][0] != " " and cells_[j][1] == t: j += 1
        out.append(f'<tspan x="{cx(c0+i):.2f}" fill="{TONES[t]}">{escape("".join(c for c, _ in cells_[i:j]))}</tspan>')
        i = j
    return "".join(out)

def rows_text(grid, cls):
    out = []
    for r, row in enumerate(grid):
        if any(ch != " " for ch, _ in row): out.append(f'<text y="{ry(r):.1f}" class="{cls}">{runs(row)}</text>')
    return "".join(out)

# eye overlay: segments where the closed picture differs
lid = []
for (ecx, ecy), (erx, ery) in EYES:
    r0, r1 = int((ecy - ery * 1.3) / ph), int((ecy + ery * 1.3) / ph) + 1
    c0, c1 = int((ecx - erx * 1.2) / pw), int((ecx + erx * 1.2) / pw) + 1
    for r in range(max(r0, 0), min(r1, ROWS)):
        seg = B[r][c0:c1]
        if seg != A[r][c0:c1]:
            lid.append(f'<rect x="{cx(c0):.1f}" y="{ry(r)-FS*.82:.1f}" width="{(c1-c0)*CW:.1f}" height="{FS+.4:.1f}" fill="{CARD}"/>'
                       f'<text y="{ry(r):.1f}" class="cat">{runs(seg, c0)}</text>')

def cells(lst, cls):
    return "".join(f'<text x="{cx(c):.1f}" y="{ry(r):.1f}" class="{cls}">{escape(ch)}</text>' for r, c, ch in lst)

# ---- smoke
rnd = random.Random(7); TX, TY = cx(tipc), ry(tipr) - FS * .4
smoke, keys = [], []
for i in range(18):
    ch = rnd.choice("~~~()'.°`")
    dur = rnd.uniform(5.5, 8); delay = -rnd.uniform(0, dur); top = rnd.uniform(260, 430); drift = rnd.uniform(-90, 10)
    sw = rnd.uniform(10, 26); k = f"s{i}"
    keys.append(f"@keyframes {k}{{0%{{transform:translate(0,0) scale(.7);opacity:0}}12%{{opacity:.75}}"
                f"35%{{transform:translate({drift*.3+sw:.0f}px,{-top*.35:.0f}px) scale(1.1)}}"
                f"65%{{transform:translate({drift*.65-sw:.0f}px,{-top*.68:.0f}px) scale(1.5);opacity:.45}}"
                f"100%{{transform:translate({drift:.0f}px,{-top:.0f}px) scale(2);opacity:0}}}}")
    st = "" if STATIC else f' style="animation:{k} {dur:.2f}s cubic-bezier(.3,.1,.5,1) {delay:.2f}s infinite"'
    op = "" if not STATIC else f' opacity="{.5 if i % 3 else 0}" transform="translate({drift*.4:.0f},{-top*.45:.0f})"'
    smoke.append(f'<text x="{TX:.1f}" y="{TY:.1f}" class="smoke"{st}{op}>{escape(ch)}</text>')

# ---- terminal text on the left
lines = [("~/bin", MUTED, 0), ("", None, 0), ("$ whoami", GREEN, 1), ("bin", INK, 1), ("", None, 0),
         ("$ cat mood.txt", GREEN, 2), ("chill · building web toys", INK, 2), ("", None, 0),
         ("$ uptime", GREEN, 3), ("always online", INK, 3)]
term = ""; y = 210
for t, col, step in lines:
    if t:
        a = "" if STATIC else f' style="animation:up .7s cubic-bezier(.2,.7,.2,1) {.4+step*.45+(0 if t.startswith("$") or t=="~/bin" else .2):.2f}s both"'
        size = 13 if t == "~/bin" else 17
        term += f'<text x="52" y="{y}" class="M" font-size="{size}" fill="{col}" letter-spacing="{2 if t=="~/bin" else 0}"{a}>{escape(t)}</text>'
    y += 30 if t else 14
term += f'<rect x="52" y="{y-4}" width="10" height="19" fill="{GREEN}" class="cur"/>'

# ---- font
vf = instancer.instantiateVariableFont(TTFont(os.path.join(ROOT, "fonts", "JetBrainsMono-VF.ttf")), {"wght": 400})
vfb = instancer.instantiateVariableFont(TTFont(os.path.join(ROOT, "fonts", "JetBrainsMono-VF.ttf")), {"wght": 800})
used = set(RAMP + "".join(c for _, _, c in ember + core) + "~()'.°`" + "".join(t for t, _, _ in lines))
buf = io.BytesIO(); vf.save(buf); buf.seek(0); f = TTFont(buf)
o = subset.Options(); o.flavor = "woff2"; s = subset.Subsetter(o); s.populate(text="".join(used)); s.subset(f)
fb = io.BytesIO(); f.flavor = "woff2"; f.save(fb)
font = "@font-face{font-family:M;src:url(data:font/woff2;base64,%s) format('woff2')}" % base64.b64encode(fb.getvalue()).decode()
buf = io.BytesIO(); vfb.save(buf); buf.seek(0); f = TTFont(buf); s = subset.Subsetter(o); s.populate(text=RAMP + "~()'.°`"); s.subset(f)
fb = io.BytesIO(); f.flavor = "woff2"; f.save(fb)
font += "@font-face{font-family:MX;src:url(data:font/woff2;base64,%s) format('woff2')}" % base64.b64encode(fb.getvalue()).decode()

css = font + f""".M,.cat,.emb,.core,.smoke{{font-family:M,ui-monospace,Menlo,monospace;white-space:pre}}
.cat{{font-family:MX,ui-monospace,Menlo,monospace;font-weight:800;font-size:{FS:.2f}px;fill:#e9e9e9}}.emb{{font-size:{FS:.2f}px;fill:{EMBER}}}.core{{font-size:{FS:.2f}px;fill:{CORE}}}
.smoke{{font-size:{FS*1.5:.1f}px;fill:#cfcfcf;transform-box:fill-box;transform-origin:50% 50%}}
"""
if not STATIC:
    css += f"""
@keyframes up{{from{{opacity:0;transform:translateY(8px)}}to{{opacity:1;transform:none}}}}
@keyframes blinkc{{0%,100%{{opacity:1}}50%{{opacity:0}}}}
@keyframes lid{{0%,90.5%,94.5%,96%,99%,100%{{opacity:0}}91.5%,93.5%,97%,98%{{opacity:1}}}}
@keyframes breathe{{0%,100%{{transform:translateY(0) rotate(0deg)}}30%{{transform:translateY(-1.6px) rotate(-.35deg)}}60%{{transform:translateY(-.6px) rotate(.25deg)}}}}
@keyframes flick{{0%,100%{{opacity:1}}18%{{opacity:.7}}34%{{opacity:.95}}52%{{opacity:.6}}70%{{opacity:1}}86%{{opacity:.75}}}}
@keyframes glow{{0%,100%{{opacity:.55}}40%{{opacity:.95}}75%{{opacity:.4}}}}
.cur{{animation:blinkc 1s step-end infinite}}
.lids{{opacity:0;animation:lid 6.5s linear 1.5s infinite}}
.head{{transform-origin:{X0+COLS*CW/2:.0f}px {H}px;animation:breathe 5.2s ease-in-out infinite}}
.ember{{animation:flick 1.7s ease-in-out infinite}}.halo{{animation:glow 2.3s ease-in-out infinite}}
{"".join(keys)}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}.lids{{opacity:0!important}}}}
"""
body = (f'<defs><clipPath id="cl"><rect x="1" y="1" width="{W-2}" height="{H-2}" rx="13"/></clipPath>'
        f'<filter id="bl" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="5"/></filter>'
        f'<radialGradient id="hg"><stop offset="0" stop-color="{EMBER}" stop-opacity=".9"/><stop offset="1" stop-color="{EMBER}" stop-opacity="0"/></radialGradient></defs>'
        f'<rect x=".5" y=".5" width="{W-1}" height="{H-1}" rx="14" fill="{CARD}"/>'
        f'<g clip-path="url(#cl)"><g class="head">{rows_text(A, "cat")}<g class="lids">{"".join(lid)}</g>'
        f'<g class="halo"><circle cx="{TX:.1f}" cy="{TY:.1f}" r="38" fill="url(#hg)" opacity=".55"/>'
        f'<g filter="url(#bl)">{cells(ember+core, "emb")}</g></g>'
        f'<g class="ember">{cells(ember, "emb")}{cells(core, "core")}</g></g>'
        f'{"".join(smoke)}</g>'
        f'{term}<rect x=".5" y=".5" width="{W-1}" height="{H-1}" rx="14" fill="none" stroke="{LINE}"/>')
svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" xml:space="preserve"><style>{css}</style>{body}</svg>'
os.makedirs(OUT, exist_ok=True); open(os.path.join(OUT, "banner.svg"), "w").write(svg)
print("banner", COLS, "x", ROWS, len(svg) // 1024, "KB", "ember", len(ember), "core", len(core), "lid segs", len(lid))
