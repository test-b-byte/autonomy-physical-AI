"""
GHOST field operator link.

Bridges a LoRa radio (Meshtastic) to the GHOST Bayesian SAR engine.
Operators carry a Meshtastic node and send plain-text commands; this
process decodes them, queries GHOST, and relays results back.

Outbound (to field operator):
  - CONTACT alert when GHOST declares a find
  - Periodic status heartbeat (entropy / peak-P / sweep count)
  - Direct replies to operator queries

Inbound (from field operator):
  - status   / stat / check    → query and reply
  - halt     / stop / freeze   → HALT: robot stops (no goals while halted)
  - go / start / resume        → GO: start the search, or continue after a halt
  - home     / rtb / return    → drive back to the launch point
  - reset    / clear           → new search on the same grid (then send go)

Usage:
  python3 pi/operator_link.py                 # real LoRa radio (auto-detect)
  python3 pi/operator_link.py --mock          # console mock — type commands here
  python3 pi/operator_link.py --host 192.168.1.42 --mock
  GHOST_LORA_MOCK=1 python3 pi/operator_link.py

Requirements:
  pip install websockets meshtastic pypubsub
"""

import argparse
import asyncio
import json
import logging
import os
import queue
import re
import threading
import time

import websockets

log = logging.getLogger("ghost.operator")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)

GHOST_WS         = "ws://localhost:9001/ws"
MAX_LORA_BYTES   = 180      # leave headroom below Meshtastic's 230-byte limit
MIN_TX_INTERVAL  = 3.5      # seconds between consecutive radio transmissions
STATUS_PERIOD    = 45.0     # seconds between unsolicited status beats
CONTACT_COOLDOWN = 8.0      # don't re-broadcast CONTACT within this window
STATE_POLL       = 2.0      # seconds between background GHOST queries


# ── keyword command decoder ───────────────────────────────────────────────────

class CommandDecoder:
    """
    Maps incoming operator text to a canonical command via keyword matching.
    No ML dependency — deterministic, offline, instant.

    Returns (command_name, {}) where command_name is None if unrecognised.
    The empty params dict is reserved for future coordinate / zone extraction.
    """

    _RULES: list[tuple[list[str], str]] = [
        (["halt", "stop", "freeze", "pause"],            "halt"),
        (["resume", "go", "continue", "move", "start"],  "resume"),
        (["status", "stat", "check", "report", "ping"],  "status"),
        (["home", "return", "rtb", "base", "back"],      "return_home"),
        (["reset", "restart", "clear", "new"],           "reset"),
        (["help", "commands", "?"],                      "help"),
    ]

    def decode(self, text: str) -> tuple[str | None, dict]:
        words = set(re.sub(r"[^a-z ]", "", text.lower()).split())
        for triggers, cmd in self._RULES:
            if words & set(triggers):
                return cmd, {}
        return None, {}

    @staticmethod
    def help_text() -> str:
        return "cmds: go halt status home reset help"


# ── LoRa radio transport ──────────────────────────────────────────────────────

