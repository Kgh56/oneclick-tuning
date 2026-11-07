#!/bin/sh
# Einmalig auf dem Server ausfuehren:  sudo sh /opt/oneclick/app/homepage/einrichten.sh
# Danach liefert Caddy die Homepage gh-mapping.de direkt vom Server aus (HTTPS automatisch).
# Spaetere Aenderungen an der Homepage gehen ueber Admin -> Einstellungen -> Update live.
set -e
[ "$(id -u)" = 0 ] || { echo "Bitte mit sudo starten."; exit 1; }

SEITE=/opt/oneclick/app/homepage/seite
DOMAIN=gh-mapping.de
[ -f "$SEITE/index.html" ] || { echo "Homepage fehlt in $SEITE - zuerst Update im Admin ausfuehren."; exit 1; }

# Caddy darf die Dateien lesen (nur die Homepage, die uebrigen Daten bleiben geschuetzt)
chmod o+x /opt/oneclick /opt/oneclick/app /opt/oneclick/app/homepage
chmod -R o+rX "$SEITE"

cp /opt/oneclick/app/homepage/homepage.caddy /etc/caddy/homepage.caddy

grep -q "import /etc/caddy/homepage.caddy" /etc/caddy/Caddyfile || \
  printf '\nimport /etc/caddy/homepage.caddy\n' >> /etc/caddy/Caddyfile

caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null
systemctl reload caddy
echo "Fertig. Caddy liefert jetzt $DOMAIN und www.$DOMAIN aus."
echo "Jetzt bei STRATO die DNS-Eintraege (A-Record) auf die IP dieses Servers stellen."
