"""Server-seitig gerenderte, abhaengigkeitsfreie SVG-Grafik fuer die
12-Monats-Tiefpunkt-Prognose - kein JS-Chart-Framework noetig."""


def render_prognose_chart(monatswerte, breite: int = 640, hoehe: int = 180) -> str:
    if not monatswerte:
        return ""

    werte = [float(m.saldo) for m in monatswerte]
    minimum = min(werte + [0.0])
    maximum = max(werte + [0.0])
    spanne = (maximum - minimum) or 1.0
    n = len(werte)
    padding_x, padding_y = 12, 20
    plot_breite = breite - 2 * padding_x
    plot_hoehe = hoehe - 2 * padding_y

    def x(i: int) -> float:
        return padding_x + (plot_breite * i / max(n - 1, 1))

    def y(v: float) -> float:
        return padding_y + plot_hoehe * (1 - (v - minimum) / spanne)

    punkte = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(werte))
    null_y = y(0.0)

    kreise = "".join(
        f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="4" class="{"chart-punkt-minus" if v < 0 else "chart-punkt"}"><title>{m.monat.strftime("%m/%Y")}: {v:.2f} €</title></circle>'
        for i, (v, m) in enumerate(zip(werte, monatswerte))
    )

    return (
        f'<svg viewBox="0 0 {breite} {hoehe}" class="prognose-chart" role="img" aria-label="12-Monats-Prognose">'
        f'<line x1="{padding_x}" y1="{null_y:.1f}" x2="{breite - padding_x}" y2="{null_y:.1f}" class="chart-nulllinie" />'
        f'<polyline points="{punkte}" fill="none" class="chart-linie" />'
        f"{kreise}"
        f"</svg>"
    )