class RadioLink:
    """
    Meshtastic LoRa wrapper with rate limiting and automatic reconnection.
    Falls back to a console mock when hardware is absent or --mock is set.

    Thread-safe: recv() is non-blocking and can be polled from any thread.
    """

    def __init__(self, mock: bool = False, dev: str | None = None,
                 allowed: set[str] | None = None) -> None:
        self._inbox     = queue.Queue()
        self._allowed   = allowed or set()
        self._mock      = mock or os.environ.get("GHOST_LORA_MOCK") == "1"
        self._iface     = None
        self._last_tx   = 0.0
        self._tx_lock   = threading.Lock()
        self._reconnecting = False

        if self._mock:
            log.info("[radio] mock mode — type commands in this console")
            self._start_console()
        else:
            self._connect(dev)

    # ── connection ────────────────────────────────────────────────────────────

    def _connect(self, dev: str | None) -> None:
        try:
            import meshtastic.serial_interface
            from pubsub import pub
            # pypubsub keeps weak references to listeners; bound methods of a
            # live object are fine, but keep the object referenced (self).
            pub.subscribe(self._on_rx,   "meshtastic.receive.text")
            pub.subscribe(self._on_lost, "meshtastic.connection.lost")
            self._iface = meshtastic.serial_interface.SerialInterface(devPath=dev)
            log.info("[radio] LoRa radio connected")
        except Exception as exc:
            log.warning(f"[radio] hardware init failed ({exc}) — using mock")
            self._mock = True
            self._start_console()

    def _reconnect(self) -> None:
        log.warning("[radio] link lost — reconnecting")
        while True:
            try:
                try:
                    self._iface.close()
                except Exception:
                    pass
                time.sleep(5.0)
                import meshtastic.serial_interface
                self._iface = meshtastic.serial_interface.SerialInterface()
                log.info("[radio] reconnected")
                break
            except Exception as exc:
                log.warning(f"[radio] reconnect attempt failed: {exc}")
        self._reconnecting = False

    def _on_lost(self, interface) -> None:  # noqa: ARG002
        if not self._reconnecting:
            self._reconnecting = True
            threading.Thread(target=self._reconnect, daemon=True).start()

    # ── receive ───────────────────────────────────────────────────────────────

    def _on_rx(self, packet, interface) -> None:  # noqa: ARG002
        try:
            text   = packet["decoded"]["text"]
            sender = packet.get("fromId", "?")
            if self._allowed and sender not in self._allowed:
                log.warning(f"[radio] ignored command from unlisted node {sender}")
                return
            self._inbox.put((sender, text))
        except KeyError:
            pass

    def _start_console(self) -> None:
        def _loop() -> None:
            while True:
                try:
                    line = input()
                except EOFError:
                    return
                if line.strip():
                    self._inbox.put(("!console", line.strip()))
        threading.Thread(target=_loop, daemon=True).start()

    def recv(self) -> tuple[str, str] | None:
        """Non-blocking.  Returns (sender_id, text) or None."""
        try:
            return self._inbox.get_nowait()
        except queue.Empty:
            return None

    # ── send ──────────────────────────────────────────────────────────────────

    def send(self, text: str, dest: str | None = None) -> bool:
        """
        Transmit up to MAX_LORA_BYTES of text, rate-limited to MIN_TX_INTERVAL.
        Returns True on success.
        """
        data = text.encode()[:MAX_LORA_BYTES].decode(errors="ignore")
        with self._tx_lock:
            gap = MIN_TX_INTERVAL - (time.monotonic() - self._last_tx)
            if gap > 0:
                time.sleep(gap)
            if self._mock:
                log.info(f"[radio:tx] → {dest or 'broadcast'}: {data!r}")
                self._last_tx = time.monotonic()
                return True
            try:
                if dest:
                    self._iface.sendText(data, destinationId=dest, wantAck=True)
                else:
                    self._iface.sendText(data)
                self._last_tx = time.monotonic()
                return True
            except Exception as exc:
                log.warning(f"[radio] send failed: {exc}")
                return False

    def close(self) -> None:
        if self._iface:
            try:
                self._iface.close()
            except Exception:
                pass


# ── GHOST query helpers ───────────────────────────────────────────────────────

async def _query(ws) -> dict:
    await ws.send(json.dumps({"type": "query"}))
    return json.loads(await ws.recv())


async def _command(ws, action: str) -> dict:
    await ws.send(json.dumps({"type": "command", "action": action}))
    return json.loads(await ws.recv())


def _fmt_status(state: dict) -> str:
    c = state.get("contact")
    if c:
        return (
            f"CONTACT ({c['world_x']:.1f},{c['world_y']:.1f})m "
            f"P={c['probability']:.2f} "
            f"{','.join(c['sensors'])}"
        )
    return (
        f"{state.get('mission', '?').upper()} "
        f"P={state.get('max_probability', 0):.3f} "
        f"S={state.get('sweep_count', 0)} "
        f"H={state.get('entropy', 0):.2f} "
        f"E={state.get('elevation', 0):.1f}m"
    )


def _fmt_contact(c: dict) -> str:
    return (
        f"GHOST CONTACT "
        f"({c['world_x']:.1f},{c['world_y']:.1f})m "
        f"P={c['probability']:.2f} "
        f"{','.join(c['sensors'])}"
    )


# ── operator link ─────────────────────────────────────────────────────────────

