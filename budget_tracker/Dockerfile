ARG BUILD_FROM
FROM $BUILD_FROM

ENV LANG=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Alpine-Basis: nur Python + Laufzeit-Libs dauerhaft, Build-Toolchain
# (pip, Compiler) wird nach der Installation wieder entfernt, um das
# Image fuer aarch64 klein zu halten. Die pip-installierten Pakete
# bleiben davon unberuehrt, da apk sie nicht kennt.
RUN apk add --no-cache python3 sqlite-libs libffi \
    && apk add --no-cache --virtual .build-deps \
        py3-pip gcc musl-dev python3-dev libffi-dev \
    && pip install --no-cache-dir --break-system-packages --upgrade pip

WORKDIR /app

COPY app/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --break-system-packages -r /app/requirements.txt \
    && apk del .build-deps

COPY app /app/app
COPY alembic /app/alembic
COPY alembic.ini /app/alembic.ini
COPY run.sh /run.sh
RUN chmod a+x /run.sh

EXPOSE 8000

CMD [ "/run.sh" ]
