import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.bootstrap import bootstrap_falls_noetig, ist_bootstrapped
from app.database import SessionLocal
from app.routers import (
    bootstrap as bootstrap_router,
    buchungen,
    dkb,
    forecast,
    overview,
    topf_umbuchung,
    trade_republic,
    umbuchungen,
    zuordnen,
)
from app.tr_sync import sync_schleife
from app.watcher import scan_schleife
from app.webutils import ctx, templates

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-5s %(name)s: %(message)s")
logger = logging.getLogger("budget_tracker")


class IngressPathMiddleware:
    """Liest X-Ingress-Path und setzt scope['root_path'], damit alle
    server-seitig erzeugten Links/Redirects unter dem von Home Assistant
    vergebenen Ingress-Praefix funktionieren."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers") or [])
            ingress_path = headers.get(b"x-ingress-path")
            if ingress_path:
                scope["root_path"] = ingress_path.decode()
        await self.app(scope, receive, send)


_hintergrund_tasks: list[asyncio.Task] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = SessionLocal()
    try:
        bootstrap_falls_noetig(db)
    finally:
        db.close()

    _hintergrund_tasks.append(asyncio.create_task(scan_schleife()))
    logger.info("Verzeichnis-Watcher gestartet.")
    # Laeuft auch ohne hinterlegte Anmeldung mit: der Abgleich prueft das selbst
    # und ueberspringt sich, solange keine Sitzung existiert.
    _hintergrund_tasks.append(asyncio.create_task(sync_schleife()))
    logger.info("Trade-Republic-Abgleich gestartet.")
    yield
    for task in _hintergrund_tasks:
        task.cancel()


app = FastAPI(title="Budget-Tracker", lifespan=lifespan)
app.add_middleware(IngressPathMiddleware)


@app.exception_handler(StarletteHTTPException)
async def fehlerseite(request: Request, exc: StarletteHTTPException):
    """Fehler im gewohnten Layout statt als rohes JSON.

    Die Routen melden Eingabefehler ueber HTTPException mit sprechendem
    detail-Text. Ohne diesen Handler landet der Nutzer auf einer nackten
    {"detail": ...}-Seite ohne Navigation und ohne Weg zurueck.
    """
    return templates.TemplateResponse(
        "fehler.html",
        ctx(request, status=exc.status_code, meldung=exc.detail),
        status_code=exc.status_code,
    )


@app.middleware("http")
async def bootstrap_gate(request: Request, call_next):
    pfad = request.url.path
    if pfad.startswith("/bootstrap"):
        return await call_next(request)

    db = SessionLocal()
    try:
        if not ist_bootstrapped(db):
            praefix = request.scope.get("root_path") or ""
            return RedirectResponse(url=f"{praefix}/bootstrap", status_code=303)
    finally:
        db.close()
    return await call_next(request)


app.include_router(bootstrap_router.router)
app.include_router(overview.router)
app.include_router(buchungen.router)
app.include_router(zuordnen.router)
app.include_router(umbuchungen.router)
app.include_router(topf_umbuchung.router)
app.include_router(forecast.router)
app.include_router(trade_republic.router)
app.include_router(dkb.router)
