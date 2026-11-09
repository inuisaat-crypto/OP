"""Изолированный BLE-клиент для связи редактора с Pybricks-хабом."""

import asyncio
import subprocess
import sys

PROGRAM_DOWNLOAD_TIMEOUT_SECONDS = 60
PROGRAM_RUN_TIMEOUT_SECONDS = 2 * PROGRAM_DOWNLOAD_TIMEOUT_SECONDS + 25

_COMPILER_SCRIPT = """\
import asyncio
import sys

from pybricksdev.compile import compile_multi_file

async def main():
    abi = tuple(map(int, sys.argv[2].split("."))) if "." in sys.argv[2] else int(sys.argv[2])
    program = await compile_multi_file(sys.argv[1], abi)
    sys.stdout.buffer.write(program)

asyncio.run(main())
"""


async def compile_route_program(path, abi, timeout):
    """Компилирует маршрут в отдельном процессе без BLE-канала на stdin."""
    abi_text = ".".join(map(str, abi)) if isinstance(abi, tuple) else str(abi)
    compiler = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        _COMPILER_SCRIPT,
        path,
        abi_text,
        stdin=subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            compiler.communicate(), timeout=timeout
        )
    except (asyncio.TimeoutError, asyncio.CancelledError):
        if compiler.returncode is None:
            compiler.kill()
        await compiler.communicate()
        raise

    if compiler.returncode:
        details = stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            details or "Локальный компилятор Pybricks завершился с ошибкой."
        )
    return stdout


