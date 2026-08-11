#!/usr/bin/env python3
"""Generate the fabric care symbols (ISO 3758) as SVGs on a shared 48x48 grid.

Source of the symbol set and the English wording:
https://www.c-and-a.com/eu/en/shop/care-and-washing-symbols-made-simple

Writes assets/care-symbols/*.svg plus care-symbols.json (the manifest).
"""

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "care-symbols")

FONT = "Helvetica Neue, Helvetica, Arial, sans-serif"

HEAD = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" '
    'fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round">'
)


def svg(*parts):
    return HEAD + "".join(parts) + "</svg>\n"


def path(d, **kw):
    extra = "".join(f' {k.replace("_", "-")}="{v}"' for k, v in kw.items())
    return f'<path d="{d}"{extra}/>'


def line(x1, y1, x2, y2):
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"/>'


def dot(cx, cy, r=1.5):
    return f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="currentColor" stroke="none"/>'


def text(s, x, y, size):
    return (
        f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" '
        f'text-anchor="middle" fill="currentColor" stroke="none">{s}</text>'
    )


def cross(x1, y1, x2, y2):
    """The 'not allowed' X, drawn over the symbol's bounding box."""
    return line(x1, y1, x2, y2) + line(x1, y2, x2, y1)


# --- washing -----------------------------------------------------------------

TUB = path("M6 16 L11.5 38 H36.5 L42 16") + path(
    "M6 16 q4.5 -3.8 9 0 t9 0 t9 0 t9 0"
)


def tub(inner="", bars=0):
    parts = [TUB, inner]
    for i in range(bars):
        y = 42 + i * 4
        parts.append(line(12, y, 36, y))
    return svg(*parts)


def tub_temp(deg, bars=0):
    return tub(text(deg, 22.5, 33, 15) + dot(33.5, 22.5, 1.4), bars)


HAND = (
    # back of the hand: wrist enters top right, four fingers dip down-left
    path(
        "M39 19.5 C34 20 30.5 20.8 28 22.6 L20 28.8 "
        "C17.8 30.5 18.3 33.8 21 34.5 C24.8 35.3 28.8 33.8 31.6 30.4 L39 25.5"
    )
    + line(24.5, 26.5, 20.6, 29.8)
    + line(25.8, 28.6, 21.7, 31.8)
    + line(27.1, 30.6, 23, 33.7)
)


# --- bleaching ---------------------------------------------------------------

TRIANGLE = path("M24 8 L41 40 H7 Z")


# --- drying ------------------------------------------------------------------

SQUARE = '<rect x="8" y="8" width="32" height="32" rx="0.5"/>'
SHADE = path("M8 20 L20 8")


def box(inner="", shade=False):
    return svg(SQUARE, inner, SHADE if shade else "")


def tumble(dots=0, crossed=False):
    inner = '<circle cx="24" cy="24" r="12"/>'
    if dots == 1:
        inner += dot(24, 24)
    elif dots == 2:
        inner += dot(20.5, 24) + dot(27.5, 24)
    elif dots == 3:
        inner += dot(17.5, 24) + dot(24, 24) + dot(30.5, 24)
    return svg(SQUARE, inner, cross(4, 4, 44, 44) if crossed else "")


# --- ironing -----------------------------------------------------------------

IRON = path("M9 13 H31 L38.5 36 H8") + path("M8 36 C9.5 29 12 22.5 17 22.5 H37.5")


def iron(dots=0, crossed=False, steam=False):
    parts = [IRON]
    if dots == 1:
        parts.append(dot(24, 29.5))
    elif dots == 2:
        parts.append(dot(20.5, 29.5) + dot(27.5, 29.5))
    elif dots == 3:
        parts.append(dot(17, 29.5) + dot(23.5, 29.5) + dot(30, 29.5))
    if steam:
        parts.append(line(16, 36.5, 15, 44) + line(23.5, 36.5, 23.5, 44) + line(31, 36.5, 32, 44))
        parts.append(cross(9, 37, 38, 46))
    if crossed:
        parts.append(cross(5, 9, 41, 40))
    return svg(*parts)


# --- professional textile care ----------------------------------------------

CIRCLE = '<circle cx="24" cy="24" r="15"/>'


def circle(letter="", bars=0, crossed=False):
    parts = [CIRCLE]
    if letter:
        parts.append(text(letter, 24, 30.5, 18))
    for i in range(bars):
        y = 43 + i * 3.5
        parts.append(line(13, y, 35, y))
    if crossed:
        parts.append(cross(3, 5, 45, 43))
    return svg(*parts)


# --- the set -----------------------------------------------------------------

