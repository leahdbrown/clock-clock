from contextlib import asynccontextmanager
import asyncio
import threading
import time

import serial
import serial.tools.list_ports
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path

HERE = Path(__file__).parent

_state: dict = {"conn": None, "port": None}
_state_lock = threading.Lock()
_clients: set[WebSocket] = set()
_main_loop: asyncio.AbstractEventLoop | None = None


def _detect_pico() -> str | None:
    for p in serial.tools.list_ports.comports():
        if "usbmodem" in p.device or "usbserial" in p.device:
            return p.device
    return None


def _list_ports() -> list[dict]:
    return [
        {
            "device": p.device,
            "description": p.description,
            "suggested": "usbmodem" in p.device or "usbserial" in p.device,
        }
        for p in serial.tools.list_ports.comports()
    ]


async def _broadcast(msg: str) -> None:
    dead: set[WebSocket] = set()
    for ws in list(_clients):
        try:
            await ws.send_text(msg)
        except Exception:
            dead.add(ws)
    _clients.difference_update(dead)


def _reader() -> None:
    while True:
        with _state_lock:
            conn = _state["conn"]
        if conn and conn.is_open:
            try:
                line = conn.readline()
                if line:
                    text = line.decode("utf-8", errors="replace").rstrip("\r\n")
                    if text and _main_loop:
                        asyncio.run_coroutine_threadsafe(_broadcast(text), _main_loop)
            except serial.SerialException as e:
                with _state_lock:
                    _state["conn"] = None
                    _state["port"] = None
                if _main_loop:
                    asyncio.run_coroutine_threadsafe(
                        _broadcast(f"[serial error: {e}]"), _main_loop
                    )
        else:
            time.sleep(0.05)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _main_loop
    _main_loop = asyncio.get_running_loop()
    threading.Thread(target=_reader, daemon=True).start()
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/")
def index():
    return FileResponse(HERE / "index.html")


@app.get("/ports")
def ports():
    return _list_ports()


@app.get("/status")
def status():
    with _state_lock:
        conn = _state["conn"]
        return {
            "connected": conn is not None and conn.is_open,
            "port": _state["port"],
        }


@app.post("/connect")
async def connect(body: dict):
    port = body.get("port") or _detect_pico()
    baud = int(body.get("baud", 115200))
    if not port:
        return JSONResponse({"error": "No port specified and Pico not detected"}, status_code=404)

    try:
        new_conn = serial.Serial(port, baud, timeout=0.1)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    with _state_lock:
        old_conn = _state["conn"]
        _state["conn"] = new_conn
        _state["port"] = port

    if old_conn and old_conn.is_open:
        try:
            old_conn.close()
        except Exception:
            pass

    await _broadcast(f"[connected {port} @ {baud} baud]")
    return {"connected": True, "port": port, "baud": baud}


@app.post("/disconnect")
async def disconnect():
    with _state_lock:
        conn = _state["conn"]
        _state["conn"] = None
        _state["port"] = None

    if conn:
        try:
            conn.close()
        except Exception:
            pass

    await _broadcast("[disconnected]")
    return {"connected": False}


@app.post("/send")
async def send(body: dict):
    cmd = (body.get("command") or "").strip()
    if not cmd:
        return JSONResponse({"error": "empty command"}, status_code=400)

    with _state_lock:
        conn = _state["conn"]

    if not conn or not conn.is_open:
        return JSONResponse({"error": "not connected"}, status_code=400)

    try:
        conn.write((cmd + "\n").encode())
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    _clients.add(websocket)
    with _state_lock:
        port = _state["port"]
    if port:
        await websocket.send_text(f"[session resumed — connected to {port}]")
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        _clients.discard(websocket)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
