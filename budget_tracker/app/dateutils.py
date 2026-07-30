import calendar
import datetime as dt
import logging
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger("budget_tracker.dateutils")

# Gespeichert wird durchgehend UTC (datetime.utcnow), angezeigt wird lokale
# Zeit. Im Sommer sind das zwei Stunden Unterschied - genug, dass ein Nutzer
# den letzten Abgleich fuer veraltet haelt oder eine Buchung dem falschen Tag
# zuordnet.
try:
    LOKALE_ZONE: ZoneInfo | None = ZoneInfo("Europe/Berlin")
except ZoneInfoNotFoundError:  # pragma: no cover - nur ohne tzdata im Image
    logger.warning("Zeitzonendaten fehlen, Zeiten werden als UTC angezeigt.")
    LOKALE_ZONE = None


def nach_lokaler_zeit(zeitpunkt: dt.datetime) -> dt.datetime:
    """Rechnet einen gespeicherten (naiven) UTC-Zeitstempel in lokale Zeit um.

    Naiv heisst hier wirklich UTC: alles in der Datenbank kommt aus
    datetime.utcnow(). Ein bereits zeitzonenbehafteter Wert wird umgerechnet,
    nicht neu interpretiert.
    """
    if zeitpunkt.tzinfo is None:
        zeitpunkt = zeitpunkt.replace(tzinfo=dt.timezone.utc)
    if LOKALE_ZONE is None:
        return zeitpunkt
    return zeitpunkt.astimezone(LOKALE_ZONE)


def add_months(d: dt.date, months: int) -> dt.date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return dt.date(year, month, day)


def month_start(d: dt.date) -> dt.date:
    return d.replace(day=1)


def month_end(d: dt.date) -> dt.date:
    last_day = calendar.monthrange(d.year, d.month)[1]
    return d.replace(day=last_day)


def safe_date(year: int, month: int, day: int) -> dt.date:
    last_day = calendar.monthrange(year, month)[1]
    return dt.date(year, month, min(day, last_day))
