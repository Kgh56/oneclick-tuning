# Homepage gh-mapping.de

- `seite/` – die fertige Homepage, so wie sie im Internet erscheint (Caddy liefert diesen Ordner aus).
- `quelle/` – Vorlage, Rechtstexte und `bauen.py`. Nach Änderungen an der Vorlage, den FAQ oder den Rechtstexten:
  `python3 homepage/quelle/bauen.py` – das erneuert `seite/`.
- `einrichten.sh` – einmalig auf dem Server: `sudo sh /opt/oneclick/app/homepage/einrichten.sh`

Änderungen gehen live, sobald im Admin-Bereich unter Einstellungen „Update“ gedrückt wird.