SYMBOLS = [
    # slug, group, label_en, label_ro, svg
    ("wash-none", "washing", "Do not wash", "A nu se spăla", tub(cross(3, 11, 45, 42))),
    ("wash-hand", "washing", "Hand wash", "Spălare manuală", tub(HAND)),
    ("wash-30", "washing", "Normal cycle up to 30°C", "Program normal, maximum 30°C", tub_temp("30")),
    ("wash-30-gentle", "washing", "Gentle cycle up to 30°C", "Program delicat, maximum 30°C", tub_temp("30", 1)),
    ("wash-30-very-gentle", "washing", "Very gentle cycle up to 30°C", "Program foarte delicat, maximum 30°C", tub_temp("30", 2)),
    ("wash-40", "washing", "Normal cycle up to 40°C", "Program normal, maximum 40°C", tub_temp("40")),
    ("wash-40-gentle", "washing", "Gentle cycle up to 40°C", "Program delicat, maximum 40°C", tub_temp("40", 1)),
    ("wash-40-very-gentle", "washing", "Very gentle cycle up to 40°C", "Program foarte delicat, maximum 40°C", tub_temp("40", 2)),
    ("wash-60", "washing", "Normal cycle up to 60°C", "Program normal, maximum 60°C", tub_temp("60")),
    ("wash-60-gentle", "washing", "Gentle cycle up to 60°C", "Program delicat, maximum 60°C", tub_temp("60", 1)),
    ("wash-95", "washing", "Normal cycle up to 95°C", "Program normal, maximum 95°C", tub_temp("95")),

    ("bleach-none", "bleaching", "Do not bleach", "A nu se înălbi", svg(TRIANGLE, cross(4, 6, 44, 42))),
    ("bleach-any", "bleaching", "Bleach allowed", "Se poate înălbi", svg(TRIANGLE)),
    ("bleach-non-chlorine", "bleaching", "Non-chlorine bleach", "Înălbitor fără clor", svg(TRIANGLE, path("M16 40 L28.5 16.5"), path("M26 40 L33.5 26"))),

    ("tumble-low", "drying", "Tumble dry at a low temperature", "Uscare în uscător, temperatură scăzută", tumble(1)),
    ("tumble-medium", "drying", "Tumble dry at a medium temperature", "Uscare în uscător, temperatură medie", tumble(2)),
    ("tumble-none", "drying", "Do not tumble dry", "A nu se usca în uscător", tumble(0, crossed=True)),
    ("dry-line", "drying", "Dry on a line", "Uscare pe sârmă", box(line(24, 14, 24, 34))),
    ("dry-drip-line", "drying", "Drip dry on a line", "Uscare pe sârmă, fără stoarcere", box(line(20.5, 14, 20.5, 34) + line(27.5, 14, 27.5, 34))),
    ("dry-flat", "drying", "Dry lying flat", "Uscare pe orizontală", box(line(14, 24, 34, 24))),
    ("dry-drip-flat", "drying", "Drip dry lying flat", "Uscare pe orizontală, fără stoarcere", box(line(14, 20.5, 34, 20.5) + line(14, 27.5, 34, 27.5))),
    ("dry-line-shade", "drying", "Line dry in the shade", "Uscare pe sârmă, la umbră", box(line(24, 16, 24, 34), shade=True)),
    ("dry-drip-line-shade", "drying", "Drip dry on the line in the shade", "Uscare pe sârmă la umbră, fără stoarcere", box(line(21.5, 17.5, 21.5, 34) + line(28, 14, 28, 34), shade=True)),
    ("dry-flat-shade", "drying", "Dry lying flat in the shade", "Uscare pe orizontală, la umbră", box(line(16, 25, 34, 25), shade=True)),
    ("dry-drip-flat-shade", "drying", "Drip dry lying flat in the shade", "Uscare pe orizontală la umbră, fără stoarcere", box(line(17, 21.5, 34, 21.5) + line(15, 28, 34, 28), shade=True)),

    ("iron-low", "ironing", "Iron at a low temperature", "Călcare la temperatură scăzută", iron(1)),
    ("iron-medium", "ironing", "Iron at a medium temperature", "Călcare la temperatură medie", iron(2)),
    ("iron-high", "ironing", "Iron at a high temperature", "Călcare la temperatură ridicată", iron(3)),
    ("iron-none", "ironing", "Do not iron", "A nu se călca", iron(crossed=True)),
    ("iron-no-steam", "ironing", "Do not steam iron", "A nu se călca cu abur", iron(steam=True)),

    ("wetclean-none", "professional", "Do not wet clean", "Fără curățare umedă profesională", circle("W", crossed=True)),
    ("wetclean", "professional", "Professional wet clean", "Curățare umedă profesională", circle("W")),
    ("wetclean-delicate", "professional", "Wet clean, delicate", "Curățare umedă, delicată", circle("W", 1)),
    ("wetclean-very-delicate", "professional", "Wet clean, very delicate", "Curățare umedă, foarte delicată", circle("W", 2)),
    ("dryclean-p", "professional", "Dry clean only with PCE", "Curățare chimică numai cu PCE", circle("P")),
    ("dryclean-p-gentle", "professional", "Gentle dry clean with PCE", "Curățare chimică delicată cu PCE", circle("P", 1)),
    ("dryclean-f", "professional", "Dry clean with petroleum solvent only", "Curățare chimică numai cu solvent pe bază de petrol", circle("F")),
    ("dryclean-f-gentle", "professional", "Delicate dry clean with petroleum solvent only", "Curățare chimică delicată cu solvent pe bază de petrol", circle("F", 1)),
    ("dryclean-a", "professional", "Dry clean with any solvent", "Curățare chimică cu orice solvent", circle("A")),
    ("dryclean-none", "professional", "Do not dry clean", "A nu se curăța chimic", circle(crossed=True)),
    ("dryclean-only", "professional", "Dry clean only", "Numai curățare chimică", circle()),
]

