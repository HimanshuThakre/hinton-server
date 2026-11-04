# Eyes: a voice agent for your phone, powered by NVIDIA NIM

Your phone shows animated eyes and handles mic + speaker. Your Ubuntu laptop
runs the server, the NIM-hosted LLM calls, and the terminal commands.

## Run

```bash
sudo apt install -y python3-venv openssl
export NVIDIA_API_KEY=nvapi-...      # from build.nvidia.com
export PAIR_TOKEN=pick-a-secret      # phone must present this
bash run.sh
```

Open the printed `https://<laptop-ip>:8000/?token=...` link in **Chrome on
your phone** (laptop and phone on the same Wi-Fi, or the phone's hotspot).
Accept the certificate warning, allow the microphone, tap **Start listening**.

If a firewall is on: `sudo ufw allow 8000/tcp`.

## Try saying
- "What's my disk usage?"
- "List the files in my home folder."
- "Create a folder called test." (asks you to confirm first)

## Config (env vars)
| Var | Default | Meaning |
|---|---|---|
| `NIM_MODEL` | `meta/llama-3.1-70b-instruct` | Any tool-calling model from build.nvidia.com |
| `WORKDIR` | `~` | Directory commands run in |
| `PAIR_TOKEN` | `changeme` | Shared secret for the phone |

## Safety
- Commands in `SAFE_COMMANDS` (server.py) with no shell metacharacters run
  automatically. Everything else asks "Run this command?" first. Answer by
  voice ("yes"/"no") or by tapping.
- Change the token from the default, and only run this on networks you trust.
- Don't expose port 8000 to the internet.

## Notes and next steps
- Speech-to-text and text-to-speech use the phone browser's built-in engines
  (Chrome on Android works best). Swap in NVIDIA speech models or
  Whisper/Piper on the server later for better quality.
- Wake word here is simple text matching ("hey buddy"). For true always-on
  detection, use openWakeWord or Porcupine.
- To use it away from home, install Tailscale on both devices.
