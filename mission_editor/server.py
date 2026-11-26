import json
import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from build_archive import build_archive
from mission_format import MissionFormatError, validate_mission


MISSIONS_DIR = ROOT / "missions"
MISSION_NAME = re.compile(r"^mission_([0-9]{1,3})\.json$")
MAX_BODY = 200000


def mission_number(filename):
    match = MISSION_NAME.match(filename or "")
    if not match:
        raise ValueError("Номер миссии должен выглядеть как mission_4.json")
    return int(match.group(1))


def resolve_mission(filename):
    mission_number(filename)
    return MISSIONS_DIR / filename


def list_missions():
    MISSIONS_DIR.mkdir(parents=True, exist_ok=True)
    missions = []
    for path in MISSIONS_DIR.glob("mission_*.json"):
        try:
            with path.open("r", encoding="utf-8") as source:
                mission = validate_mission(json.load(source))
        except (OSError, UnicodeError, ValueError) as error:
            missions.append(
                {
                    "filename": path.name,
                    "number": mission_number(path.name),
                    "error": str(error),
                }
            )
            continue
        missions.append(
            {
                "filename": path.name,
                "number": mission_number(path.name),
                "mission": mission,
            }
        )
    return sorted(missions, key=lambda item: item["number"])


def store_mission(filename, raw_mission, previous=None):
    destination = resolve_mission(filename)
    mission = validate_mission(raw_mission)
    MISSIONS_DIR.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(mission, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if previous and previous != filename:
        old = resolve_mission(previous)
        if old.is_file():
            old.unlink()
    return destination


class MissionEditorHandler(BaseHTTPRequestHandler):
    def _respond(self, status, payload):
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        size = int(self.headers.get("Content-Length", "0"))
        if size < 1 or size > MAX_BODY:
            raise ValueError("Request body must be between 1 and 200000 bytes")
        return json.loads(self.rfile.read(size).decode("utf-8"))

    def do_GET(self):
        if self.path == "/api/missions":
            self._respond(200, {"missions": list_missions()})
            return
        self._respond(404, {"error": "Not found"})

    def do_POST(self):
        try:
            if self.path == "/api/save":
                request = self._read_body()
                destination = store_mission(
                    request.get("filename"),
                    request.get("mission"),
                    request.get("previous"),
                )
            elif self.path == "/api/build":
                archive = build_archive()
                self._respond(
                    200,
                    {"archive": archive.name, "missions": len(list_missions())},
                )
                return
            else:
                self._respond(404, {"error": "Not found"})
                return
        except (UnicodeError, ValueError, MissionFormatError) as error:
            self._respond(400, {"error": str(error)})
            return
        except (OSError, RuntimeError, FileNotFoundError) as error:
            self._respond(500, {"error": str(error)})
            return

        self._respond(200, {"filename": destination.name, "missions": list_missions()})

    def log_message(self, format_string, *args):
        sys.stdout.write("Mission editor: " + format_string % args + "\n")


if __name__ == "__main__":
    MISSIONS_DIR.mkdir(parents=True, exist_ok=True)
    print("Mission editor API: http://127.0.0.1:8765")
    HTTPServer(("127.0.0.1", 8765), MissionEditorHandler).serve_forever()
