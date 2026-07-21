"""Server-seitig gerenderte, abhaengigkeitsfreie SVG-Sparkline fuer die
12-Monats-Tiefpunkt-Prognose - kein JS-Chart-Framework noetig."""

_MONATE_KURZ = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]

TOPF_FARBEN = {
    "kredit": "var(--t-kredit)",
    "renov": "var(--t-renov)",
    "urlaub": "var(--t-urlaub)",
    "sonder": "var(--t-sonder)",
}


def _monat_kurz(d) -> str:
    return f"{_MONATE_KURZ[d.month - 1]} {d.strftime('%y')}"


def render_prognose_chart(monatswerte, topf_klasse: str = "sonder", breite: int = 300, hoehe: int = 108) -> str:
    if not monatswerte:
        return ""

    werte = [float(m.saldo) for m in monatswerte]
    minus_warnung = min(werte) < 0
    farbe = "var(--warn)" if minus_warnung else TOPF_FARBEN.get(topf_klasse, "var(--accent)")

    minimum = min(werte + [0.0])
    maximum = max(werte + [0.0])
    spanne = (maximum - minimum) or 1.0
    n = len(werte)
    pad_x, pad_top, pad_bottom = 10, 8, 20

    plot_breite = breite - 2 * pad_x
    plot_hoehe = hoehe - pad_top - pad_bottom

    def x(i: int) -> float:
        return pad_x + (plot_breite * i / max(n - 1, 1))

    def y(v: float) -> float:
        return pad_top + plot_hoehe * (1 - (v - minimum) / spanne)

    punkte = [(x(i), y(v)) for i, v in enumerate(werte)]
    punkte_str = " ".join(f"{px:.1f},{py:.1f}" for px, py in punkte)
    flaeche = (
        f"M{punkte[0][0]:.1f},{punkte[0][1]:.1f} "
        + " ".join(f"L{px:.1f},{py:.1f}" for px, py in punkte[1:])
        + f" L{punkte[-1][0]:.1f},{hoehe - pad_bottom:.1f} L{punkte[0][0]:.1f},{hoehe - pad_bottom:.1f} Z"
    )
    null_y = y(0.0)

    tiefster_index = min(range(n), key=lambda i: werte[i])
    tx, ty = punkte[tiefster_index]

    beschriftungen = ""
    for i in (0, n // 3, (2 * n) // 3, n - 1):
        anchor = "start" if i == 0 else ("end" if i == n - 1 else "middle")
        beschriftungen += (
            f'<text x="{x(i):.1f}" y="{hoehe - 6}" text-anchor="{anchor}" '
            f'font-family="IBM Plex Mono" font-size="8" fill="var(--ink-faint)">'
            f"{_monat_kurz(monatswerte[i].monat)}</text>"
        )

    return (
        f'<svg class="sc-spark" viewBox="0 0 {breite} {hoehe}" preserveAspectRatio="none" '
        f'role="img" aria-label="12-Monats-Prognose">'
        f'<path d="{flaeche}" fill="{farbe}" fill-opacity="0.1" stroke="none"/>'
        f'<line x1="{pad_x}" y1="{null_y:.1f}" x2="{breite - pad_x}" y2="{null_y:.1f}" '
        f'stroke="var(--line-strong)" stroke-width="1" stroke-dasharray="3 3"/>'
        f'<polyline points="{punkte_str}" fill="none" stroke="{farbe}" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round"/>'
        f'<circle cx="{tx:.1f}" cy="{ty:.1f}" r="3.5" fill="#fff" stroke="{farbe}" stroke-width="2"/>'
        f"{beschriftungen}"
        f"</svg>"
    )
