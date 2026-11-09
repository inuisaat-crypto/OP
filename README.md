# Pybricks route editor

Tkinter route editor and Bluetooth controller for a Pybricks hub.

## Run

On Windows, double-click `launch_controller.bat`. It reuses the existing
`HZ\.venv` when available. Otherwise, it creates a project-local `.venv` and
installs the pinned BLE dependency on first run. Python 3.10 or newer and
internet access are required only when the dependency needs to be installed.
After clicking **Run**, the status shows when the program is being compiled,
sent over Bluetooth, and started on the hub. If the editor is closed during a
run, it asks before requesting a safe stop and waits for the hub instead of
forcibly terminating the Bluetooth client.

If the hub does not respond during upload or start, the editor now shows which
stage timed out and attempts to stop the program. Reconnect the hub and check
that it is running compatible Pybricks firmware before retrying.

To start manually after setup:

```powershell
.\.venv\Scripts\python.exe .\controller.py
```

## Modules

- `controller.py` starts the application.
- `route_editor.py` contains the Tkinter interface and file operations.
- `route_model.py` validates routes and generates Pybricks programs.
- `ble_client.py` runs Bluetooth communication in a separate process so motor
  operations do not block the Tkinter event loop.

Routes are stored in `route.json` format version 2. Version 1 routes remain
readable. Select any route point on the map and edit its next movement and
point action in the properties panel. Segments support forward, backward, or
curved travel and an optional speed; points support stationary turns, stops,
and text markers. The physical grid step is configurable from 5 to 500 mm. The
route generator uses a 60 mm wheel diameter, 148 mm axle track, and motors on
ports E and A.

The **Manual control · recordings** window loads the motor program from
`HZ/1.py`, lets you drive the A/E pair and an attachment motor, and displays
the commanded speed for ports A–F. Recordings in `HZ` are listed with a motor
timeline; select one to preview or replay it. New recordings use the same JSON
format as the `HZ` keyboard controller and can be saved in that folder.

Grid dimensions are limited to 2–100 cells and change only after clicking
**Apply**. Larger grids keep cells at a usable size and can be scrolled. Segment
and marker settings are stored separately from point coordinates so edits and
route resizing can keep each movement command attached to its intended point.
