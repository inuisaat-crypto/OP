import json
import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from build_archive import build_archive
from mission_format import MissionFormatError, validate_mission


MISSION_NAME = re.compile(r"^mission_[0-9]+\.json$")


class MissionEditorHandler(BaseHTTPRequestHandler):
    def _respond(self, status, payload):
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path != "/api/missions":
            self._respond(404, {"error": "Not found"})
            return

        missions = []
        for path in sorted(ROOT.glob("mission_*.json")):
            try:
                with path.open("r", encoding="utf-8") as source:
                    mission = validate_mission(json.load(source))
            except (OSError, UnicodeError, ValueError) as error:
                missions.append({"filename": path.name, "error": str(error)})
                continue
            missions.append({"filename": path.name, "mission": mission})
        self._respond(200, {"missions": missions})

    def do_POST(self):
        if self.path != "/api/save":
            self._respond(404, {"error": "Not found"})
            return

        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size < 1 or size > 200000:
                raise ValueError("Request body must be between 1 and 200000 bytes")
            request = json.loads(self.rfile.read(size).decode("utf-8"))
            filename = request.get("filename")
            if not isinstance(filename, str) or not MISSION_NAME.match(filename):
                raise ValueError("Filename must look like mission_4.json")
            mission = validate_mission(request.get("mission"))
            destination = ROOT / filename
            destination.write_text(
                json.dumps(mission, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            archive = build_archive()
        except (UnicodeError, ValueError, MissionFormatError) as error:
            self._respond(400, {"error": str(error)})
            return
        except (OSError, RuntimeError) as error:
            self._respond(500, {"error": str(error)})
            return

        self._respond(
            200,
            {
                "filename": filename,
                "archive": archive.name,
                "message": "Mission saved and Pybricks archive rebuilt.",
            },
        )

    def log_message(self, format_string, *args):
        sys.stdout.write("Mission editor: " + format_string % args + "\n")


if __name__ == "__main__":
    print("Mission editor API: http://127.0.0.1:8765")
    HTTPServer(("127.0.0.1", 8765), MissionEditorHandler).serve_forever()
