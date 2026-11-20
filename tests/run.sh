#!/usr/bin/env bash
# Füstteszt egy ELDOBHATÓ konténerben: üres adatbázis, a users.example.json felhasználói.
# Az éles példányt (és a data/ mappát) nem érinti.
#
#   ./tests/run.sh            # alapból a 8091-es porton
#   TEST_PORT=9000 ./tests/run.sh
set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${TEST_PORT:-8091}"
NAME="reservation-test-$$"
TMP="$(mktemp -d)"
chmod 777 "$TMP"   # a konténer az 1000-es UID-dal ír bele

cleanup() {
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  rm -rf "$TMP"
}
trap cleanup EXIT

echo "Fordítás-ellenőrzés..."
python3 tests/i18n_check.py

echo "Image build..."
docker compose build -q

echo "Tesztkonténer indítása (port $PORT)..."
docker run -d --name "$NAME" -p "127.0.0.1:$PORT:8000" \
  -v "$TMP:/data" \
  -v "$PWD/config/users.example.json:/config/users.json:ro" \
  reservation:latest >/dev/null

for _ in $(seq 1 30); do
  if python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:$PORT/healthz')" 2>/dev/null; then
    break
  fi
  sleep 0.5
done

BASE_URL="http://127.0.0.1:$PORT" python3 tests/smoke_test.py || {
  echo; echo "--- konténer log ---"; docker logs --tail 50 "$NAME"; exit 1;
}

echo
echo "Konténer log (angol nyelvű kell legyen):"
docker logs "$NAME" 2>&1 | grep -v '"GET \|"POST ' | sed 's/^/  /'
if docker logs "$NAME" 2>&1 | grep -v '"GET \|"POST ' | grep -q '[áéíóöőúüűÁÉÍÓÖŐÚÜŰ]'; then
  echo "  ✗ magyar szöveg a konténer logban"; exit 1
fi
echo "  ✓ a log angol nyelvű"