GROUPS = {
    "washing": ("Washing", "Spălare"),
    "bleaching": ("Bleaching", "Înălbire"),
    "drying": ("Drying", "Uscare"),
    "ironing": ("Ironing", "Călcare"),
    "professional": ("Professional textile care", "Curățare profesională"),
}

# one sentence per symbol, for the overview sheet
DESC = {
    "wash-none": "Materialul nu se spală nici în mașină, nici manual.",
    "wash-hand": "Se spală doar cu mâna, în apă călduță și fără frecare.",
    "wash-30": "Spălare în mașină pe program normal, cu apă de cel mult 30°C.",
    "wash-30-gentle": "Program delicat, cu agitare și centrifugare reduse, la maximum 30°C.",
    "wash-30-very-gentle": "Program foarte delicat, cu agitare minimă și mașina încărcată pe jumătate, la maximum 30°C.",
    "wash-40": "Spălare în mașină pe program normal, cu apă de cel mult 40°C.",
    "wash-40-gentle": "Program delicat, cu agitare și centrifugare reduse, la maximum 40°C.",
    "wash-40-very-gentle": "Program foarte delicat, cu agitare minimă și mașina încărcată pe jumătate, la maximum 40°C.",
    "wash-60": "Spălare în mașină pe program normal, cu apă de cel mult 60°C.",
    "wash-60-gentle": "Program delicat, cu agitare și centrifugare reduse, la maximum 60°C.",
    "wash-95": "Spălare în mașină pe program normal, cu apă de cel mult 95°C.",
    "bleach-none": "Materialul nu suportă niciun fel de înălbitor.",
    "bleach-any": "Suportă înălbitor de orice fel, inclusiv pe bază de clor.",
    "bleach-non-chlorine": "Suportă doar înălbitor pe bază de oxigen, niciodată clor.",
    "tumble-low": "Se poate usca în uscător, dar numai la temperatură scăzută.",
    "tumble-medium": "Se poate usca în uscător, la temperatură medie.",
    "tumble-none": "Nu se usucă în uscător, pentru că fibrele se strâng și se deformează.",
    "dry-line": "Se usucă atârnat pe sârmă sau pe umeraș, după centrifugare.",
    "dry-drip-line": "Se atârnă ud, fără stoarcere, și se lasă să se scurgă.",
    "dry-flat": "Se usucă întins pe orizontală, ca să nu se lase în lungime.",
    "dry-drip-flat": "Se întinde ud pe orizontală, fără stoarcere și fără centrifugare.",
    "dry-line-shade": "Se atârnă la uscat ferit de soare, care decolorează materialul.",
    "dry-drip-line-shade": "Se atârnă ud și ferit de soare, fără stoarcere.",
    "dry-flat-shade": "Se usucă întins pe orizontală, la umbră.",
    "dry-drip-flat-shade": "Se întinde ud pe orizontală, la umbră, fără stoarcere.",
    "iron-low": "Se calcă la temperatură scăzută, până în 110°C.",
    "iron-medium": "Se calcă la temperatură medie, până în 150°C.",
    "iron-high": "Se calcă la temperatură ridicată, până în 200°C.",
    "iron-none": "Nu se calcă, pentru că fierul strică fibrele și luciul materialului.",
    "iron-no-steam": "Se calcă doar uscat, fără abur și fără pulverizare cu apă.",
    "wetclean-none": "Nu se curăță umed profesional, chiar dacă merge la curățătorie chimică.",
    "wetclean": "Se curăță umed, cu apă și detergenți speciali, într-o curățătorie profesională.",
    "wetclean-delicate": "Curățare umedă profesională, pe program delicat.",
    "wetclean-very-delicate": "Curățare umedă profesională, pe cel mai delicat program.",
    "dryclean-p": "Curățare chimică profesională cu percloretilenă, pe program normal.",
    "dryclean-p-gentle": "Curățare chimică cu percloretilenă, pe program delicat.",
    "dryclean-f": "Curățare chimică doar cu solvent pe bază de petrol.",
    "dryclean-f-gentle": "Curățare chimică cu solvent pe bază de petrol, pe program delicat.",
    "dryclean-a": "Curățare chimică profesională cu orice solvent obișnuit.",
    "dryclean-none": "Materialul nu se dă la curățătorie chimică.",
    "dryclean-only": "Se curăță numai profesional, la curățătorie.",
}


