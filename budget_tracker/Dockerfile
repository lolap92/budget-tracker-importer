ARG BUILD_FROM
FROM $BUILD_FROM

ENV LANG=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Debian-Basis statt Alpine seit 1.18.0: pytr haengt zwingend an playwright,
# und davon gibt es kein musl-Wheel - unter Alpine liesse sich pytr also gar
# nicht installieren. Der Browser selbst wird nie gestartet (die Anmeldung holt
# ihren WAF-Token rein in Python, siehe app/tr_client.py); playwright muss nur
# importierbar sein. Deshalb fliegt der mitgelieferte Browser-Treiber nach der
# Installation wieder raus - 131 der 270 MB, die niemals jemand ausfuehrt.
#
# tzdata wird gebraucht, weil die Zeitstempel der Trade-Republic-Timeline in UTC
# kommen und fuer das Buchungsdatum in lokale Zeit umgerechnet werden
# (app/tr_events.py). Ein Compiler ist nicht noetig: alle Abhaengigkeiten
# bringen fertige manylinux-Wheels fuer amd64 und aarch64 mit.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 python3-pip ca-certificates tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY app/requirements.txt /app/requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r /app/requirements.txt \
    && rm -rf "$(python3 -c 'import os, playwright; print(os.path.dirname(playwright.__file__))')/driver"

COPY app /app/app
COPY alembic /app/alembic
COPY alembic.ini /app/alembic.ini
# Nur wegen der Versionsangabe: die App liest sie von hier, statt sie ein
# zweites Mal im Quelltext zu fuehren (app/config.py: version()).
COPY config.yaml /app/config.yaml
COPY run.sh /run.sh
RUN chmod a+x /run.sh

EXPOSE 8000

CMD [ "/run.sh" ]