BLE_CLIENT_SCRIPT = r'''
import asyncio
import json
import os
import sys
import tempfile

from pybricksdev.ble import find_device
from pybricksdev.connections.pybricks import (
    HubCapabilityFlag,
    PybricksHubBLE,
    StatusFlag,
)
from ble_client import compile_route_program

PROGRAM_DOWNLOAD_TIMEOUT_SECONDS = 60


def send(event, **values):
    print(json.dumps({"event": event, **values}), flush=True)


async def main():
    hub = None
    connection_subscription = None
    active_run = None
    program_started = False
    stop_requested = False
    stop_sent = False

    async def run_program(source, task_name):
        nonlocal program_started, stop_requested, stop_sent
        path = None
        state_subscription = None
        phase = "Компиляция программы на компьютере"
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", suffix=".py", delete=False
            ) as program_file:
                program_file.write(source)
                path = program_file.name
            send(
                "task_progress",
                name=task_name,
                phase="Компилирую программу на компьютере...",
            )
            program_states = asyncio.Queue()
            state_subscription = hub.status_observable.subscribe(
                lambda status: program_states.put_nowait(
                    bool(status & StatusFlag.USER_PROGRAM_RUNNING)
                )
            )
            try:
                # Старые версии прошивки поддерживаются через совместимый run().
                if getattr(hub, "_mpy_abi_version", 0):
                    phase = "Компиляция и загрузка на хаб"
                    await asyncio.wait_for(
                        hub.run(
                            path,
                            wait=False,
                            print_output=False,
                            line_handler=False,
                        ),
                        timeout=PROGRAM_DOWNLOAD_TIMEOUT_SECONDS,
                    )
                else:
                    abi = (
                        (6, 1)
                        if hub._capability_flags
                        & HubCapabilityFlag.USER_PROG_MULTI_FILE_MPY6_1_NATIVE
                        else 6
                    )
                    program = await compile_route_program(
                        path, abi, PROGRAM_DOWNLOAD_TIMEOUT_SECONDS
                    )
                    phase = "Загрузка программы на хаб по Bluetooth"
                    send(
                        "task_progress",
                        name=task_name,
                        phase="Загружаю программу на хаб по Bluetooth...",
                    )
                    await asyncio.wait_for(
                        hub.download_user_program(program),
                        timeout=PROGRAM_DOWNLOAD_TIMEOUT_SECONDS,
                    )
                    phase = "Запуск программы на хабе"
                    send(
                        "task_progress",
                        name=task_name,
                        phase="Программа загружена; запускаю на хабе...",
                    )
                    await asyncio.wait_for(
                        hub.start_user_program(), timeout=10
                    )
            except asyncio.TimeoutError:
                stop_message = "Команда остановки отправлена."
                try:
                    await asyncio.wait_for(hub.stop_user_program(), timeout=5)
                except Exception as stop_error:
                    stop_message = "Не удалось подтвердить остановку: {}".format(
                        stop_error
                    )
                raise RuntimeError(
                    "Хаб не ответил на этапе «{}» за отведённое время. {} "
                    "Проверь Bluetooth-соединение и прошивку Pybricks на хабе."
                    .format(phase, stop_message)
                )
            program_started = True
            send("program_started", name=task_name)
            if stop_requested and not stop_sent and hub is not None:
                stop_sent = True
                await hub.stop_user_program()
            saw_running = False
            while True:
                try:
                    is_running = await asyncio.wait_for(
                        program_states.get(), timeout=30 if not saw_running else None
                    )
                except asyncio.TimeoutError:
                    raise RuntimeError(
                        "Хаб принял программу, но не сообщил о её запуске."
                    )
                if is_running:
                    saw_running = True
                elif saw_running:
                    break
            send("task_finished", name=task_name, stopped=stop_requested)
        except Exception as error:
            send(
                "task_finished",
                name=task_name,
                stopped=stop_requested,
                error=str(error),
            )
        finally:
            program_started = False
            if state_subscription is not None:
                state_subscription.dispose()
            stop_requested = False
            stop_sent = False
            if path and os.path.exists(path):
                os.remove(path)

    async def stop_active_program():
        nonlocal stop_requested, stop_sent
        if active_run is None or active_run.done():
            return
        stop_requested = True
        if program_started and not stop_sent and hub is not None:
            stop_sent = True
            await hub.stop_user_program()
        timeout = 5 if program_started else PROGRAM_DOWNLOAD_TIMEOUT_SECONDS + 10
        try:
            await asyncio.wait_for(asyncio.shield(active_run), timeout=timeout)
        except asyncio.TimeoutError:
            raise RuntimeError("Не удалось остановить программу Pybricks вовремя.")

    async def send_user_program_command(user_command):
        if hub is None or active_run is None or active_run.done() or not program_started:
            raise RuntimeError("Ручная программа не запущена на хабе.")
        await hub.write_line(user_command)
        response = await asyncio.wait_for(hub.read_line(), timeout=10)
        if response == user_command:
            response = await asyncio.wait_for(hub.read_line(), timeout=10)
        if response != "OK":
            raise RuntimeError(response.removeprefix("ERROR,"))

    while True:
        line = await asyncio.to_thread(sys.stdin.readline)
        if not line:
            break
        try:
            message = json.loads(line)
            command = message.get("command")
            if command == "connect":
                if hub is not None:
                    send("error", operation="connect", message="Хаб уже подключён.")
                    continue
                device = await find_device(
                    name=message.get("name") or None, timeout=30
                )
                candidate = PybricksHubBLE(device)
                try:
                    await candidate.connect()
                except Exception as connect_error:
                    try:
                        await candidate.disconnect()
                    except Exception as cleanup_error:
                        raise RuntimeError(
                            "{}; очистка соединения также завершилась ошибкой: {}"
                            .format(connect_error, cleanup_error)
                        ) from connect_error
                    raise
                hub = candidate

                def handle_connection_state(state, connected_hub=candidate):
                    nonlocal hub, connection_subscription
                    if state.name == "DISCONNECTED" and hub is connected_hub:
                        hub = None
                        if connection_subscription is not None:
                            connection_subscription.dispose()
                        connection_subscription = None
                        send("link_lost")

                connection_subscription = (
                    candidate.connection_state_observable.subscribe(
                        handle_connection_state
                    )
                )
                device_name = device.name or device.address
                send("connected", name=device_name, address=device.address)
            elif command == "run":
                if hub is None:
                    send("error", operation="run", message="Сначала подключи хаб.")
                elif active_run is not None and not active_run.done():
                    send("error", operation="run", message="Робот уже выполняет команду.")
                else:
                    stop_requested = False
                    stop_sent = False
                    active_run = asyncio.create_task(
                        run_program(message["source"], message["name"])
                    )
                    send("task_started", name=message["name"])
            elif command == "manual_setup":
                if hub is None or active_run is None or active_run.done():
                    raise RuntimeError("Сначала запусти программу ручного управления.")
                ready = await asyncio.wait_for(hub.read_line(), timeout=10)
                if ready != "READY":
                    raise RuntimeError("Ручная программа не готова: {}".format(ready))
                await send_user_program_command("ports,A,E")
                send("manual_ready", left_port="A", right_port="E")
            elif command == "manual":
                user_command = message.get("value")
                if not isinstance(user_command, str):
                    raise ValueError("Пустая команда ручного управления.")
                await send_user_program_command(user_command)
                send("manual_ack", value=user_command)
            elif command == "manual_batch":
                commands = message.get("values")
                if not isinstance(commands, list) or not commands or any(not isinstance(value, str) for value in commands):
                    raise ValueError("Неверный список команд ручного управления.")
                for user_command in commands:
                    await send_user_program_command(user_command)
                send("manual_ack", value=commands[-1])
            elif command == "stop":
                if hub is not None and active_run is not None and not active_run.done():
                    stop_requested = True
                    if program_started and not stop_sent:
                        stop_sent = True
                        await hub.stop_user_program()
                send("stop_requested")
            elif command == "disconnect":
                if hub is not None:
                    await stop_active_program()
                    await hub.disconnect()
                    hub = None
                if connection_subscription is not None:
                    connection_subscription.dispose()
                    connection_subscription = None
                active_run = None
                send("disconnected")
            elif command == "shutdown":
                if hub is not None:
                    await stop_active_program()
                    await hub.disconnect()
                if connection_subscription is not None:
                    connection_subscription.dispose()
                send("shutdown")
                return
        except Exception as error:
            error_message = str(error).strip()
            if isinstance(error, asyncio.TimeoutError):
                requested_name = message.get("name", "").strip()
                target = (
                    "хаб «{}»".format(requested_name)
                    if requested_name
                    else "Pybricks-хаб"
                )
                error_message = (
                    "За 30 секунд не найден {}. Включи хаб и проверь, что "
                    "Bluetooth включён. "
                    "Если указано имя/адрес, очисти поле и попробуй снова."
                ).format(target)
            elif not error_message:
                error_message = "Нет дополнительной информации от Bluetooth."
            send(
                "error",
                operation=message.get("command", "unknown"),
                message="{}: {}".format(type(error).__name__, error_message),
            )


asyncio.run(main())
'''
