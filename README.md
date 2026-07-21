# budget-tracker-importer

Home-Assistant-Add-on-Repository für **Budget-Tracker** – eine private
Web-App zur Verwaltung von vier virtuellen Spartöpfen auf einem Konto.

Das eigentliche Add-on liegt in [`budget_tracker/`](./budget_tracker); alle
Installations-, Einrichtungs- und Betriebshinweise stehen in
[`budget_tracker/README.md`](./budget_tracker/README.md).

## Repository als Add-on-Store hinzufügen

**Home Assistant → Einstellungen → Add-ons → Add-on-Store → ⋮ → Repositories**
und die URL dieses Repositories eintragen. Danach erscheint **Budget-Tracker**
als installierbares Add-on.

## Stack

FastAPI + SQLite + SQLAlchemy + Alembic, Ingress-Einbindung, gebaut für
`aarch64`/`amd64` auf schlanker Alpine-Basis.

## Datenschutz

Der Code in diesem Repository ist öffentlich; echte Daten (CSV-Importe,
die SQLite-Datenbank und eine eventuelle `seed-data.json`) bleiben
ausschließlich auf dem Home-Assistant-Host und werden nie committet
(siehe [`.gitignore`](./.gitignore)).
