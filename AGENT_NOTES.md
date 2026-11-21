# OP — brief for agents

Handoff note: read this instead of re-reading the whole project history.
UI language and docs are Russian; keep it that way.

## What this is

FLL / Pybricks robot project: motion library for the hub, JSON mission format,
generator that packs missions into a Pybricks archive, and a browser block
editor with a field preview.

## Layout

- `pybricks_runtime/` — code that runs on the hub: `core.py` (LQR moves, attachments),
  `config.py`, `main.py`, `menu.py`, `mission_recording.py`.
- `missions/` — `mission_1..4.json` + built `OP_pybricks_project.zip` (JSON never goes into the ZIP).
- `mission_format.py` — the single source of truth for the JSON schema (`STEP_TYPES`).
- `build_archive.py` — JSON → `.py` renderer + ZIP builder.
- `mission_tester.py` — Bluetooth runner, `--offline` dry-run, pose preview math.
- `mission_editor/` — `server.py` (REST API), `index.html`, `src/main.js`, `src/styles.css`, `src/assets/fll-field-map.png`.
- `tests/` — unit tests (`test_mission_format`, `test_build_archive`, `test_mission_tester`,
  `test_json_guide`, `test_mission_catalog`, `test_menu`, `test_system_check`).
- `JSON_GUIDE.md` — every step type documented; the last fenced `json` example must stay valid.
- `README.md` — hub menu, archive, tester, editor.

## Commands (Windows PowerShell)

```powershell
# tests (43 total, run from repo root)
.\.venv-mission-tester\Scripts\python.exe -m unittest discover -s tests

# archive: missions/*.json -> missions/OP_pybricks_project.zip
python build_archive.py

# offline mission dry-run (no hub)
python mission_tester.py --offline

# editor: api on 8765 + vite on 5173
cd mission_editor; npm run dev
# production build check
cd mission_editor; npx vite build
```

## Mission JSON

21 step types: `straight`, `turn`, `turn_to`, `wheel_turn`, `arc`, `wall_square`,
`attachment`, `att_until_stalled`, `set_att_accel`, `wait`, `beep`, `log`,
`battery_check`, `set_speed`, `set_heading`, `rush`, `reset_start`, `stop`,
`if`, `repeat`, `parallel`.

Rules that bite:

- Every step type must be (a) in `STEP_TYPES`, (b) rendered in `build_archive.py`,
  (c) described in `JSON_GUIDE.md` — `tests/test_json_guide.py` enforces the docs.
- Movements accept `"through": true` → rendered as `then=Stop.NONE`; the validator
  requires the next step in the same sequence to be a movement too.
- Generated modules import only the core names they call (`CORE_EXPORTS` scan), and
  `rush()` appears only when the JSON has an explicit `rush` step.
- `beep` steps call `core.beep()`, which is silent when `DEBUG_BEEP = False`.
- `parallel` lanes: `drive` takes movement + `wait` only; `E`/`F` take exactly one
  matching `attachment`.
- Core API used by the generator (`pybricks_runtime/core.py`): `straight`, `turn`,
  `turn_to`, `wheel_turn(angle, locked="right"|"left")`, `arc`, `wall_square`,
  `att_run`, `att_run_until_stalled`, `att_wait`, `set_att_accel`, `set_speed`,
  `set_heading`, `rush`, `stop_drive`, `stop_all`, `release_drive`,
  `reset_start`, `battery_check`, `log`.

## Editor internals

- Blocks ↔ steps: `blockToStep` and `createStepBlock` in `mission_editor/src/main.js`.
  A new block needs both plus a toolbox entry.
- Toolbox groups: Движение / Навески / Действия / Робот / Логика.
  Colours: `#1d9bf0`, `#00ba7c`, `#c9a227`, `#f91880`, `#536471`.
- Collapsed toolbox → 24 px rail with 3×22 px category ticks, labels hidden.
- Canvas: dot grid via `grid: { spacing: 26, length: 0 }`; Blockly draws the dot as a
  zero-length line and omits `stroke`, so the colour comes from CSS
  (`#blockly [id^="blocklyGridPattern"] line`). Drag panning only works with
  `move.scrollbars: true` — v12 forces `move.drag = false` when scrollbars are off;
  the scrollbars themselves are hidden with `opacity: 0`.
- Preview: `poseAfter` (plan path) and `buildTimeline` (player, trapezoid accel/decel);
  `wheel_turn` moves the body centre around the locked wheel (`AXLE_TRACK = 165 mm`).
- Persistence: `localStorage` keys `op.settings` and panel collapse state.
- Player bar is an overlay on `.field-wrap`: hidden by default, revealed by
  `.field-wrap:hover`, keyboard focus (`:has(:focus-visible)`) or `.is-playing`;
  `loadTimeline` adds `.no-timeline` when `timeline.duration <= 0` (mission without
  movements), which hides the bar completely.
- REST: `GET /api/missions`, `POST /api/save` (`filename`, `mission`, optional
  `previous` for rename), `POST /api/build`.

## Style

- Black canvas, surfaces `#16181c`, hairlines `#2f3336`, one accent `#1d9bf0`,
  pill buttons, no gradients, no emoji.
- Russian UI labels and docs; numbers with units, e.g. `мм/с`, `°/с`.

## Known details

- `mission_3.json` starts at `x_mm: 100`, so the editor correctly warns that the
  robot is partly off the field — that is the data, not a bug.
- `build_archive.py` uses `ast.Constant` (not `ast.Str`) — required on Python 3.14.
- `missions/` is still untracked in git; `git add missions` when ready.
- `.gitignore`, `__pycache__` noise: ignore when checking `git status`.

## Before finishing a change

1. `python -m unittest discover -s tests` → all green.
2. `npx vite build` in `mission_editor` → success.
3. If missions/JSON changed: rebuild the archive and confirm the ZIP contains only `.py`.
