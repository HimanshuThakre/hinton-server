"""Voice agent server: phone (eyes UI) <-> WebSocket <-> NVIDIA NIM LLM + terminal tool."""
import asyncio
import json
import os
import subprocess

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, PlainTextResponse
from openai import OpenAI

NVIDIA_API_KEY = os.environ["NVIDIA_API_KEY"]
MODEL = os.environ.get("NIM_MODEL", "meta/llama-3.1-70b-instruct")
TOKEN = os.environ.get("PAIR_TOKEN", "changeme")
WORKDIR = os.path.expanduser(os.environ.get("WORKDIR", "~"))
HERE = os.path.dirname(os.path.abspath(__file__))

client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=NVIDIA_API_KEY, timeout=40.0, max_retries=0)
app = FastAPI()

# Commands that run without asking. Anything else (or anything containing
# shell metacharacters) needs a spoken/tapped "yes" from you first.
SAFE_COMMANDS = {
    "ls", "pwd", "whoami", "date", "uptime", "df", "free", "hostname",
    "uname", "cat", "head", "tail", "wc", "ps", "ip", "echo", "id",
}
META_CHARS = set(";&|><$`\\\n")

SYSTEM_PROMPT = (
    "You are Hinton, a friendly voice assistant shown as a pair of glowing eyes on the "
    "user's phone. Your replies are spoken aloud, so keep them short and plain: "
    "no markdown, no lists, no code blocks. You can run shell commands on the "
    "user's Ubuntu Linux computer with the run_command tool. Use it when the "
    "user asks for something that needs the computer. After a command, "
    "summarise the result briefly in natural speech."
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run a shell command on the user's Ubuntu computer and return its output.",
            "parameters": {
                "type": "object",
                "properties": {"cmd": {"type": "string", "description": "The bash command"}},
                "required": ["cmd"],
            },
        },
    }
]


def is_safe(cmd: str) -> bool:
    if any(c in META_CHARS for c in cmd):
        return False
    parts = cmd.split()
    return bool(parts) and parts[0] in SAFE_COMMANDS


def run_shell(cmd: str) -> str:
    try:
        p = subprocess.run(
            cmd, shell=True, cwd=WORKDIR, capture_output=True, text=True, timeout=30,
            executable="/bin/bash",
        )
        out = (p.stdout + p.stderr).strip()
        out = out[:3000] + ("\n...[truncated]" if len(out) > 3000 else "")
        return f"exit code {p.returncode}\n{out}"
    except subprocess.TimeoutExpired:
        return "Command timed out after 30 seconds."
    except Exception as e:  # noqa: BLE001
        return f"Error: {e}"


@app.get("/")
async def index():
    return FileResponse(os.path.join(HERE, "index.html"))


@app.get("/health")
async def health():
    return PlainTextResponse("ok")


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    if ws.query_params.get("token") != TOKEN:
        await ws.close(code=4401)
        return
    await ws.accept()

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    state = {"confirm": None, "busy": False}

    async def send(obj):
        await ws.send_text(json.dumps(obj))

    async def ask_confirm(cmd: str) -> bool:
        loop = asyncio.get_running_loop()
        state["confirm"] = loop.create_future()
        await send({"type": "confirm", "cmd": cmd})
        try:
            return await asyncio.wait_for(state["confirm"], timeout=60)
        except asyncio.TimeoutError:
            return False
        finally:
            state["confirm"] = None

    async def handle(text: str):
        state["busy"] = True
        try:
            await send({"type": "state", "value": "thinking"})
            messages.append({"role": "user", "content": text})
            for _ in range(6):  # max tool-use rounds
                resp = await asyncio.to_thread(
                    client.chat.completions.create,
                    model=MODEL, messages=messages, tools=TOOLS, temperature=0.4,
                )
                msg = resp.choices[0].message
                messages.append(msg.model_dump(exclude_none=True))
                if not msg.tool_calls:
                    await send({"type": "say", "text": msg.content or "Done."})
                    return
                for call in msg.tool_calls:
                    try:
                        cmd = json.loads(call.function.arguments)["cmd"]
                    except Exception:  # noqa: BLE001
                        cmd = ""
                    if not cmd:
                        result = "Invalid command."
                    elif is_safe(cmd) or await ask_confirm(cmd):
                        await send({"type": "state", "value": "thinking"})
                        result = await asyncio.to_thread(run_shell, cmd)
                    else:
                        result = "The user declined to run this command."
                    messages.append(
                        {"role": "tool", "tool_call_id": call.id, "content": result}
                    )
            await send({"type": "say", "text": "Sorry, that took too many steps."})
        except Exception as e:  # noqa: BLE001
            await send({"type": "say", "text": f"Something went wrong: {e}"})
        finally:
            state["busy"] = False
            await send({"type": "state", "value": "idle"})

    try:
        await send({"type": "state", "value": "idle"})
        while True:
            data = json.loads(await ws.receive_text())
            if data.get("type") == "text" and not state["busy"]:
                text = (data.get("text") or "").strip()
                if text:
                    asyncio.create_task(handle(text))
            elif data.get("type") == "confirm" and state["confirm"] is not None:
                if not state["confirm"].done():
                    state["confirm"].set_result(bool(data.get("ok")))
    except WebSocketDisconnect:
        pass