class OperatorLink:
    def __init__(self, ws_url: str, mock: bool, dev: str | None,
                 allowed: set[str] | None = None) -> None:
        self._ws_url   = ws_url
        self._radio    = RadioLink(mock=mock, dev=dev, allowed=allowed)
        self._decoder  = CommandDecoder()
        self._last_contact_tx = 0.0

    async def run(self) -> None:
        while True:
            try:
                async with websockets.connect(self._ws_url, max_size=None) as ws:
                    await ws.recv()   # the core pushes a snapshot on connect — drain it,
                                      # or every reply after this is one message stale
                    log.info(f"connected to GHOST at {self._ws_url}")
                    await self._loop(ws)
            except (websockets.ConnectionClosed, OSError) as exc:
                log.warning(f"GHOST WS lost ({exc}), retrying in 3 s…")
                await asyncio.sleep(3.0)

    async def _loop(self, ws) -> None:
        t_status  = time.monotonic() - STATUS_PERIOD   # broadcast immediately
        t_contact = time.monotonic() - STATE_POLL

        while True:
            await asyncio.sleep(0.1)
            now = time.monotonic()

            # ── incoming operator message ─────────────────────────────────────
            msg = self._radio.recv()
            if msg:
                sender, text = msg
                log.info(f"[radio:rx] {sender}: {text!r}")
                reply = await self._handle(ws, text)
                if reply:
                    self._radio.send(reply, dest=sender)

            # ── background state check ────────────────────────────────────────
            if now - t_contact >= STATE_POLL:
                state = await _query(ws)
                t_contact = now

                contact = state.get("contact")
                if contact and now - self._last_contact_tx > CONTACT_COOLDOWN:
                    self._radio.send(_fmt_contact(contact))
                    self._last_contact_tx = now
                    log.warning("[radio:tx] CONTACT alert broadcast")

                if now - t_status >= STATUS_PERIOD:
                    self._radio.send(_fmt_status(state))
                    t_status = now

    async def _handle(self, ws, text: str) -> str | None:
        cmd, _ = self._decoder.decode(text)
        if cmd is None:
            return "GHOST: unclear — try: go halt status home reset"

        if cmd == "status":
            state = await _query(ws)
            return _fmt_status(state)

        if cmd == "reset":                    # new search, same grid; waits for GO
            state = await _command(ws, "abort")
            return f"GHOST: new search ready ({state.get('mission')}) — send go"

        if cmd == "halt":                     # robot stops: no goals while halted
            state = await _command(ws, "halt")
            return f"GHOST: {state.get('mission', '?').upper()}"

        if cmd == "resume":                   # GO: start from idle, or continue after halt
            state = await _query(ws)
            action = "start" if state.get("mission") == "idle" else "resume"
            state = await _command(ws, action)
            return f"GHOST: {state.get('mission', '?').upper()}"

        if cmd == "return_home":
            state = await _command(ws, "return_home")
            return f"GHOST: {state.get('mission', '?').upper()}"

        if cmd == "help":
            return CommandDecoder.help_text()

        return f"GHOST: {cmd} OK"

    def close(self) -> None:
        self._radio.close()


# ── entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="GHOST field operator link")
    ap.add_argument("--host",  default="localhost",
                    help="Hostname of the machine running ghost-core")
    ap.add_argument("--port",  type=int, default=9001)
    ap.add_argument("--mock",  action="store_true",
                    help="Mock LoRa radio — read commands from stdin")
    ap.add_argument("--dev",   default=None,
                    help="LoRa serial device (e.g. /dev/ttyUSB0); auto-detect if omitted")
    ap.add_argument("--allow", default="",
                    help="comma-separated Meshtastic node ids allowed to command the drone "
                         "(e.g. '!a1b2c3d4'); empty = anyone on the channel (bench only)")
    args = ap.parse_args()

    allowed = {a.strip() for a in args.allow.split(",") if a.strip()}
    if not allowed and not args.mock:
        log.warning("no --allow list: ANY node on the channel can halt/resume the drone")
    ws_url = f"ws://{args.host}:{args.port}/ws"
    link   = OperatorLink(ws_url=ws_url, mock=args.mock, dev=args.dev, allowed=allowed)
    try:
        asyncio.run(link.run())
    except KeyboardInterrupt:
        log.info("shutdown")
    finally:
        link.close()


if __name__ == "__main__":
    main()
