#!/usr/bin/env bash
# Usage: NVIDIA_API_KEY=nvapi-... PAIR_TOKEN=pick-a-secret bash run.sh
set -e
cd "$(dirname "$0")"

: "${NVIDIA_API_KEY:?Set NVIDIA_API_KEY (get one at build.nvidia.com)}"
export PAIR_TOKEN="${PAIR_TOKEN:-changeme}"

if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi

# Self-signed cert: phone browsers only allow the microphone over HTTPS.
if [ ! -f cert.pem ]; then
  IP=$(hostname -I | awk '{print $1}')
  openssl req -x509 -newkey rsa:2048 -nodes -keyout key.pem -out cert.pem -days 365 \
    -subj "/CN=$IP" -addext "subjectAltName=IP:$IP"
fi

IP=$(hostname -I | awk '{print $1}')
echo
echo "Open on your phone (same Wi-Fi/hotspot):  https://$IP:8000/?token=$PAIR_TOKEN"
echo "Accept the certificate warning once, then allow the microphone."
echo

exec .venv/bin/uvicorn server:app --host 0.0.0.0 --port 8000 \
  --ssl-keyfile key.pem --ssl-certfile cert.pem
