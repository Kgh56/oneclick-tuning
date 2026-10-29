#!/usr/bin/env bash
# OneClick Tuning - Installation auf einem frischen Ubuntu-Server (24.04 / 26.04)
#
# Aufruf (als root):
#   curl -fsSL https://raw.githubusercontent.com/Kgh56/oneclick-tuning/main/install.sh | bash
#
# Richtet ein: Webseite (Dienst, startet nach Neustart automatisch), HTTPS (Caddy),
# Syncthing fuer den WinOLS-Sync, Firewall, automatische Sicherheitsupdates,
# taegliches Backup. Kann gefahrlos erneut ausgefuehrt werden (= Update).
set -euo pipefail

REPO_URL="${ONECLICK_REPO:-https://github.com/Kgh56/oneclick-tuning.git}"
BRANCH="${ONECLICK_BRANCH:-main}"
BASIS=/opt/oneclick
APP="$BASIS/app"
VENV="$BASIS/venv"
ST_HOME="$BASIS/syncthing"
NUTZER=oneclick

gruen() { printf '\n\033[1;32m%s\033[0m\n' "$*"; }
fehler() { printf '\n\033[1;31mFEHLER: %s\033[0m\n' "$*" >&2; exit 1; }
frage() { local antwort; read -rp "$1" antwort </dev/tty; printf '%s' "$antwort"; }

[ "$(id -u)" -eq 0 ] || fehler "Bitte als root ausführen."
grep -qi ubuntu /etc/os-release || fehler "Dieses Skript ist für Ubuntu gemacht."

# ---------------------------------------------------------------------------
gruen "1/8  Angaben"
DOMAIN="${ONECLICK_DOMAIN:-}"
if [ -z "$DOMAIN" ] && [ -f /etc/caddy/Caddyfile ] && grep -q "# oneclick" /etc/caddy/Caddyfile; then
  DOMAIN=$(awk '/# oneclick/{getline; print $1; exit}' /etc/caddy/Caddyfile)
fi
[ -n "$DOMAIN" ] || DOMAIN=$(frage "Domain der Seite (z. B. files.deine-firma.de): ")
DOMAIN="${DOMAIN#https://}"; DOMAIN="${DOMAIN#http://}"; DOMAIN="${DOMAIN%%/*}"
[ -n "$DOMAIN" ] || fehler "Keine Domain angegeben."
echo "Domain: $DOMAIN"

# ---------------------------------------------------------------------------
gruen "2/8  Pakete installieren (dauert ein paar Minuten)"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q python3 python3-venv git curl ufw unattended-upgrades syncthing debian-keyring debian-archive-keyring apt-transport-https gnupg
if ! apt-get install -y -q caddy 2>/dev/null; then
  # Caddy aus dem offiziellen Repository, falls Ubuntu es nicht mitbringt
  curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -q && apt-get install -y -q caddy
fi
dpkg-reconfigure -f noninteractive unattended-upgrades >/dev/null 2>&1 || true

# ---------------------------------------------------------------------------
gruen "3/8  Programm holen"
id "$NUTZER" >/dev/null 2>&1 || useradd --system --home-dir "$BASIS" --shell /usr/sbin/nologin "$NUTZER"
mkdir -p "$BASIS"
if [ -d "$APP/.git" ]; then
  git -C "$APP" fetch -q origin "$BRANCH" && git -C "$APP" reset -q --hard "origin/$BRANCH"
else
  git clone -q --branch "$BRANCH" "$REPO_URL" "$APP"
fi
chown -R "$NUTZER:$NUTZER" "$BASIS"
[ -d "$VENV" ] || sudo -u "$NUTZER" python3 -m venv "$VENV"
sudo -u "$NUTZER" "$VENV/bin/pip" install -q --upgrade pip
sudo -u "$NUTZER" "$VENV/bin/pip" install -q -r "$APP/requirements.txt"

# ---------------------------------------------------------------------------
gruen "4/8  Syncthing (WinOLS-Sync) einrichten"
if [ ! -f "$ST_HOME/config.xml" ]; then
  sudo -u "$NUTZER" syncthing generate --home="$ST_HOME" >/dev/null
fi
# Weboberflaeche nur lokal, keine Statistik, keine Selbst-Updates (macht apt)
sudo -u "$NUTZER" python3 - "$ST_HOME/config.xml" <<'PY'
import re, sys
p = sys.argv[1]; s = open(p).read()
s = re.sub(r"(<gui[^>]*>\s*<address>)[^<]*(</address>)", r"\g<1>127.0.0.1:8384\g<2>", s, count=1)
for tag, wert in [("startBrowser", "false"), ("urAccepted", "-1"), ("autoUpgradeIntervalH", "0"), ("crashReportingEnabled", "false")]:
    s = re.sub(rf"<{tag}>[^<]*</{tag}>", f"<{tag}>{wert}</{tag}>", s)
open(p, "w").write(s)
PY
ST_KEY=$(grep -oP '(?<=<apikey>)[^<]+' "$ST_HOME/config.xml" | head -1)

cat > /etc/systemd/system/oneclick-syncthing.service <<EOF
[Unit]
Description=OneClick Tuning - Syncthing (WinOLS-Sync)
After=network-online.target
Wants=network-online.target

