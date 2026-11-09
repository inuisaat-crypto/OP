import os
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

import route_editor
from ble_client import BLE_CLIENT_SCRIPT, compile_route_program
from route_editor import RouteEditor


class FakeProcess:
    def __init__(self):
        self.return_code = None
        self.wait_timeout = None

    def poll(self):
        return self.return_code

    def wait(self, timeout):
        self.wait_timeout = timeout
        self.return_code = 0
        return self.return_code


class FakeRoot:
    def __init__(self):
        self.destroyed = False

    def after(self, _delay, callback):
        callback()

    def destroy(self):
        self.destroyed = True


class BleShutdownTests(unittest.TestCase):
    def test_embedded_ble_client_script_is_valid_python(self):
        compile(BLE_CLIENT_SCRIPT, "ble_client_subprocess.py", "exec")

    def test_compiler_does_not_inherit_open_ble_command_stdin(self):
        self.assertTrue(callable(compile_route_program))
        source = (
            "from pybricks.hubs import PrimeHub\n"
            "from pybricks.parameters import Port\n"
            "from pybricks.pupdevices import Motor\n"
            "hub = PrimeHub()\n"
            "motor = Motor(Port.A)\n"
        )
        child_script = (
            "import asyncio, sys\n"
            "from ble_client import compile_route_program\n"
            "async def main():\n"
            "    result = await compile_route_program(sys.argv[1], 6, 20)\n"
            "    print(len(result), flush=True)\n"
            "asyncio.run(main())\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            program_path = os.path.join(directory, "route.py")
            with open(program_path, "w", encoding="utf-8") as program_file:
                program_file.write(source)
            process = subprocess.Popen(
                [sys.executable, "-u", "-c", child_script, program_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                cwd=os.path.dirname(os.path.dirname(__file__)),
            )
            output = []
            reader = threading.Thread(
                target=lambda: output.append(process.stdout.readline()),
                daemon=True,
            )
            try:
                process.stdin.write("keep BLE command pipe open\n")
                process.stdin.flush()
                reader.start()
                reader.join(timeout=20)
                self.assertFalse(
                    reader.is_alive(),
                    "Compilation hung while BLE command stdin remained open.",
                )
                self.assertRegex(output[0], r"^\d+\s*$")
                self.assertEqual(process.wait(timeout=5), 0)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
                for pipe in (process.stdin, process.stdout, process.stderr):
                    if pipe is not None:
                        pipe.close()

    def create_editor(self, running=False):
        editor = RouteEditor.__new__(RouteEditor)
        editor.root = FakeRoot()
        editor.ble_process = FakeProcess()
        editor.ble_running = running
        editor.ble_program_started = False
        editor.ble_closing = False
        editor.ble_run_timeout_id = None
        editor._set_ble_status = Mock()
        editor._refresh_ble_controls = Mock()
        editor._send_ble_command = Mock()
        editor._ble_send_async = Mock()
        return editor

    def test_close_waits_for_graceful_ble_shutdown(self):
        editor = self.create_editor()

        class InlineThread:
            def __init__(self, target, daemon):
                self.target = target

            def start(self):
                self.target()

        with (
            patch.object(route_editor.threading, "Thread", InlineThread),
            patch.object(route_editor.messagebox, "askyesno", return_value=True),
        ):
            editor._on_close()

        editor._send_ble_command.assert_called_once_with(
            {"command": "shutdown"}, editor.ble_process
        )
        self.assertEqual(
            editor.ble_process.wait_timeout,
            route_editor.PROGRAM_DOWNLOAD_TIMEOUT_SECONDS + 20,
        )
        self.assertTrue(editor.root.destroyed)

    def test_close_during_run_requires_confirmation(self):
        editor = self.create_editor(running=True)

        with patch.object(route_editor.messagebox, "askyesno", return_value=False):
            editor._on_close()

        editor._send_ble_command.assert_not_called()
        self.assertFalse(editor.root.destroyed)

    def test_close_timeout_keeps_window_open_and_ble_client_alive(self):
        editor = self.create_editor()
        timeout = subprocess.TimeoutExpired("ble-client", 10)

        class InlineThread:
            def __init__(self, target, daemon):
                self.target = target

            def start(self):
                self.target()

        with (
            patch.object(route_editor.threading, "Thread", InlineThread),
            patch.object(route_editor.messagebox, "showerror"),
            patch.object(
                editor.ble_process, "wait", side_effect=timeout
            ),
        ):
            editor._on_close()

        self.assertFalse(editor.root.destroyed)
        self.assertFalse(editor.ble_closing)

    def test_run_timeout_requests_stop_without_killing_ble_client(self):
        editor = self.create_editor(running=True)

        with patch.object(route_editor.messagebox, "showwarning"):
            editor._on_ble_run_timeout()

        self.assertTrue(editor.ble_running)
        editor._ble_send_async.assert_called_once_with(
            {"command": "stop"}, "stop"
        )


if __name__ == "__main__":
    unittest.main()