PAGE = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Simboluri de întreținere</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,700&display=swap" rel="stylesheet">
<style>
:root{--black:#1D1D1F;--greytext:#707173;--greystroke:#C8CBD0;--greybg:#F2F2F2}
*{box-sizing:border-box}
body{margin:0;background:#fff;color:var(--black);
  font-family:'DM Sans',system-ui,sans-serif;line-height:115%;
  -webkit-font-smoothing:antialiased}
.wrap{max-width:520px;margin:0 auto;padding:32px 20px 64px}
h1{font-size:24px;font-weight:700;letter-spacing:-.02em;margin:0 0 8px}
.intro{font-size:15px;line-height:140%;color:var(--greytext);margin:0 0 32px}
h2{font-size:13px;font-weight:500;letter-spacing:.08em;text-transform:uppercase;
  color:var(--greytext);margin:36px 0 4px;padding-bottom:12px;
  border-bottom:1px solid var(--greystroke)}
ul{list-style:none;margin:0;padding:0}
li{display:flex;gap:16px;align-items:flex-start;padding:18px 0;
  border-bottom:1px solid var(--greybg)}
li:last-child{border-bottom:0}
.ico{flex:0 0 40px;height:40px;color:var(--black)}
.ico svg{width:40px;height:40px;display:block}
.txt{flex:1;min-width:0;padding-top:2px}
.name{font-size:16px;font-weight:500;margin:0 0 6px}
.desc{font-size:14px;line-height:140%;color:var(--greytext);margin:0}
footer{margin-top:40px;font-size:12px;line-height:150%;color:var(--greytext)}
</style>
</head>
<body>
<div class="wrap">
<h1>Simboluri de întreținere</h1>
<p class="intro">Cele 41 de simboluri de pe eticheta unui material, grupate pe cele cinci categorii, cu explicația fiecăruia într-o frază.</p>
__BODY__
<footer>Simboluri desenate după standardul ISO 3758 (GINETEX). Set preluat și redesenat după ghidul public de etichete al C&amp;A.</footer>
</div>
</body>
</html>
"""


def build_overview():
    body = []
    for gid, (_, ro_group) in GROUPS.items():
        body.append(f"<h2>{ro_group}</h2>\n<ul>")
        for slug, group, _en, ro, markup in SYMBOLS:
            if group != gid:
                continue
            icon = markup.strip().replace(
                '<svg ', '<svg role="img" aria-label="' + ro + '" '
            )
            body.append(
                f'<li><span class="ico">{icon}</span>'
                f'<span class="txt"><p class="name">{ro}</p>'
                f'<p class="desc">{DESC[slug]}</p></span></li>'
            )
        body.append("</ul>")
    return PAGE.replace("__BODY__", "\n".join(body))


def main():
    os.makedirs(OUT, exist_ok=True)
    manifest = {
        "source": "https://www.c-and-a.com/eu/en/shop/care-and-washing-symbols-made-simple",
        "standard": "ISO 3758 / GINETEX",
        "viewBox": "0 0 48 48",
        "groups": [{"id": k, "label_en": v[0], "label_ro": v[1]} for k, v in GROUPS.items()],
        "symbols": [],
    }
    for slug, group, en, ro, markup in SYMBOLS:
        with open(os.path.join(OUT, f"{slug}.svg"), "w") as f:
            f.write(markup)
        manifest["symbols"].append(
            {
                "id": slug,
                "group": group,
                "label_en": en,
                "label_ro": ro,
                "desc_ro": DESC[slug],
                "file": f"{slug}.svg",
            }
        )
    with open(os.path.join(OUT, "care-symbols.json"), "w") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write("\n")
    page = os.path.join(ROOT, "simboluri-intretinere.html")
    with open(page, "w") as f:
        f.write(build_overview())
    print(f"{len(SYMBOLS)} symbols -> {OUT}\noverview -> {page}")


if __name__ == "__main__":
    main()