[Service]
User=$NUTZER
ExecStart=/usr/bin/syncthing serve --home=$ST_HOME --no-browser --no-restart --no-default-folder
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# ---------------------------------------------------------------------------
gruen "5/8  Webseite einrichten"
sudo -u "$NUTZER" python3 - "$APP/config.json" "$DOMAIN" "$ST_KEY" <<'PY'
import json, os, sys
p, domain, key = sys.argv[1:4]
cfg = json.load(open(p)) if os.path.exists(p) else {"aufbewahrung_tage": 90}
cfg.update(basis_url=f"https://{domain}", syncthing_api_key=key, syncthing_url="http://127.0.0.1:8384")
json.dump(cfg, open(p, "w"), indent=2, ensure_ascii=False)
os.chmod(p, 0o600)
PY

cat > /etc/systemd/system/oneclick.service <<EOF
[Unit]
Description=OneClick Tuning - Webseite
After=network-online.target oneclick-syncthing.service
Wants=network-online.target

[Service]
User=$NUTZER
WorkingDirectory=$APP
Environment=ONECLICK_HOST=127.0.0.1
Environment=PYTHONUNBUFFERED=1
ExecStart=$VENV/bin/python $APP/app.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# HTTPS-Zertifikat holt Caddy automatisch
if ! grep -q "# oneclick" /etc/caddy/Caddyfile 2>/dev/null; then
  cp /etc/caddy/Caddyfile /etc/caddy/Caddyfile.vorher 2>/dev/null || true
fi
cat > /etc/caddy/Caddyfile <<EOF
# oneclick
$DOMAIN {
	encode gzip
	reverse_proxy 127.0.0.1:5000
}
EOF

# ---------------------------------------------------------------------------
gruen "6/8  Firewall"
ufw allow OpenSSH >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw allow 22000/tcp >/dev/null    # Syncthing
ufw allow 22000/udp >/dev/null
ufw allow 21027/udp >/dev/null
ufw --force enable >/dev/null

# ---------------------------------------------------------------------------
gruen "7/8  Tägliches Backup und Update-Befehl"
mkdir -p /var/backups/oneclick
cat > /etc/cron.daily/oneclick-backup <<EOF
#!/bin/sh
# Archiv + Einstellungen sichern, 14 Tage aufheben
tar czf /var/backups/oneclick/oneclick-\$(date +%F).tar.gz -C $APP archiv config.json benutzer.json 2>/dev/null
find /var/backups/oneclick -name 'oneclick-*.tar.gz' -mtime +14 -delete
EOF
chmod 755 /etc/cron.daily/oneclick-backup

cat > /usr/local/bin/oneclick-update <<EOF
#!/bin/sh
# Neueste Version holen und neu starten
set -e
sudo -u $NUTZER git -C $APP fetch -q origin $BRANCH
sudo -u $NUTZER git -C $APP reset -q --hard origin/$BRANCH
sudo -u $NUTZER $VENV/bin/pip install -q -r $APP/requirements.txt
systemctl restart oneclick
echo "Aktualisiert."
EOF
chmod 755 /usr/local/bin/oneclick-update

# ---------------------------------------------------------------------------
gruen "8/8  Starten"
systemctl daemon-reload
systemctl enable -q --now oneclick-syncthing
systemctl enable -q oneclick
systemctl restart oneclick
systemctl enable -q caddy
systemctl restart caddy

if ! sudo -u "$NUTZER" test -s "$APP/benutzer.json"; then
  gruen "Admin-Zugang anlegen"
  ADMIN=$(frage "Admin-Benutzername: ")
  [ -n "$ADMIN" ] || ADMIN="admin"
  until sudo -u "$NUTZER" "$VENV/bin/python" "$APP/app.py" admin "$ADMIN" </dev/tty; do
    echo "Bitte nochmal."
  done
  systemctl restart oneclick
fi

# Pruefen, ob die Domain auf diesen Server zeigt
SERVER_IP=$(curl -4 -fsS https://api.ipify.org 2>/dev/null || true)
DOMAIN_IP=$(getent ahostsv4 "$DOMAIN" 2>/dev/null | awk 'NR==1{print $1}')
sleep 3
if systemctl is-active -q oneclick && systemctl is-active -q caddy; then
  gruen "Fertig!"
  echo "Seite:        https://$DOMAIN"
  echo "Admin-Login:  https://$DOMAIN/login"
  echo "Update später mit:  oneclick-update"
  if [ -n "$SERVER_IP" ] && [ "$SERVER_IP" != "$DOMAIN_IP" ]; then
    printf '\n\033[1;33mACHTUNG: %s zeigt noch nicht auf diesen Server (%s, Domain: %s).\n' "$DOMAIN" "$SERVER_IP" "${DOMAIN_IP:-keine}"
    printf 'Beim Domain-Anbieter einen A-Eintrag auf %s setzen. HTTPS startet dann von selbst.\033[0m\n' "$SERVER_IP"
  fi
else
  fehler "Ein Dienst läuft nicht. Ausgabe von:  journalctl -u oneclick -n 50 --no-pager"
fi
