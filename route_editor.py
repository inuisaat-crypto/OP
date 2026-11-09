import glob
import json
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ble_client import (
    BLE_CLIENT_SCRIPT,
    PROGRAM_DOWNLOAD_TIMEOUT_SECONDS,
    PROGRAM_RUN_TIMEOUT_SECONDS,
)
from route_model import (
    CELL_DISTANCE_MM,
    HEADINGS,
    HEADING_DELTAS,
    generate_pybricks_program,
    generate_pybricks_test_program,
    route_end_heading_index,
    validate_route_data,
)


CELL_SIZE = 42
MIN_CELL_SIZE = 18.0
COLORS = {
    "background": "#0b1018",
    "surface": "#121a25",
    "surface_alt": "#1a2634",
    "border": "#283747",
    "text": "#e8f0f7",
    "muted": "#91a3b5",
    "accent": "#54d6b2",
    "accent_hover": "#83edce",
    "green": "#54d6b2",
    "green_hover": "#83edce",
    "route": "#f5b84b",
    "grid": "#253242",
    "cell": "#101923",
    "cell_alt": "#121d28",
    "robot": "#62a9ff",
}


class RouteEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("Pybricks — редактор маршрута")
        self.root.minsize(980, 640)
        self.root.geometry("1200x780")
        self.root.configure(background=COLORS["background"])

        self.columns = tk.IntVar(value=20)
        self.rows = tk.IntVar(value=14)
        self.grid_columns = 20
        self.grid_rows = 14
        self.cell_size = float(CELL_SIZE)
        self._resize_redraw_pending = False
        self.tool = tk.StringVar(value="select")
        self.heading = tk.StringVar(value="N")
        self.start = None
        self.route = []
        self.segments = []
        self.markers = {}
        self.cell_distance = tk.IntVar(value=CELL_DISTANCE_MM)
        self.selected_index = 0
        self.zoom = 1.0
        self.segment_mode_var = tk.StringVar(value="Вперёд")
        self.segment_speed_var = tk.StringVar(value="")
        self.segment_curve_var = tk.StringVar(value="45")
        self.marker_action_var = tk.StringVar(value="Нет")
        self.marker_text_var = tk.StringVar(value="")
        self.marker_angle_var = tk.StringVar(value="90")
        self.last_brush_cell = None
        self.ble_device = tk.StringVar()
        self.reverse_motor_directions = tk.BooleanVar(value=False)
        self.route_file_path = None
        self.route_dirty = False
        self.ble_connected = False
        self.ble_connecting = False
        self.ble_running = False
        self.ble_disconnecting = False
        self.ble_program_started = False
        self.ble_closing = False
        self.ble_process = None
        self.ble_run_timeout_id = None
        self.ble_stderr_lines = []
        self.ble_stderr_thread = None
        self.ble_write_lock = threading.Lock()
        self.ble_window = None
        self.file_menu = None
        self.ble_menu_status = None
        self.ble_buttons = {}
        self.top_connect_button = None
        self.top_run_button = None
        self.map_info = None
        self.manual_window = None
        self.manual_ready = False
        self.manual_setup_pending = False
        self.manual_start_when_connected = False
        self.manual_keys = set()
        self.manual_last_command = None
        self.manual_drive_speed = tk.IntVar(value=300)
        self.manual_turn_speed = tk.IntVar(value=250)
        self.manual_attachment_speed = tk.IntVar(value=300)
        self.manual_attachment_port = tk.StringVar(value="B")
        self.manual_last_attachment_port = "B"
        self.manual_status_var = tk.StringVar(value="Ручной режим не запущен")
        self.manual_recording = False
        self.manual_recording_started = 0.0
        self.manual_recording_events = []
        self.manual_recording_path = None
        self.manual_recordings = []
        self.manual_playback_events = []
        self.manual_playback_index = 0
        self.manual_playback_started = 0.0
        self.manual_playback_after_id = None
        self.manual_waiting_for_ack = False
        self.manual_motor_speeds = {port: 0 for port in "ABCDEF"}
        self.manual_motor_widgets = {}

        self._configure_theme()
        self._build_workspace_ui()
        self._update_status()
        self._draw_grid()
        self.root.after_idle(self._redraw_grid_after_resize)

    def _build_workspace_ui(self):
        self.root.title("Маршрут · Pybricks Studio")
        self.root.minsize(1180, 720)
        self.root.geometry("1440x900")
        self.root.configure(background=COLORS["background"])

        self.file_menu = tk.Menu(self.root, tearoff=False, background=COLORS["surface"], foreground=COLORS["text"], activebackground=COLORS["accent"], activeforeground=COLORS["background"], borderwidth=0)
        self.file_menu.add_command(label="Новая карта", command=self._new_route)
        self.file_menu.add_command(label="Открыть…", command=self._load)
        self.file_menu.add_command(label="Сохранить", command=self._save)
        self.file_menu.add_command(label="Сохранить как…", command=self._save_as)
        self.file_menu.add_separator()
        self.file_menu.add_command(label="Экспорт Pybricks…", command=self._export_pybricks)

        top = ttk.Frame(self.root, style="Topbar.TFrame", padding=(18, 12))
        top.pack(fill=tk.X)
        ttk.Label(top, text="◈", style="BrandMark.TLabel").pack(side=tk.LEFT, padx=(0, 10))
        title_block = ttk.Frame(top, style="Topbar.TFrame")
        title_block.pack(side=tk.LEFT)
        ttk.Label(title_block, text="ROUTE STUDIO", style="Brand.TLabel").pack(anchor=tk.W)
        self.project_title = ttk.Label(title_block, text="Новый маршрут", style="Project.TLabel")
        self.project_title.pack(anchor=tk.W, pady=(2, 0))
        ttk.Separator(top, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=18)
        self.file_menu_button = ttk.Button(top, text="Файл  ▾", command=self._show_file_menu, style="Toolbar.TButton")
        self.file_menu_button.pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(top, text="↶  Отменить шаг", command=self._undo, style="Toolbar.TButton").pack(side=tk.LEFT, padx=3)
        ttk.Button(top, text="Очистить", command=self._clear_route, style="Toolbar.TButton").pack(side=tk.LEFT, padx=3)
        spacer = ttk.Frame(top, style="Topbar.TFrame")
        spacer.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.top_connect_button = ttk.Button(top, text="Подключить хаб", command=self._toggle_connection, style="Toolbar.TButton")
        self.top_connect_button.pack(side=tk.RIGHT, padx=(8, 0))
        self.top_run_button = ttk.Button(top, text="▶  Запустить маршрут", command=self._run_route_over_bluetooth, style="Run.TButton")
        self.top_run_button.pack(side=tk.RIGHT)
        ttk.Button(top, text="Ручное управление · записи", command=self._open_manual_control, style="Toolbar.TButton").pack(side=tk.RIGHT, padx=(0, 8))

        body = ttk.Frame(self.root, style="Workspace.TFrame", padding=(14, 0, 14, 12))
        body.pack(fill=tk.BOTH, expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        workspace = ttk.Panedwindow(body, orient=tk.HORIZONTAL)
        workspace.grid(row=0, column=0, sticky="nsew")

        tools = ttk.Frame(workspace, style="Panel.TFrame", padding=14, width=188)
        workspace.add(tools, weight=0)
        ttk.Label(tools, text="ИНСТРУМЕНТЫ", style="Eyebrow.TLabel").pack(anchor=tk.W, pady=(0, 9))
        for label, value in (("⌖   Выбор", "select"), ("╱   Рисовать путь", "brush"), ("●   Добавить точку", "point"), ("⚑   Старт", "start"), ("⌫   Ластик", "erase")):
            ttk.Radiobutton(tools, text=label, value=value, variable=self.tool, command=self._update_status, style="Tool.TRadiobutton").pack(fill=tk.X, pady=2)

        ttk.Separator(tools).pack(fill=tk.X, pady=14)
        ttk.Label(tools, text="РУЧНОЙ ШАГ", style="Eyebrow.TLabel").pack(anchor=tk.W, pady=(0, 8))
        for label, direction in (("↑  Вперёд", "forward"), ("→  Вправо", "right"), ("↓  Назад", "back"), ("←  Влево", "left")):
            ttk.Button(tools, text=label, command=lambda d=direction: self._step_route(d), style="Toolbar.TButton").pack(fill=tk.X, pady=2)

        ttk.Separator(tools).pack(fill=tk.X, pady=14)
        ttk.Label(tools, text="КАРТА", style="Eyebrow.TLabel").pack(anchor=tk.W, pady=(0, 8))
        ttk.Label(tools, text="Размер, клетки", style="Muted.TLabel").pack(anchor=tk.W)
        dims = ttk.Frame(tools, style="Panel.TFrame")
        dims.pack(fill=tk.X, pady=(4, 8))
        for variable in (self.columns, self.rows):
            ttk.Spinbox(dims, from_=2, to=100, width=5, textvariable=variable).pack(side=tk.LEFT, fill=tk.X, expand=True)
            if variable is self.columns:
                ttk.Label(dims, text="×", style="Muted.TLabel").pack(side=tk.LEFT, padx=5)
        ttk.Label(tools, text="Шаг сетки, мм", style="Muted.TLabel").pack(anchor=tk.W)
        ttk.Spinbox(tools, from_=5, to=500, increment=5, textvariable=self.cell_distance).pack(fill=tk.X, pady=(4, 7))
        ttk.Button(tools, text="Применить карту", command=self._apply_map_settings, style="Accent.TButton").pack(fill=tk.X)
        ttk.Label(tools, text="Колесо — прокрутка\nCtrl + колесо — масштаб\nСредняя кнопка — двигать карту", style="Hint.TLabel", justify=tk.LEFT).pack(anchor=tk.W, pady=(16, 0))

        map_panel = ttk.Frame(workspace, style="Panel.TFrame", padding=12)
        workspace.add(map_panel, weight=1)
        map_header = ttk.Frame(map_panel, style="Panel.TFrame")
        map_header.pack(fill=tk.X, pady=(2, 10))
        ttk.Label(map_header, text="ПОЛЕ МАРШРУТА", style="Eyebrow.TLabel").pack(side=tk.LEFT)
        self.map_info = ttk.Label(map_header, text="", style="MapMuted.TLabel")
        self.map_info.pack(side=tk.RIGHT)
        canvas_frame = ttk.Frame(map_panel, style="Map.TFrame")
        canvas_frame.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(canvas_frame, background=COLORS["background"], highlightthickness=1, highlightbackground=COLORS["border"], cursor="crosshair")
        x_scroll = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        y_scroll = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=x_scroll.set, yscrollcommand=y_scroll.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        canvas_frame.rowconfigure(0, weight=1)
        canvas_frame.columnconfigure(0, weight=1)
        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<Double-Button-1>", self._edit_route_point)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<ButtonPress-2>", lambda event: self.canvas.scan_mark(event.x, event.y))
        self.canvas.bind("<B2-Motion>", lambda event: self.canvas.scan_dragto(event.x, event.y, gain=1))
        self.canvas.bind("<MouseWheel>", self._on_canvas_wheel)
        self.canvas.bind("<Control-MouseWheel>", self._on_canvas_zoom)
        self.canvas.bind("<Configure>", self._on_canvas_resize)

        inspector = ttk.Frame(workspace, style="Panel.TFrame", padding=14, width=260)
        workspace.add(inspector, weight=0)
        self.inspector_title = ttk.Label(inspector, text="СВОЙСТВА ТОЧКИ", style="Eyebrow.TLabel")
        self.inspector_title.pack(anchor=tk.W)
        self.inspector_summary = ttk.Label(inspector, text="Выбери точку или участок на карте", style="InspectorTitle.TLabel", wraplength=230)
        self.inspector_summary.pack(anchor=tk.W, pady=(8, 14))
        ttk.Label(inspector, text="ДВИЖЕНИЕ К СЛЕДУЮЩЕЙ ТОЧКЕ", style="Eyebrow.TLabel", wraplength=225).pack(anchor=tk.W)
        self.segment_mode_box = ttk.Combobox(inspector, state="readonly", textvariable=self.segment_mode_var, values=("Вперёд", "Задом", "Дуга (управляемый поворот)"))
        self.segment_mode_box.pack(fill=tk.X, pady=(6, 10))
        ttk.Label(inspector, text="Скорость, мм/с · пусто = 100", style="Muted.TLabel", wraplength=230).pack(anchor=tk.W)
        ttk.Entry(inspector, textvariable=self.segment_speed_var).pack(fill=tk.X, pady=(5, 10))
        ttk.Label(inspector, text="Угол дуги, градусы", style="Muted.TLabel").pack(anchor=tk.W)
        ttk.Entry(inspector, textvariable=self.segment_curve_var).pack(fill=tk.X, pady=(5, 14))
        ttk.Separator(inspector).pack(fill=tk.X, pady=(0, 12))
        ttk.Label(inspector, text="КОМАНДА В ЭТОЙ ТОЧКЕ", style="Eyebrow.TLabel").pack(anchor=tk.W)
        self.marker_action_box = ttk.Combobox(inspector, state="readonly", textvariable=self.marker_action_var, values=("Нет", "Поворот на месте", "Остановка", "Метка"))
        self.marker_action_box.pack(fill=tk.X, pady=(6, 8))
        ttk.Label(inspector, text="Угол поворота", style="Muted.TLabel").pack(anchor=tk.W)
        ttk.Entry(inspector, textvariable=self.marker_angle_var).pack(fill=tk.X, pady=(5, 8))
        ttk.Label(inspector, text="Название / заметка", style="Muted.TLabel").pack(anchor=tk.W)
        ttk.Entry(inspector, textvariable=self.marker_text_var).pack(fill=tk.X, pady=(5, 12))
        ttk.Button(inspector, text="Применить свойства", command=self._apply_inspector_changes, style="Accent.TButton").pack(fill=tk.X)
        ttk.Button(inspector, text="Настройки хаба и тест", command=self._open_bluetooth_menu, style="Toolbar.TButton").pack(fill=tk.X, pady=(8, 0))

        footer = ttk.Frame(self.root, style="Footer.TFrame", padding=(16, 8))
        footer.pack(fill=tk.X)
        self.ble_status = ttk.Label(footer, text="○  Хаб отключён", style="Footer.TLabel")
        self.ble_status.pack(side=tk.LEFT)
        self.status = ttk.Label(footer, text="", style="Footer.TLabel", anchor=tk.E)
        self.status.pack(side=tk.RIGHT)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Control-o>", lambda _event: self._load())
        self.root.bind("<Control-s>", lambda _event: self._save())
        self.root.bind("<Control-z>", lambda _event: self._undo())

    def _build_ui(self):
        header = ttk.Frame(self.root, style="Header.TFrame", padding=(16, 10))
        header.pack(side=tk.TOP, fill=tk.X)
        self.top_connect_button = ttk.Button(
            header,
            text="Подключить",
            command=self._toggle_connection,
            style="Connect.TButton",
        )
        self.top_connect_button.pack(side=tk.LEFT)

        self.file_menu = tk.Menu(
            self.root,
            tearoff=False,
            background=COLORS["surface"],
            foreground=COLORS["text"],
            activebackground=COLORS["accent"],
            activeforeground="#ffffff",
            borderwidth=0,
            relief=tk.FLAT,
        )
        self.file_menu.add_command(label="Новый маршрут", command=self._new_route)
        self.file_menu.add_separator()
        self.file_menu.add_command(label="Открыть…", command=self._load)
        self.file_menu.add_command(
            label="Импортировать маршрут…", command=self._load
        )
        self.file_menu.add_command(label="Сохранить", command=self._save)
        self.file_menu.add_command(label="Сохранить как…", command=self._save_as)
        self.file_menu.add_separator()
        self.file_menu.add_command(
            label="Экспортировать программу Pybricks…",
            command=self._export_pybricks,
        )
        self.file_menu_button = ttk.Button(
            header,
            text="Файлы  ▾",
            command=self._show_file_menu,
            style="File.TButton",
        )
        self.file_menu_button.pack(side=tk.LEFT, padx=(10, 0))
        ttk.Label(
            header, text="Маршруты робота", style="Title.TLabel"
        ).pack(side=tk.LEFT, padx=24)
        self.top_run_button = ttk.Button(
            header,
            text="▶  Запустить",
            command=self._run_route_over_bluetooth,
            style="Run.TButton",
        )
        self.top_run_button.pack(side=tk.RIGHT)

        body = ttk.Frame(self.root, style="App.TFrame")
        body.pack(fill=tk.BOTH, expand=True)
        controls = ttk.Frame(body, style="Sidebar.TFrame", padding=(16, 16))
        controls.pack(side=tk.LEFT, fill=tk.Y)
        controls.configure(width=260)
        controls.pack_propagate(False)
        ttk.Label(controls, text="ИНСТРУМЕНТЫ", style="Section.TLabel").pack(
            anchor=tk.W, pady=(0, 8)
        )
        tools = (
            ("✎  Кисть", "brush"),
            ("●  Точка", "point"),
            ("⌖  Старт робота", "start"),
            ("⌫  Ластик", "erase"),
        )
        for label, value in tools:
            ttk.Radiobutton(
                controls,
                text=label,
                value=value,
                variable=self.tool,
                command=self._update_status,
                style="Tool.TRadiobutton",
            ).pack(fill=tk.X, pady=2)

        ttk.Label(controls, text="НАПРАВЛЕНИЕ СТАРТА", style="Section.TLabel").pack(
            anchor=tk.W, pady=(18, 8)
        )
        directions = ttk.Frame(controls, style="Sidebar.TFrame")
        directions.pack(anchor=tk.W, pady=(0, 6))
        for value in HEADINGS:
            ttk.Radiobutton(
                directions,
                text={"N": "↑", "E": "→", "S": "↓", "W": "←"}[value],
                value=value,
                variable=self.heading,
                command=self._on_heading_change,
                style="Direction.TRadiobutton",
            ).pack(side=tk.LEFT, padx=(0, 5))

        ttk.Label(controls, text="ДОБАВИТЬ ШАГ", style="Section.TLabel").pack(
            anchor=tk.W, pady=(18, 8)
        )
        for label, direction in (
            ("↑   Вперёд", "forward"),
            ("→   Вправо", "right"),
            ("↓   Назад", "back"),
            ("←   Влево", "left"),
        ):
            ttk.Button(
                controls,
                text=label,
                command=lambda d=direction: self._step_route(d),
                style="Panel.TButton",
            ).pack(fill=tk.X, pady=2)

        ttk.Label(controls, text="РАЗМЕР СЕТКИ", style="Section.TLabel").pack(
            anchor=tk.W, pady=(18, 8)
        )
        dimensions = ttk.Frame(controls, style="Sidebar.TFrame")
        dimensions.pack(fill=tk.X)
        for variable in (self.columns, self.rows):
            tk.Spinbox(
                dimensions,
                from_=2,
                to=100,
                width=4,
                textvariable=variable,
                background=COLORS["surface_alt"],
                foreground=COLORS["text"],
                buttonbackground=COLORS["surface"],
                insertbackground=COLORS["text"],
                relief=tk.FLAT,
            ).pack(side=tk.LEFT)
            if variable is self.columns:
                ttk.Label(dimensions, text=" × ", style="Muted.TLabel").pack(
                    side=tk.LEFT
                )
        ttk.Button(
            dimensions,
            text="Применить",
            command=self._resize_grid,
            style="Panel.TButton",
        ).pack(side=tk.RIGHT)
        ttk.Label(
            controls,
            text="1 клетка = {} мм".format(CELL_DISTANCE_MM),
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(8, 0))
        ttk.Label(controls, text="Физический шаг клетки (мм)", style="Muted.TLabel").pack(anchor=tk.W, pady=(8, 2))
        tk.Spinbox(controls, from_=5, to=500, increment=5, width=7, textvariable=self.cell_distance).pack(anchor=tk.W)
        ttk.Separator(controls, orient=tk.HORIZONTAL).pack(
            fill=tk.X, pady=(20, 12)
        )
        ttk.Button(
            controls,
            text="Настройка робота и тест",
            command=self._open_bluetooth_menu,
            style="Panel.TButton",
        ).pack(fill=tk.X, pady=2)
        ttk.Button(
            controls,
            text="Отменить шаг",
            command=self._undo,
            style="Panel.TButton",
        ).pack(fill=tk.X, pady=2)
        ttk.Button(
            controls,
            text="Очистить маршрут",
            command=self._clear_route,
            style="Panel.TButton",
        ).pack(fill=tk.X, pady=2)
        ttk.Label(
            controls,
            text="Кисть: тяни мышь по карте.\n"
            "Точка: добавляй узлы маршрута.\n"
            "Поставь старт, затем рисуй путь.\n"
            "Большую карту можно прокручивать.",
            justify=tk.LEFT,
            style="Help.TLabel",
            wraplength=220,
        ).pack(anchor=tk.W, pady=(20, 8))

        self.ble_status = ttk.Label(
            self.root, text="○  Хаб не подключён", style="Footer.TLabel"
        )
        self.ble_status.pack(side=tk.BOTTOM, fill=tk.X, padx=16, pady=(0, 10))
        self.status = ttk.Label(
            self.root, text="", style="Footer.TLabel", anchor=tk.E
        )
        self.status.pack(side=tk.BOTTOM, fill=tk.X, padx=16, pady=(0, 4))

        board = ttk.Frame(body, style="Map.TFrame", padding=18)
        board.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        map_header = ttk.Frame(board, style="Map.TFrame")
        map_header.pack(fill=tk.X, pady=(0, 12))
        ttk.Label(map_header, text="Карта маршрута", style="MapTitle.TLabel").pack(
            side=tk.LEFT
        )
        self.map_info = ttk.Label(map_header, text="", style="MapMuted.TLabel")
        self.map_info.pack(side=tk.RIGHT)
        canvas_frame = ttk.Frame(board, style="Map.TFrame")
        canvas_frame.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(
            canvas_frame,
            background=COLORS["background"],
            highlightthickness=1,
            highlightbackground=COLORS["border"],
        )
        x_scroll = ttk.Scrollbar(
            canvas_frame, orient=tk.HORIZONTAL, command=self.canvas.xview
        )
        y_scroll = ttk.Scrollbar(
            canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview
        )
        self.canvas.configure(
            xscrollcommand=x_scroll.set,
            yscrollcommand=y_scroll.set,
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        canvas_frame.rowconfigure(0, weight=1)
        canvas_frame.columnconfigure(0, weight=1)
        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<Double-Button-1>", self._edit_route_point)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Control-o>", lambda _event: self._load())
        self.root.bind("<Control-s>", lambda _event: self._save())
        self.root.bind("<Control-z>", lambda _event: self._undo())

    def _configure_theme(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            ".",
            background=COLORS["background"],
            foreground=COLORS["text"],
            font=("Segoe UI", 10),
        )
        style.configure("App.TFrame", background=COLORS["background"])
        style.configure("Header.TFrame", background=COLORS["surface"])
        style.configure("Sidebar.TFrame", background=COLORS["surface"])
        style.configure("Map.TFrame", background=COLORS["background"])
        style.configure(
            "TLabel", background=COLORS["background"], foreground=COLORS["text"]
        )
        style.configure(
            "Title.TLabel",
            background=COLORS["surface"],
            foreground=COLORS["text"],
            font=("Segoe UI Semibold", 12),
        )
        style.configure(
            "Section.TLabel",
            background=COLORS["surface"],
            foreground=COLORS["muted"],
            font=("Segoe UI Semibold", 9),
        )
        style.configure(
            "MapTitle.TLabel",
            background=COLORS["background"],
            foreground=COLORS["text"],
            font=("Segoe UI Semibold", 12),
        )
        style.configure(
            "MapMuted.TLabel",
            background=COLORS["background"],
            foreground=COLORS["muted"],
        )
        style.configure(
            "Muted.TLabel",
            background=COLORS["surface"],
            foreground=COLORS["muted"],
        )
        style.configure(
            "Footer.TLabel",
            background=COLORS["background"],
            foreground=COLORS["muted"],
            font=("Segoe UI", 9),
        )
        style.configure(
            "Help.TLabel",
            background=COLORS["surface"],
            foreground=COLORS["muted"],
            font=("Segoe UI", 9),
        )
        style.configure(
            "TButton",
            background=COLORS["surface_alt"],
            foreground=COLORS["text"],
            borderwidth=0,
            focusthickness=0,
            padding=(10, 7),
        )
        style.map(
            "TButton",
            background=[("disabled", COLORS["surface"]), ("active", COLORS["border"])],
            foreground=[("disabled", COLORS["muted"])],
        )
        style.configure(
            "Panel.TButton",
            background=COLORS["surface_alt"],
            foreground=COLORS["text"],
            anchor=tk.W,
            padding=(12, 9),
        )
        style.configure(
            "Connect.TButton",
            background=COLORS["surface_alt"],
            foreground=COLORS["text"],
            padding=(14, 8),
        )
        style.configure(
            "File.TButton",
            background=COLORS["surface_alt"],
            foreground=COLORS["text"],
            padding=(14, 8),
        )
        style.configure(
            "Disconnect.TButton",
            background=COLORS["surface_alt"],
            foreground=COLORS["route"],
            padding=(14, 8),
        )
        style.configure(
            "Run.TButton",
            background=COLORS["green"],
            foreground="#07160f",
            font=("Segoe UI Semibold", 10),
            padding=(16, 8),
        )
        style.map(
            "Run.TButton",
            background=[
                ("disabled", COLORS["surface_alt"]),
                ("active", COLORS["green_hover"]),
            ],
            foreground=[("disabled", COLORS["muted"])],
        )
        style.configure(
            "Tool.TRadiobutton",
            background=COLORS["surface"],
            foreground=COLORS["text"],
            padding=(8, 7),
        )
        style.map(
            "Tool.TRadiobutton",
            background=[
                ("selected", COLORS["surface_alt"]),
                ("active", COLORS["surface_alt"]),
            ],
            foreground=[("selected", COLORS["accent_hover"])],
        )
        style.configure(
            "Direction.TRadiobutton",
            background=COLORS["surface_alt"],
            foreground=COLORS["text"],
            padding=(8, 6),
        )
        style.map(
            "Direction.TRadiobutton",
            background=[("selected", COLORS["accent"]), ("active", COLORS["border"])],
            foreground=[("selected", "#ffffff")],
        )
        style.configure("TSeparator", background=COLORS["border"])
        style.configure(".", background=COLORS["background"], foreground=COLORS["text"], font=("Segoe UI", 10))
        style.configure("Topbar.TFrame", background=COLORS["surface"])
        style.configure("Workspace.TFrame", background=COLORS["background"])
        style.configure("Panel.TFrame", background=COLORS["surface"])
        style.configure("Map.TFrame", background=COLORS["background"])
        style.configure("Footer.TFrame", background=COLORS["surface"])
        style.configure("BrandMark.TLabel", background=COLORS["surface"], foreground=COLORS["accent"], font=("Segoe UI Symbol", 22, "bold"))
        style.configure("Brand.TLabel", background=COLORS["surface"], foreground=COLORS["accent"], font=("Segoe UI Semibold", 8))
        style.configure("Project.TLabel", background=COLORS["surface"], foreground=COLORS["text"], font=("Segoe UI Semibold", 12))
        style.configure("Eyebrow.TLabel", background=COLORS["surface"], foreground=COLORS["muted"], font=("Segoe UI Semibold", 8))
        style.configure("InspectorTitle.TLabel", background=COLORS["surface"], foreground=COLORS["text"], font=("Segoe UI Semibold", 13))
        style.configure("Hint.TLabel", background=COLORS["surface"], foreground=COLORS["muted"], font=("Segoe UI", 9))
        style.configure("MapMuted.TLabel", background=COLORS["surface"], foreground=COLORS["muted"])
        style.configure("Footer.TLabel", background=COLORS["surface"], foreground=COLORS["muted"], font=("Segoe UI", 9))
        style.configure("Tool.TRadiobutton", background=COLORS["surface"], foreground=COLORS["text"], padding=(10, 9), anchor=tk.W)
        style.map("Tool.TRadiobutton", background=[("selected", COLORS["surface_alt"]), ("active", COLORS["surface_alt"])], foreground=[("selected", COLORS["accent"])])
        style.configure("Toolbar.TButton", background=COLORS["surface_alt"], foreground=COLORS["text"], padding=(10, 8))
        style.map("Toolbar.TButton", background=[("active", COLORS["border"])])
        style.configure("Accent.TButton", background=COLORS["accent"], foreground=COLORS["background"], font=("Segoe UI Semibold", 10), padding=(10, 9))
        style.map("Accent.TButton", background=[("active", COLORS["accent_hover"])])
        style.configure("Run.TButton", background=COLORS["green"], foreground=COLORS["background"], font=("Segoe UI Semibold", 10), padding=(14, 9))
        style.map("Run.TButton", background=[("active", COLORS["green_hover"])])
        style.configure("TEntry", fieldbackground=COLORS["surface_alt"], foreground=COLORS["text"], insertcolor=COLORS["text"], bordercolor=COLORS["border"], padding=7)
        style.configure("TCombobox", fieldbackground=COLORS["surface_alt"], background=COLORS["surface_alt"], foreground=COLORS["text"], arrowcolor=COLORS["accent"], padding=7)
        style.configure("TSpinbox", fieldbackground=COLORS["surface_alt"], background=COLORS["surface_alt"], foreground=COLORS["text"], arrowcolor=COLORS["accent"], padding=5)
        style.configure("Motor.TFrame", background=COLORS["surface_alt"])
        style.configure("MotorPort.TLabel", background=COLORS["surface_alt"], foreground=COLORS["accent"], font=("Segoe UI Semibold", 12))
        style.configure("MotorRole.TLabel", background=COLORS["surface_alt"], foreground=COLORS["muted"], font=("Segoe UI", 8))
        style.configure("MotorValue.TLabel", background=COLORS["surface_alt"], foreground=COLORS["muted"], font=("Consolas", 9))

    def _open_manual_control(self):
        if self.manual_window is not None and self.manual_window.winfo_exists():
            self.manual_window.deiconify()
            self.manual_window.lift()
            self._refresh_recording_list()
            return
        window = tk.Toplevel(self.root)
        window.title("Ручное управление и записи · Pybricks")
        window.geometry("1120x790")
        window.minsize(980, 680)
        window.configure(background=COLORS["background"])
        window.protocol("WM_DELETE_WINDOW", self._hide_manual_window)
        self.manual_window = window

        header = ttk.Frame(window, style="Topbar.TFrame", padding=(18, 14))
        header.pack(fill=tk.X)
        ttk.Label(header, text="РУЧНОЕ УПРАВЛЕНИЕ", style="Brand.TLabel").pack(side=tk.LEFT)
        self.manual_status_label = ttk.Label(header, textvariable=self.manual_status_var, style="Project.TLabel")
        self.manual_status_label.pack(side=tk.LEFT, padx=18)
        ttk.Button(header, text="Запустить ручной режим", command=self._start_manual_session, style="Accent.TButton").pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(header, text="Завершить сеанс", command=self._stop_manual_session, style="Toolbar.TButton").pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(header, text="Остановить моторы", command=self._manual_stop_all, style="Toolbar.TButton").pack(side=tk.RIGHT)

        body = ttk.Panedwindow(window, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True, padx=14, pady=14)
        controls = ttk.Frame(body, style="Panel.TFrame", padding=16)
        body.add(controls, weight=1)
        recordings = ttk.Frame(body, style="Panel.TFrame", padding=16)
        body.add(recordings, weight=1)

        ttk.Label(controls, text="МОТОРЫ И СКОРОСТЬ", style="Eyebrow.TLabel").pack(anchor=tk.W)
        settings = ttk.Frame(controls, style="Panel.TFrame")
        settings.pack(fill=tk.X, pady=(8, 12))
        ttk.Label(settings, text="Привод: A — левый · E — правый", style="Muted.TLabel").grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=3)
        for row, (label, variable) in enumerate((
            ("Движение, мм/с", self.manual_drive_speed),
            ("Поворот, мм/с", self.manual_turn_speed),
            ("Навесной мотор, °/с", self.manual_attachment_speed),
        ), start=1):
            ttk.Label(settings, text=label, style="Muted.TLabel").grid(row=row, column=0, sticky=tk.W, pady=3)
            ttk.Spinbox(settings, from_=50, to=1000, increment=50, textvariable=variable, width=8).grid(row=row, column=1, sticky=tk.E, padx=(12, 0), pady=3)
        ttk.Label(settings, text="Навесной порт", style="Muted.TLabel").grid(row=4, column=0, sticky=tk.W, pady=3)
        self.manual_port_box = ttk.Combobox(settings, state="readonly", values=("B", "C", "D", "F"), textvariable=self.manual_attachment_port, width=6)
        self.manual_port_box.grid(row=4, column=1, sticky=tk.E, padx=(12, 0), pady=3)
        self.manual_port_box.bind("<<ComboboxSelected>>", self._manual_attachment_port_changed)
        for variable in (self.manual_drive_speed, self.manual_turn_speed, self.manual_attachment_speed):
            variable.trace_add("write", self._manual_settings_changed)
        settings.columnconfigure(0, weight=1)

        ttk.Label(controls, text="УПРАВЛЕНИЕ · держи кнопку", style="Eyebrow.TLabel").pack(anchor=tk.W, pady=(8, 4))
        pad = ttk.Frame(controls, style="Panel.TFrame")
        pad.pack(anchor=tk.CENTER, pady=(2, 12))
        self._make_hold_button(pad, "↑", "forward", 0, 1)
        self._make_hold_button(pad, "←", "left", 1, 0)
        self._make_hold_button(pad, "СТОП", "stop", 1, 1)
        self._make_hold_button(pad, "→", "right", 1, 2)
        self._make_hold_button(pad, "↓", "backward", 2, 1)
        ttk.Label(controls, text="Навесной мотор", style="Eyebrow.TLabel").pack(anchor=tk.W, pady=(0, 5))
        attachment = ttk.Frame(controls, style="Panel.TFrame")
        attachment.pack(fill=tk.X)
        self._make_hold_button(attachment, "⟳  Вперёд", "attach_forward", 0, 0)
        self._make_hold_button(attachment, "⟲  Назад", "attach_backward", 0, 1)

        ttk.Separator(controls).pack(fill=tk.X, pady=14)
        ttk.Label(controls, text="КОМАНДУЕМАЯ СКОРОСТЬ · ПОРТЫ A–F", style="Eyebrow.TLabel").pack(anchor=tk.W)
        motors = ttk.Frame(controls, style="Panel.TFrame")
        motors.pack(fill=tk.X, pady=(7, 0))
        for index, port in enumerate("ABCDEF"):
            row, col = divmod(index, 2)
            card = ttk.Frame(motors, style="Motor.TFrame", padding=(8, 7))
            card.grid(row=row, column=col, sticky="ew", padx=(0, 7), pady=3)
            ttk.Label(card, text=port, style="MotorPort.TLabel", width=2).pack(side=tk.LEFT)
            value = ttk.Label(card, text="0", style="MotorValue.TLabel", width=7, anchor=tk.E)
            value.pack(side=tk.RIGHT)
            ttk.Label(card, text={"A": "Левый привод", "E": "Правый привод"}.get(port, "Навесной"), style="MotorRole.TLabel").pack(side=tk.LEFT, padx=7)
            self.manual_motor_widgets[port] = value
        motors.columnconfigure(0, weight=1)
        motors.columnconfigure(1, weight=1)
        window.bind("<KeyPress>", self._manual_key_press)
        window.bind("<KeyRelease>", self._manual_key_release)
        window.bind("<FocusOut>", self._manual_focus_lost)

        ttk.Label(recordings, text="ЗАПИСИ И ВОСПРОИЗВЕДЕНИЕ", style="Eyebrow.TLabel").pack(anchor=tk.W)
        list_frame = ttk.Frame(recordings, style="Panel.TFrame")
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(8, 8))
        self.recording_list = tk.Listbox(list_frame, background=COLORS["surface_alt"], foreground=COLORS["text"], selectbackground=COLORS["accent"], selectforeground=COLORS["background"], highlightthickness=0, borderwidth=0, activestyle="none", font=("Segoe UI", 10))
        self.recording_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        recording_scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.recording_list.yview)
        recording_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.recording_list.configure(yscrollcommand=recording_scroll.set)
        self.recording_list.bind("<<ListboxSelect>>", self._select_recording)
        self.recording_summary = ttk.Label(recordings, text="Выбери запись для просмотра", style="Muted.TLabel", wraplength=420)
        self.recording_summary.pack(anchor=tk.W, pady=(0, 8))
        self.recording_timeline = tk.Canvas(recordings, height=190, background=COLORS["background"], highlightthickness=1, highlightbackground=COLORS["border"])
        self.recording_timeline.pack(fill=tk.X, pady=(0, 10))
        record_actions = ttk.Frame(recordings, style="Panel.TFrame")
        record_actions.pack(fill=tk.X)
        self.manual_record_button = ttk.Button(record_actions, text="⏺  Начать запись", command=self._toggle_manual_recording, style="Accent.TButton")
        self.manual_record_button.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(record_actions, text="▶  Воспроизвести", command=self._play_selected_recording, style="Run.TButton").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))
        ttk.Button(record_actions, text="Импортировать…", command=self._import_recording, style="Toolbar.TButton").pack(side=tk.LEFT, padx=(8, 0))
        self._refresh_recording_list()

    def _make_hold_button(self, parent, label, action, row, column):
        button = ttk.Button(parent, text=label, style="Toolbar.TButton")
        button.grid(row=row, column=column, sticky="nsew", padx=3, pady=3, ipadx=7, ipady=7)
        button.bind("<ButtonPress-1>", lambda _event, key=action: self._manual_key_down(key))
        button.bind("<ButtonRelease-1>", lambda _event, key=action: self._manual_key_up(key))
        parent.columnconfigure(column, weight=1)
        parent.rowconfigure(row, weight=1)
        return button

    def _start_manual_session(self):
        if not self.ble_connected:
            self.manual_start_when_connected = True
            self.manual_status_var.set("Подключаюсь к хабу…")
            self._connect_bluetooth()
            return
        if self.ble_running:
            messagebox.showinfo("Ручное управление", "Сначала останови текущую программу на хабе.")
            return
        program_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "HZ", "1.py")
        try:
            with open(program_path, "r", encoding="utf-8") as program_file:
                source = program_file.read()
        except OSError as error:
            messagebox.showerror("Ручной режим", "Не удалось открыть HZ/1.py: {}".format(error))
            return
        self.manual_setup_pending = True
        self.manual_ready = False
        self.manual_last_command = None
        self.manual_status_var.set("Загружаю контроллер моторов на хаб…")
        self._run_ble_program(source, "Ручное управление")

    def _stop_manual_session(self):
        if not self.manual_ready:
            return
        if self.manual_recording:
            self._autosave_manual_recording()
        self.manual_ready = False
        self._stop_bluetooth_run()

    def _manual_key_down(self, action):
        if self.manual_playback_events:
            self._cancel_manual_playback()
        if action == "stop":
            self.manual_keys.clear()
            self._manual_stop_all()
            return
        self.manual_keys.add(action)
        self._update_manual_motors()

    def _manual_key_up(self, action):
        self.manual_keys.discard(action)
        self._update_manual_motors()

    def _manual_key_press(self, event):
        if event.widget.winfo_class() in ("TEntry", "TSpinbox", "TCombobox", "Listbox", "Canvas"):
            return None
        keys = {"Up": "forward", "Down": "backward", "Left": "left", "Right": "right", "w": "forward", "s": "backward", "a": "left", "d": "right", "q": "attach_forward", "e": "attach_backward", "space": "attachment_stop"}
        action = keys.get(event.keysym)
        if action:
            self._manual_key_down(action)
            return "break"

    def _manual_key_release(self, event):
        if event.widget.winfo_class() in ("TEntry", "TSpinbox", "TCombobox", "Listbox", "Canvas"):
            return None
        keys = {"Up": "forward", "Down": "backward", "Left": "left", "Right": "right", "w": "forward", "s": "backward", "a": "left", "d": "right", "q": "attach_forward", "e": "attach_backward", "space": "attachment_stop"}
        action = keys.get(event.keysym)
        if action:
            self._manual_key_up(action)
            return "break"

    def _manual_focus_lost(self, _event):
        if self.manual_keys:
            self.manual_keys.clear()
            self._update_manual_motors()

    def _autosave_manual_recording(self):
        if not self.manual_recording:
            return
        timestamp = round((time.perf_counter() - self.manual_recording_started) * 1000)
        if not self.manual_recording_events or self.manual_recording_events[-1][1] != "stop_all":
            self.manual_recording_events.append([timestamp, "stop_all"])
        self.manual_recording = False
        if hasattr(self, "manual_record_button"):
            self.manual_record_button.configure(text="⏺  Начать запись")
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "HZ", "robot_recording_{}.json".format(time.strftime("%Y%m%d_%H%M%S")))
        data = {"version": 2, "left_port": "A", "right_port": "E", "events": self.manual_recording_events}
        try:
            with open(path, "w", encoding="utf-8") as recording_file:
                json.dump(data, recording_file, ensure_ascii=False, indent=2)
        except OSError as error:
            self.manual_status_var.set("Не удалось сохранить запись: {}".format(error))
        else:
            self.manual_status_var.set("Запись автоматически сохранена: {}".format(os.path.basename(path)))
            self._refresh_recording_list(path)

    def _update_manual_motors(self):
        forward = int("forward" in self.manual_keys) - int("backward" in self.manual_keys)
        turn = int("right" in self.manual_keys) - int("left" in self.manual_keys)
        try:
            drive = max(50, min(1000, int(self.manual_drive_speed.get())))
            turning = max(50, min(1000, int(self.manual_turn_speed.get())))
            attachment_limit = max(50, min(1000, int(self.manual_attachment_speed.get())))
        except (tk.TclError, ValueError):
            return
        left_speed = max(-1000, min(1000, forward * drive + turn * turning))
        right_speed = max(-1000, min(1000, forward * drive - turn * turning))
        attachment_direction = int("attach_forward" in self.manual_keys) - int("attach_backward" in self.manual_keys)
        if "attachment_stop" in self.manual_keys:
            attachment_direction = 0
        attachment_speed = attachment_direction * attachment_limit
        port = self.manual_attachment_port.get()
        old_port = self.manual_last_attachment_port
        self.manual_motor_speeds.update({"A": left_speed, "E": right_speed, port: attachment_speed})
        if old_port != port:
            self.manual_motor_speeds[old_port] = 0
            self.manual_last_attachment_port = port
        self._refresh_motor_visuals()
        command = "control,{},{},{},{}".format(left_speed, right_speed, port, attachment_speed)
        if old_port != port and self.manual_ready:
            self.manual_send_batch(["motor,{},0".format(old_port), command])
        else:
            self.manual_send_command(command)

    def _manual_attachment_port_changed(self, _event=None):
        self._update_manual_motors()

    def _manual_settings_changed(self, *_args):
        if self.manual_ready and self.manual_keys:
            self._update_manual_motors()

    def manual_send_command(self, command):
        if not self.manual_ready:
            if self.manual_window is not None and self.manual_window.winfo_exists():
                self.manual_status_var.set("Сначала запусти ручной режим на хабе")
            return
        if command == self.manual_last_command:
            return
        self.manual_last_command = command
        if command == "stop_all":
            self.manual_motor_speeds = {port: 0 for port in "ABCDEF"}
        else:
            self.manual_motor_speeds.update(self._recording_speeds(command))
        self._refresh_motor_visuals()
        if self.manual_recording:
            timestamp = round((time.perf_counter() - self.manual_recording_started) * 1000)
            self.manual_recording_events.append([timestamp, command])
        self._ble_send_async({"command": "manual", "value": command}, "manual")

    def manual_send_batch(self, commands):
        if not self.manual_ready:
            return
        self.manual_last_command = commands[-1]
        if self.manual_recording:
            for command in commands:
                timestamp = round((time.perf_counter() - self.manual_recording_started) * 1000)
                self.manual_recording_events.append([timestamp, command])
        self._ble_send_async({"command": "manual_batch", "values": commands}, "manual")

    def _manual_stop_all(self):
        if self.manual_playback_events:
            self._cancel_manual_playback()
        self.manual_keys.clear()
        self.manual_motor_speeds = {port: 0 for port in "ABCDEF"}
        self._refresh_motor_visuals()
        self.manual_send_command("stop_all")

    def _cancel_manual_playback(self):
        if self.manual_playback_after_id is not None:
            try:
                self.root.after_cancel(self.manual_playback_after_id)
            except tk.TclError:
                pass
            self.manual_playback_after_id = None
        self.manual_playback_events = []
        self.manual_waiting_for_ack = False
        self.manual_status_var.set("Воспроизведение остановлено ручным вводом")

    def _refresh_motor_visuals(self):
        if not self.manual_motor_widgets:
            return
        for port, label in self.manual_motor_widgets.items():
            speed = self.manual_motor_speeds.get(port, 0)
            role = "Левый привод" if port == "A" else "Правый привод" if port == "E" else "Навесной"
            arrow = "▶" if speed > 0 else "◀" if speed < 0 else "—"
            label.configure(text="{} {}".format(arrow, abs(speed)), foreground=COLORS["accent"] if speed else COLORS["muted"])

    def _toggle_manual_recording(self):
        if self.manual_playback_events:
            messagebox.showinfo("Запись", "Сначала останови воспроизведение.", parent=self.manual_window)
            return
        if self.manual_recording:
            timestamp = round((time.perf_counter() - self.manual_recording_started) * 1000)
            if not self.manual_recording_events or self.manual_recording_events[-1][1] != "stop_all":
                self.manual_recording_events.append([timestamp, "stop_all"])
            self.manual_recording = False
            self.manual_record_button.configure(text="⏺  Начать запись")
            self._manual_stop_all()
            directory = os.path.join(os.path.dirname(os.path.abspath(__file__)), "HZ")
            initial = "robot_recording_{}.json".format(time.strftime("%Y%m%d_%H%M%S"))
            path = filedialog.asksaveasfilename(parent=self.manual_window, initialdir=directory, initialfile=initial, defaultextension=".json", filetypes=(("Запись движения", "*.json"), ("Все файлы", "*.*")))
            if path:
                data = {"version": 2, "left_port": "A", "right_port": "E", "events": self.manual_recording_events}
                try:
                    with open(path, "w", encoding="utf-8") as recording_file:
                        json.dump(data, recording_file, ensure_ascii=False, indent=2)
                except OSError as error:
                    messagebox.showerror("Запись", str(error), parent=self.manual_window)
                else:
                    self.manual_status_var.set("Запись сохранена: " + os.path.basename(path))
                    self._refresh_recording_list(path)
            else:
                self.manual_status_var.set("Запись отменена; файл не сохранён")
        else:
            if not self.manual_ready:
                messagebox.showinfo("Запись движения", "Сначала запусти ручной режим на хабе.", parent=self.manual_window)
                return
            self.manual_recording_events = [[0, self.manual_last_command or "control,0,0,B,0"]]
            self.manual_recording_started = time.perf_counter()
            self.manual_recording = True
            self.manual_record_button.configure(text="■  Остановить и сохранить")
            self.manual_status_var.set("● Идёт запись. Нажми кнопку записи ещё раз, чтобы сохранить.")

    def _recording_paths(self):
        roots = (os.path.join(os.path.dirname(os.path.abspath(__file__)), "HZ"), os.path.dirname(os.path.abspath(__file__)))
        paths = []
        for directory in roots:
            try:
                candidates = [os.path.join(directory, name) for name in os.listdir(directory) if name.lower().endswith(".json")]
            except OSError:
                continue
            for path in candidates:
                if path not in paths:
                    try:
                        with open(path, "r", encoding="utf-8") as candidate:
                            data = json.load(candidate)
                    except (OSError, ValueError, UnicodeError):
                        continue
                    if isinstance(data, dict) and isinstance(data.get("events"), list):
                        paths.append(path)
        return sorted(paths, key=lambda path: ("robot_recording" not in os.path.basename(path).lower(), os.path.basename(path).lower()))

    def _refresh_recording_list(self, select_path=None):
        if not self.manual_window or not self.manual_window.winfo_exists() or not hasattr(self, "recording_list"):
            return
        self.manual_recordings = self._recording_paths()
        self.recording_list.delete(0, tk.END)
        for path in self.manual_recordings:
            self.recording_list.insert(tk.END, os.path.basename(path))
        if select_path in self.manual_recordings:
            index = self.manual_recordings.index(select_path)
            self.recording_list.selection_set(index)
            self.recording_list.see(index)
            self._select_recording()
        elif self.manual_recordings:
            self.recording_list.selection_set(0)
            self._select_recording()
        else:
            self.recording_summary.configure(text="В HZ пока нет записей движения")
            self.recording_timeline.delete("all")

    def _load_recording_file(self, path):
        with open(path, "r", encoding="utf-8") as recording_file:
            data = json.load(recording_file)
        if not isinstance(data, dict) or data.get("version") not in (1, 2):
            raise ValueError("Поддерживаются записи HZ версий 1 и 2.")
        if not isinstance(data.get("events"), list):
            raise ValueError("В файле записи нет списка событий.")
        if (data.get("left_port"), data.get("right_port")) != ("A", "E"):
            raise ValueError("Запись должна использовать приводные порты A и E.")
        events = []
        previous = -1
        for event in data.get("events", []):
            if data["version"] == 1:
                if not isinstance(event, list) or len(event) != 3 or any(type(value) is not int for value in event):
                    raise ValueError("Неверный формат события версии 1.")
                timestamp, left, right = event
                command = "drive,{},{}".format(left, right)
            else:
                if not isinstance(event, list) or len(event) != 2 or type(event[0]) is not int or not isinstance(event[1], str):
                    raise ValueError("Неверный формат события версии 2.")
                timestamp, command = event
            if timestamp < 0 or timestamp < previous:
                raise ValueError("Временные отметки идут не по порядку.")
            self._validate_manual_recording_command(command)
            previous = timestamp
            events.append((timestamp, command))
        if not events:
            raise ValueError("В записи нет событий.")
        return events

    @staticmethod
    def _validate_manual_recording_command(command):
        if command == "stop_all":
            return
        parts = command.split(",")
        if parts[0] == "drive" and len(parts) == 3:
            speeds = [int(parts[1]), int(parts[2])]
        elif parts[0] == "control" and len(parts) == 5:
            if parts[3] not in ("B", "C", "D", "F"):
                raise ValueError("Неверный порт навесного мотора.")
            speeds = [int(parts[1]), int(parts[2]), int(parts[4])]
        elif parts[0] == "motor" and len(parts) == 3 and parts[1] in "ABCDEF":
            speeds = [int(parts[2])]
        else:
            raise ValueError("Неизвестная команда в записи: " + command)
        if any(abs(speed) > 1000 for speed in speeds):
            raise ValueError("Скорость в записи превышает 1000.")

    def _selected_recording_path(self):
        selection = self.recording_list.curselection()
        if not selection:
            return None
        index = selection[0]
        return self.manual_recordings[index] if index < len(self.manual_recordings) else None

    def _select_recording(self, _event=None):
        path = self._selected_recording_path()
        self.recording_timeline.delete("all")
        if path is None:
            return
        try:
            events = self._load_recording_file(path)
        except (OSError, ValueError, UnicodeError) as error:
            self.recording_summary.configure(text="Запись недоступна: {}".format(error))
            return
        duration = events[-1][0]
        self.recording_summary.configure(text="{}  ·  {} команд  ·  {} сек  ·  моторы A/E + навесной".format(os.path.basename(path), len(events), round(duration / 1000, 1)))
        self._draw_recording_timeline(events)

    def _draw_recording_timeline(self, events):
        canvas = self.recording_timeline
        canvas.delete("all")
        canvas.update_idletasks()
        width = max(300, canvas.winfo_width())
        height = max(120, canvas.winfo_height())
        left, right = 75, width - 12
        duration = max(1, events[-1][0])
        rows = (("A · левый", "A"), ("E · правый", "E"), ("Навесной", "aux"))
        for row, (label, port) in enumerate(rows):
            y = 34 + row * 47
            canvas.create_text(8, y, text=label, anchor=tk.W, fill=COLORS["muted"], font=("Segoe UI", 8))
            canvas.create_line(left, y, right, y, fill=COLORS["border"], width=3)
        for index, (timestamp, command) in enumerate(events):
            end_time = events[index + 1][0] if index + 1 < len(events) else duration
            if end_time <= timestamp:
                end_time = timestamp + 1
            speeds = self._recording_speeds(command)
            x1 = left + (right - left) * timestamp / duration
            x2 = left + (right - left) * end_time / duration
            values = (speeds.get("A", 0), speeds.get("E", 0), speeds.get("aux", 0))
            for row, speed in enumerate(values):
                if speed:
                    y = 34 + row * 47
                    color = COLORS["accent"] if speed > 0 else COLORS["route"]
                    canvas.create_line(x1, y, max(x1 + 2, x2), y, fill=color, width=8, capstyle=tk.ROUND)
        canvas.create_text(left, height - 12, text="0 с", anchor=tk.W, fill=COLORS["muted"], font=("Segoe UI", 8))
        canvas.create_text(right, height - 12, text="{} с".format(round(duration / 1000, 1)), anchor=tk.E, fill=COLORS["muted"], font=("Segoe UI", 8))

    @staticmethod
    def _recording_speeds(command):
        if command == "stop_all":
            return {}
        parts = command.split(",")
        if parts[0] == "drive" and len(parts) == 3:
            return {"A": int(parts[1]), "E": int(parts[2])}
        if parts[0] == "control" and len(parts) == 5:
            return {"A": int(parts[1]), "E": int(parts[2]), parts[3]: int(parts[4])}
        if parts[0] == "motor" and len(parts) == 3:
            return {parts[1]: int(parts[2])}
        return {}

    def _import_recording(self):
        path = filedialog.askopenfilename(parent=self.manual_window, title="Открыть запись HZ", filetypes=(("Записи JSON", "*.json"), ("Все файлы", "*.*")))
        if not path:
            return
        try:
            self._load_recording_file(path)
        except (OSError, ValueError, UnicodeError) as error:
            messagebox.showerror("Запись не открыта", str(error), parent=self.manual_window)
            return
        if path not in self.manual_recordings:
            self.manual_recordings.append(path)
            self.recording_list.insert(tk.END, os.path.basename(path))
        index = self.manual_recordings.index(path)
        self.recording_list.selection_clear(0, tk.END)
        self.recording_list.selection_set(index)
        self._select_recording()

    def _play_selected_recording(self):
        path = self._selected_recording_path()
        if not path:
            messagebox.showinfo("Воспроизведение", "Выбери запись в списке.", parent=self.manual_window)
            return
        if not self.manual_ready:
            messagebox.showinfo("Воспроизведение", "Сначала запусти ручной режим на хабе.", parent=self.manual_window)
            return
        try:
            self.manual_playback_events = self._load_recording_file(path)
        except (OSError, ValueError, UnicodeError) as error:
            messagebox.showerror("Запись не открыта", str(error), parent=self.manual_window)
            return
        self.manual_playback_index = 0
        self.manual_playback_started = time.perf_counter()
        self.manual_status_var.set("▶ Воспроизведение: " + os.path.basename(path))
        self._schedule_recording_event()

    def _schedule_recording_event(self):
        if self.manual_playback_index >= len(self.manual_playback_events):
            self.manual_playback_events = []
            self.manual_stop_all()
            self.manual_status_var.set("Воспроизведение завершено")
            return
        timestamp, command = self.manual_playback_events[self.manual_playback_index]
        elapsed = time.perf_counter() - self.manual_playback_started
        delay = max(0, int(timestamp - elapsed * 1000))
        self.manual_playback_after_id = self.root.after(delay, lambda cmd=command: self._send_playback_event(cmd))

    def _send_playback_event(self, command):
        self.manual_playback_after_id = None
        if command == self.manual_last_command:
            self.manual_playback_index += 1
            self._schedule_recording_event()
            return
        self.manual_waiting_for_ack = True
        self.manual_send_command(command)

    def _hide_manual_window(self):
        self.manual_keys.clear()
        if self.manual_ready:
            self._update_manual_motors()
        self.manual_window.withdraw()

    def _show_file_menu(self):
        self.root.update_idletasks()
        x = self.file_menu_button.winfo_rootx()
        y = self.file_menu_button.winfo_rooty() + self.file_menu_button.winfo_height()
        try:
            self.file_menu.tk_popup(x, y)
        finally:
            self.file_menu.grab_release()

    def _grid_dimensions(self):
        return self.grid_columns, self.grid_rows

    def _resize_grid(self):
        old_dimensions = self._grid_dimensions()
        try:
            columns = self.columns.get()
            rows = self.rows.get()
        except (tk.TclError, ValueError):
            self.columns.set(self.grid_columns)
            self.rows.set(self.grid_rows)
            messagebox.showerror(
                "Неверный размер сетки",
                "Введите целое число от 2 до 100 для ширины и высоты.",
            )
            return
        if not (2 <= columns <= 100 and 2 <= rows <= 100):
            self.columns.set(self.grid_columns)
            self.rows.set(self.grid_rows)
            messagebox.showerror(
                "Неверный размер сетки",
                "Ширина и высота сетки должны быть от 2 до 100 клеток.",
            )
            return

        self.columns.set(columns)
        self.rows.set(rows)
        self.grid_columns = columns
        self.grid_rows = rows
        if self.start and not self._in_bounds(*self.start):
            self.start = None
            self.route = []
            self.segments = []
            self.markers = {}
        else:
            valid_route = []
            for point in self.route:
                if not self._in_bounds(*point):
                    break
                valid_route.append(point)
            self.route = valid_route
            self.segments = self.segments[:max(0, len(self.route) - 1)]
            self.markers = {i: m for i, m in self.markers.items() if i < len(self.route)}
        if self.start and (not self.route or self.route[0] != self.start):
            self.route.insert(0, self.start)
        if old_dimensions != (columns, rows):
            self._mark_route_dirty()
        self._fit_grid_to_canvas()
        self._draw_grid()
        self._update_status()

    def _apply_map_settings(self):
        try:
            distance = self.cell_distance.get()
        except (tk.TclError, ValueError):
            messagebox.showerror("Шаг сетки", "Укажи целое число от 5 до 500 мм.")
            return
        if not 5 <= distance <= 500:
            messagebox.showerror("Шаг сетки", "Укажи целое число от 5 до 500 мм.")
            return
        self._resize_grid()
        self._mark_route_dirty()
        self._update_status()

    def _in_bounds(self, x, y):
        columns, rows = self._grid_dimensions()
        return 0 <= x < columns and 0 <= y < rows

    def _cell_at(self, event):
        x = int(self.canvas.canvasx(event.x) // self.cell_size)
        y = int(self.canvas.canvasy(event.y) // self.cell_size)
        return (x, y) if self._in_bounds(x, y) else None

    def _on_press(self, event):
        self.last_brush_cell = None
        self._apply_tool(self._cell_at(event))

    def _on_drag(self, event):
        cell = self._cell_at(event)
        if cell and self.tool.get() in ("brush", "erase"):
            self._apply_tool(cell)

    def _on_release(self, _event):
        self.last_brush_cell = None

    def _apply_tool(self, cell):
        if cell is None:
            return
        mode = self.tool.get()
        previous_start = self.start
        previous_route = list(self.route)
        if mode == "start":
            self.start = cell
            self.route = [cell]
            self.segments = []
            self.markers = {}
        elif mode in ("brush", "point"):
            if self.start is None:
                messagebox.showinfo("Старт робота", "Сначала задайте старт робота.")
                self.tool.set("start")
            elif not self.route:
                self.route = [self.start]
                self._append_segment(cell)
            elif mode == "point":
                self._append_segment(cell)
            elif cell != self.last_brush_cell:
                self._append_segment(cell)
                self.last_brush_cell = cell
        elif mode == "erase":
            if cell == self.start:
                self.start = None
                self.route = []
                self.segments = []
                self.markers = {}
            else:
                if cell in self.route:
                    self.route = self.route[: self.route.index(cell)]
                    self.segments = self.segments[:max(0, len(self.route) - 1)]
                    self.markers = {i: m for i, m in self.markers.items() if i < len(self.route)}
                if not self.route and self.start:
                    self.route = [self.start]
        elif mode == "select":
            self._select_route_point(cell)
        elif mode == "select":
            self._select_route_point(cell)
        if previous_start != self.start or previous_route != self.route:
            self._mark_route_dirty()
        self._draw_grid()
        self._update_status()

    def _append_segment(self, destination):
        if not self.route:
            return
        x, y = self.route[-1]
        end_x, end_y = destination
        while x != end_x:
            x += 1 if end_x > x else -1
            self.route.append((x, y))
            self.segments.append({"mode": "forward"})
        while y != end_y:
            y += 1 if end_y > y else -1
            self.route.append((x, y))
            self.segments.append({"mode": "forward"})
        self.selected_index = len(self.route) - 1

    def _step_route(self, direction):
        if not self.route:
            messagebox.showinfo("Старт робота", "Сначала задайте старт робота.")
            return
        relative_steps = {"forward": 0, "right": 1, "back": 2, "left": -1}
        if direction not in relative_steps:
            raise ValueError("Неизвестное направление шага: {}".format(direction))
        heading_index = route_end_heading_index(self.route, self.heading.get())
        map_direction = HEADINGS[
            (heading_index + relative_steps[direction]) % len(HEADINGS)
        ]
        dx, dy = HEADING_DELTAS[map_direction]
        x, y = self.route[-1]
        next_cell = (x + dx, y + dy)
        if not self._in_bounds(*next_cell):
            self.root.bell()
            return
        self.route.append(next_cell)
        self.segments.append({"mode": "forward"})
        self.selected_index = len(self.route) - 1
        self._mark_route_dirty()
        self._draw_grid()
        self._update_status()

    def _undo(self):
        if len(self.route) > 1:
            self.route.pop()
            if self.segments:
                self.segments.pop()
            self.markers.pop(len(self.route), None)
            self.selected_index = min(self.selected_index, len(self.route) - 1)
            self._mark_route_dirty()
        self._draw_grid()
        self._update_status()

    def _clear_route(self):
        new_route = [self.start] if self.start else []
        if new_route != self.route:
            self.route = new_route
            self.segments = []
            self.markers = {}
            self._mark_route_dirty()
        self._draw_grid()
        self._update_status()

    def _on_canvas_resize(self, _event):
        if not self._resize_redraw_pending:
            self._resize_redraw_pending = True
            self.root.after_idle(self._redraw_grid_after_resize)

    def _redraw_grid_after_resize(self):
        self._resize_redraw_pending = False
        if self._fit_grid_to_canvas():
            self._draw_grid()

    def _fit_grid_to_canvas(self):
        columns, rows = self._grid_dimensions()
        available_width = max(1, self.canvas.winfo_width() - 4)
        available_height = max(1, self.canvas.winfo_height() - 4)
        fit_cell_size = max(
            MIN_CELL_SIZE,
            min(available_width / float(columns), available_height / float(rows)),
        )
        new_cell_size = max(MIN_CELL_SIZE, fit_cell_size * getattr(self, "zoom", 1.0))
        if abs(new_cell_size - self.cell_size) > 0.5:
            self.cell_size = new_cell_size
            return True
        return False

    def _draw_grid(self):
        self.canvas.delete("all")
        columns, rows = self._grid_dimensions()
        cell_size = self.cell_size
        scale = cell_size / float(CELL_SIZE)
        self.canvas.configure(
            scrollregion=(0, 0, columns * cell_size, rows * cell_size)
        )
        for y in range(rows):
            for x in range(columns):
                left, top = x * cell_size, y * cell_size
                fill = COLORS["cell_alt"] if (x + y) % 2 else COLORS["cell"]
                self.canvas.create_rectangle(
                    left,
                    top,
                    left + cell_size,
                    top + cell_size,
                    fill=fill,
                    outline=COLORS["grid"],
                )
        for index in range(1, len(self.route)):
            previous = self.route[index - 1]
            current = self.route[index]
            self.canvas.create_line(
                previous[0] * cell_size + cell_size / 2,
                previous[1] * cell_size + cell_size / 2,
                current[0] * cell_size + cell_size / 2,
                current[1] * cell_size + cell_size / 2,
                fill=COLORS["accent"],
                width=max(2, 3 * scale),
                arrow=tk.LAST,
                arrowshape=(
                    max(3, 9 * scale),
                    max(4, 11 * scale),
                    max(2, 5 * scale),
                ),
            )
        for index, (x, y) in enumerate(self.route):
            cx, cy = x * cell_size + cell_size / 2, y * cell_size + cell_size / 2
            radius = max(4, cell_size * 0.16)
            self.canvas.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, fill=COLORS["accent"], outline=COLORS["background"], width=max(1, scale))
            self.canvas.create_text(cx, cy, text=str(index + 1), fill=COLORS["background"], font=("Segoe UI Semibold", max(6, int(8 * scale))))
        for index, entries in self.markers.items():
            if not 0 <= index < len(self.route):
                continue
            x, y = self.route[index]
            cx, cy = x * cell_size + cell_size / 2, y * cell_size + cell_size / 2
            label = next((entry.get("text") for entry in entries if entry.get("action") == "label"), None)
            marker_color = COLORS["green"] if label else COLORS["accent_hover"]
            radius = max(4, 7 * scale)
            self.canvas.create_oval(cx + radius, cy - radius, cx + 3 * radius, cy + radius, fill=marker_color, outline=COLORS["text"])
            marker_text = label[:8] if label else ("↻" if any(entry.get("action") == "turn" for entry in entries) else "■")
            self.canvas.create_text(cx + 2 * radius, cy, text=marker_text, fill=COLORS["text"], font=("Segoe UI", max(6, int(8 * scale))))
        if self.route and 0 <= self.selected_index < len(self.route):
            x, y = self.route[self.selected_index]
            inset = max(3, cell_size * 0.12)
            self.canvas.create_rectangle(x * cell_size + inset, y * cell_size + inset, (x + 1) * cell_size - inset, (y + 1) * cell_size - inset, outline=COLORS["accent"], width=max(2, int(2 * scale)), dash=(4, 2))
        if self.start:
            x, y = self.start
            center_x = x * cell_size + cell_size / 2
            center_y = y * cell_size + cell_size / 2
            robot_radius = min(cell_size * 0.32, 13 * scale)
            self.canvas.create_oval(
                center_x - robot_radius,
                center_y - robot_radius,
                center_x + robot_radius,
                center_y + robot_radius,
                fill=COLORS["robot"],
                outline=COLORS["text"],
                width=max(1, 2 * scale),
            )
            dx, dy = HEADING_DELTAS[self.heading.get()]
            self.canvas.create_line(
                center_x,
                center_y,
                center_x + dx * robot_radius * 0.85,
                center_y + dy * robot_radius * 0.85,
                fill=COLORS["background"],
                width=max(1, 3 * scale),
                arrow=tk.LAST,
            )

    def _update_status(self):
        if self.start is None:
            text = "Старт не задан"
        else:
            text = "Старт: {} · {} · точек: {}".format(
                self.start, self.heading.get(), len(self.route)
            )
        self.status.configure(text=text)
        if self.map_info is not None:
            self.map_info.configure(
                text="{} × {}  ·  шаг {} мм".format(*self._grid_dimensions(), self.cell_distance.get())
            )
        self._refresh_ble_controls()
        self._refresh_inspector()

    def _on_heading_change(self):
        self._mark_route_dirty()
        self._draw_grid()
        self._update_status()

    def _edit_route_point(self, event):
        cell = self._cell_at(event)
        if cell not in self.route:
            return
        index = self.route.index(cell)
        choice = simpledialog.askinteger(
            "Настроить точку",
            "0 — очистить метку, 1 — поворот на месте, 2 — остановка, 3 — подпись",
            parent=self.root, minvalue=0, maxvalue=3,
        )
        if choice is None:
            return
        if choice == 0:
            self.markers.pop(index, None)
        elif choice == 1:
            angle = simpledialog.askinteger("Поворот на месте", "Угол: 90 вправо, -90 влево", parent=self.root, initialvalue=90, minvalue=-360, maxvalue=360)
            if angle is None:
                return
            self.markers[index] = [{"action": "turn", "angle": angle}]
        elif choice == 2:
            self.markers[index] = [{"action": "stop"}]
        else:
            label = simpledialog.askstring("Метка маршрута", "Текст метки", parent=self.root)
            if label is None:
                return
            self.markers[index] = [{"action": "label", "text": label}]
        if index > 0:
            current = self.segments[index - 1]
            mode = simpledialog.askstring("Режим участка", "forward / backward / arc", parent=self.root, initialvalue=current.get("mode", "forward"))
            if mode in ("forward", "backward", "arc"):
                current["mode"] = mode
            speed = simpledialog.askinteger("Скорость участка", "Скорость мм/с (отмена — оставить)", parent=self.root, minvalue=10, maxvalue=1000)
            if speed is not None:
                current["speed"] = speed
        self._mark_route_dirty()
        self._draw_grid()

    def _edit_route_point(self, event):
        self._select_route_point(self._cell_at(event))

    def _select_route_point(self, cell):
        if cell is None or not self.route:
            return
        matches = [i for i, point in enumerate(self.route) if point == cell]
        self.selected_index = min(matches, key=lambda i: abs(i - self.selected_index)) if matches else min(range(len(self.route)), key=lambda i: abs(self.route[i][0] - cell[0]) + abs(self.route[i][1] - cell[1]))
        self._draw_grid()
        self._refresh_inspector()

    def _refresh_inspector(self):
        if not hasattr(self, "inspector_summary"):
            return
        if not self.route or not 0 <= self.selected_index < len(self.route):
            self.inspector_summary.configure(text="Выбери точку на карте")
            return
        index = self.selected_index
        self.inspector_summary.configure(text="Точка {}  ·  ({}, {})".format(index + 1, *self.route[index]))
        segment = self.segments[index - 1] if index > 0 and index - 1 < len(self.segments) else {}
        self.segment_mode_var.set({"forward": "Вперёд", "backward": "Задом", "arc": "Дуга (управляемый поворот)"}.get(segment.get("mode"), "Вперёд"))
        self.segment_speed_var.set(str(segment.get("speed", "")))
        self.segment_curve_var.set(str(segment.get("curve", 45)))
        entries = self.markers.get(index, [])
        marker = entries[0] if entries else {}
        self.marker_action_var.set({None: "Нет", "turn": "Поворот на месте", "stop": "Остановка", "label": "Метка"}.get(marker.get("action"), "Нет"))
        self.marker_angle_var.set(str(marker.get("angle", 90)))
        self.marker_text_var.set(str(marker.get("text", "")))

    def _apply_inspector_changes(self):
        if not self.route or not 0 <= self.selected_index < len(self.route):
            return
        index = self.selected_index
        if index > 0:
            segment = self.segments[index - 1]
            segment["mode"] = {"Вперёд": "forward", "Задом": "backward", "Дуга (управляемый поворот)": "arc"}.get(self.segment_mode_var.get(), "forward")
            speed_text = self.segment_speed_var.get().strip()
            if speed_text:
                try:
                    speed = int(speed_text)
                    if not 10 <= speed <= 1000:
                        raise ValueError
                except ValueError:
                    messagebox.showerror("Скорость", "Укажи целое число от 10 до 1000 мм/с.")
                    return
                segment["speed"] = speed
            else:
                segment.pop("speed", None)
            try:
                curve = int(self.segment_curve_var.get())
                if not 1 <= abs(curve) <= 360:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Угол дуги", "Укажи угол от -360 до 360 градусов, кроме нуля.")
                return
            segment["curve"] = curve
        action = self.marker_action_var.get()
        if action == "Нет":
            self.markers.pop(index, None)
        elif action == "Остановка":
            self.markers[index] = [{"action": "stop"}]
        elif action == "Поворот на месте":
            try:
                angle = int(self.marker_angle_var.get())
                if not -360 <= angle <= 360:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Поворот", "Укажи целый угол от -360 до 360 градусов.")
                return
            self.markers[index] = [{"action": "turn", "angle": angle}]
        else:
            label = self.marker_text_var.get().strip()
            if not label:
                messagebox.showerror("Метка", "Введи название метки.")
                return
            self.markers[index] = [{"action": "label", "text": label}]
        self._mark_route_dirty()
        self._draw_grid()

    def _on_canvas_wheel(self, event):
        self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")

    def _on_canvas_zoom(self, event):
        self.zoom = min(2.5, max(0.55, self.zoom * (1.1 if event.delta > 0 else 1 / 1.1)))
        self._fit_grid_to_canvas()
        self._draw_grid()

    def _toggle_connection(self):
        if self.ble_connected:
            self._disconnect_bluetooth()
        elif not self.ble_connecting and not self.ble_disconnecting:
            self._connect_bluetooth()

    def _open_bluetooth_menu(self):
        if self.ble_window is not None and self.ble_window.winfo_exists():
            self.ble_window.deiconify()
            self.ble_window.lift()
            return

        window = tk.Toplevel(self.root)
        window.title("Bluetooth — управление роботом")
        window.resizable(False, False)
        window.protocol("WM_DELETE_WINDOW", window.withdraw)
        self.ble_window = window

        panel = ttk.Frame(window, padding=12)
        panel.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            panel,
            text="Имя хаба или BLE-адрес (пусто — искать любой Pybricks-хаб)",
            wraplength=320,
        ).pack(anchor=tk.W)
        ttk.Entry(panel, textvariable=self.ble_device, width=42).pack(
            fill=tk.X, pady=(4, 8)
        )
        ttk.Checkbutton(
            panel,
            text="Поменять направление обоих моторов",
            variable=self.reverse_motor_directions,
        ).pack(anchor=tk.W, pady=(0, 6))

        self.ble_buttons = {
            "connect": ttk.Button(
                panel, text="Подключиться", command=self._connect_bluetooth
            ),
            "disconnect": ttk.Button(
                panel, text="Отключиться", command=self._disconnect_bluetooth
            ),
            "test": ttk.Button(
                panel, text="Тест движения", command=self._test_over_bluetooth
            ),
            "run": ttk.Button(
                panel,
                text="Запустить маршрут",
                command=self._run_route_over_bluetooth,
            ),
            "stop": ttk.Button(
                panel, text="Остановить робота", command=self._stop_bluetooth_run
            ),
        }
        for key in ("connect", "disconnect", "test", "run", "stop"):
            self.ble_buttons[key].pack(fill=tk.X, pady=2)

        self.ble_menu_status = ttk.Label(
            panel,
            text="Хаб не подключён.",
            wraplength=320,
            justify=tk.LEFT,
        )
        self.ble_menu_status.pack(anchor=tk.W, pady=(8, 0))
        ttk.Label(
            panel,
            text="Включи хаб и отключи его от других приложений перед поиском.\n\n"
            "Тест: 50 мм вперёд и назад на малой скорости. "
            "Маршрут отправляется сразу; для остановки используй кнопку "
            "«Остановить робота». Соединение остаётся активным.",
            wraplength=320,
        ).pack(anchor=tk.W, pady=(8, 0))
        self._refresh_ble_controls()

    def _set_ble_status(self, text):
        if self.ble_connected:
            text = "●  " + text
        elif self.ble_connecting:
            text = "◌  " + text
        else:
            text = "○  " + text
        self.ble_status.configure(text=text)
        if self.ble_menu_status is not None:
            try:
                self.ble_menu_status.configure(text=text)
            except tk.TclError:
                self.ble_menu_status = None

    def _refresh_ble_controls(self):
        if self.top_connect_button is not None:
            if self.ble_connected:
                self.top_connect_button.configure(
                    text="Отключить",
                    style="Disconnect.TButton",
                    state=(
                        tk.NORMAL
                        if not self.ble_disconnecting and not self.ble_closing
                        else tk.DISABLED
                    ),
                )
            elif self.ble_connecting or self.ble_disconnecting:
                self.top_connect_button.configure(
                    text="Подключение…", state=tk.DISABLED
                )
            else:
                self.top_connect_button.configure(
                    text="Подключить",
                    style="Connect.TButton",
                    state=tk.DISABLED if self.ble_closing else tk.NORMAL,
                )
        if self.top_run_button is not None:
            self.top_run_button.configure(
                text=(
                    "Загружаю маршрут…"
                    if self.ble_running and not self.ble_program_started
                    else "Команда выполняется"
                    if self.ble_running
                    else "▶  Запустить"
                ),
                state=tk.NORMAL
                if self.ble_connected
                and self.start is not None
                and len(self.route) > 1
                and not self.ble_running
                and not self.ble_disconnecting
                and not self.ble_closing
                else tk.DISABLED
            )
        if not self.ble_buttons:
            return
        connecting = self.ble_connecting or self.ble_disconnecting
        self.ble_buttons["connect"].configure(
            state=(
                tk.DISABLED
                if self.ble_connected or connecting or self.ble_closing
                else tk.NORMAL
            )
        )
        self.ble_buttons["disconnect"].configure(
            state=tk.NORMAL
            if self.ble_connected
            and not self.ble_disconnecting
            and not self.ble_closing
            else tk.DISABLED
        )
        self.ble_buttons["test"].configure(
            state=tk.NORMAL
            if self.ble_connected
            and not self.ble_running
            and not connecting
            and not self.ble_closing
            else tk.DISABLED
        )
        self.ble_buttons["run"].configure(
            text=(
                "Загрузка на хаб…"
                if self.ble_running and not self.ble_program_started
                else "Команда выполняется"
                if self.ble_running
                else "Запустить маршрут"
            ),
            state=tk.NORMAL
            if self.ble_connected
            and self.start is not None
            and len(self.route) > 1
            and not self.ble_running
            and not connecting
            and not self.ble_closing
            else tk.DISABLED
        )
        self.ble_buttons["stop"].configure(
            state=tk.NORMAL
            if self.ble_connected and self.ble_running and not self.ble_closing
            else tk.DISABLED
        )

    def _connect_bluetooth(self):
        if self.ble_connected or self.ble_connecting or self.ble_disconnecting:
            return
        self.ble_connecting = True
        self._set_ble_status("Запускаю Bluetooth и ищу Pybricks-хаб...")
        self._refresh_ble_controls()
        threading.Thread(
            target=self._connect_bluetooth_worker,
            args=(self.ble_device.get().strip(),),
            daemon=True,
        ).start()

    def _connect_bluetooth_worker(self, device_name):
        try:
            process = self.ble_process
            if process is None or process.poll() is not None:
                interpreter = self._find_pybricks_python()
                process = subprocess.Popen(
                    [interpreter, "-u", "-c", BLE_CLIENT_SCRIPT],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                    encoding="utf-8",
                    bufsize=1,
                    cwd=os.path.dirname(os.path.abspath(__file__)),
                )
                self.ble_process = process
                self.ble_stderr_lines = []
                self.ble_stderr_thread = threading.Thread(
                    target=self._read_ble_stderr,
                    args=(process,),
                    daemon=True,
                )
                self.ble_stderr_thread.start()
                threading.Thread(
                    target=self._read_ble_messages,
                    args=(process,),
                    daemon=True,
                ).start()
            self._send_ble_command(
                {"command": "connect", "name": device_name}, process
            )
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            self.root.after(
                0,
                lambda error=error: self._handle_ble_message(
                    {"event": "error", "operation": "connect", "message": str(error)}
                ),
            )

    def _send_ble_command(self, command, process=None):
        with self.ble_write_lock:
            process = process or self.ble_process
            if process is None or process.poll() is not None or process.stdin is None:
                raise RuntimeError("Bluetooth-клиент не запущен.")
            process.stdin.write(json.dumps(command) + "\n")
            process.stdin.flush()

    def _read_ble_messages(self, process):
        try:
            for line in process.stdout:
                try:
                    message = json.loads(line)
                except ValueError:
                    self.root.after(
                        0,
                        lambda text=line.strip(): self._handle_ble_message(
                            {
                                "event": "error",
                                "operation": "protocol",
                                "message": "Неожиданный ответ Bluetooth-клиента: "
                                + text[:500],
                            }
                        ),
                    )
                    continue
                self.root.after(
                    0,
                    lambda message=message: self._handle_ble_message(message),
                )
        finally:
            code = process.wait()
            if self.ble_stderr_thread is not None:
                self.ble_stderr_thread.join(timeout=2)
            stderr_text = "".join(self.ble_stderr_lines).strip()
            self.root.after(
                0,
                lambda: self._ble_process_exited(process, code, stderr_text),
            )

    def _read_ble_stderr(self, process):
        if process.stderr is None:
            return
        for line in process.stderr:
            self.ble_stderr_lines.append(line)

    def _ble_process_exited(self, process, return_code, stderr_text=""):
        if process is not self.ble_process:
            return
        self.ble_process = None
        self._clear_ble_run_timeout()
        was_connected = self.ble_connected
        self.ble_connected = False
        self.ble_connecting = False
        self.ble_disconnecting = False
        self.ble_running = False
        self._refresh_ble_controls()
        if was_connected or return_code:
            details = stderr_text[-2000:]
            message = "Bluetooth-клиент завершился (код {}).".format(return_code)
            if details:
                message += "\n\n" + details
            self._set_ble_status(
                message.splitlines()[0]
            )
            if return_code:
                messagebox.showerror("Сбой Bluetooth-клиента", message)

    def _handle_ble_message(self, message):
        event = message.get("event")
        if event == "connected":
            self.ble_connecting = False
            self.ble_connected = True
            self._set_ble_status(
                "Подключено: {} ({})".format(
                    message.get("name", "Pybricks-хаб"),
                    message.get("address", ""),
                )
            )
            if self.manual_start_when_connected:
                self.manual_start_when_connected = False
                self._start_manual_session()
        elif event == "disconnected":
            self._clear_ble_run_timeout()
            self.ble_connected = False
            self.ble_connecting = False
            self.ble_disconnecting = False
            self.ble_running = False
            self.ble_program_started = False
            self.manual_ready = False
            self.manual_setup_pending = False
            self._autosave_manual_recording()
            self._set_ble_status("Хаб отключён.")
        elif event == "link_lost":
            self._clear_ble_run_timeout()
            self.ble_connected = False
            self.ble_disconnecting = False
            self.ble_running = False
            self.ble_program_started = False
            self.manual_ready = False
            self.manual_setup_pending = False
            self._autosave_manual_recording()
            self._set_ble_status("Связь с хабом потеряна. Нажми «Подключиться».")
        elif event == "task_started":
            self.ble_running = True
            self._set_ble_status(
                "{}: подготовка и загрузка на хаб...".format(
                    message.get("name", "Команда")
                )
            )
        elif event == "task_progress":
            self._set_ble_status(
                "{}: {}".format(
                    message.get("name", "Команда"),
                    message.get("phase", "Выполнение..."),
                )
            )
        elif event == "program_started":
            self._clear_ble_run_timeout()
            self.ble_running = True
            self.ble_program_started = True
            self._set_ble_status(
                "{} запущена; Bluetooth подключён.".format(
                    message.get("name", "Программа")
                )
            )
            if self.manual_setup_pending and message.get("name") == "Ручное управление":
                self._ble_send_async({"command": "manual_setup"}, "manual_setup")
        elif event == "manual_ready":
            self.manual_setup_pending = False
            self.manual_ready = True
            self.manual_status_var.set("Ручной режим готов · привод A/E · навесной порт {}".format(self.manual_attachment_port.get()))
            self.manual_last_command = None
            self._manual_stop_all()
        elif event == "manual_ack":
            self.manual_status_var.set("Ручной режим активен · {}".format(message.get("value", "команда выполнена")))
            if self.manual_waiting_for_ack:
                self.manual_waiting_for_ack = False
                self.manual_playback_index += 1
                self._schedule_recording_event()
        elif event == "task_finished":
            self._clear_ble_run_timeout()
            self.ble_running = False
            self.ble_program_started = False
            saved_manual_recording = self.manual_recording
            self._autosave_manual_recording()
            if message.get("name") == "Ручное управление":
                self.manual_ready = False
                self.manual_setup_pending = False
                self.manual_motor_speeds = {port: 0 for port in "ABCDEF"}
                self._refresh_motor_visuals()
                if self.manual_window is not None and self.manual_window.winfo_exists() and not saved_manual_recording:
                    self.manual_status_var.set("Ручной режим остановлен")
            if message.get("error"):
                self._set_ble_status("Ошибка при выполнении команды.")
                messagebox.showerror(
                    "Ошибка Pybricks",
                    message.get("error", "Не удалось выполнить команду."),
                )
            elif message.get("stopped"):
                self._set_ble_status("Робот остановлен; Bluetooth подключён.")
            else:
                self._set_ble_status(
                    "{} завершено; Bluetooth подключён.".format(
                        message.get("name", "Команда")
                    )
                )
        elif event == "stop_requested":
            self._set_ble_status("Останавливаю робота...")
        elif event == "error":
            operation = message.get("operation")
            if operation == "connect":
                self.ble_connecting = False
                if self.manual_start_when_connected:
                    self.manual_start_when_connected = False
                    self.manual_status_var.set("Не удалось подключиться к хабу")
            elif operation == "disconnect":
                self.ble_disconnecting = False
            elif operation == "run":
                self._clear_ble_run_timeout()
                self.ble_running = False
                self.ble_program_started = False
            elif operation in ("manual", "manual_setup"):
                self.manual_status_var.set("Ошибка ручного режима: " + message.get("message", ""))
                if operation == "manual_setup":
                    self.manual_setup_pending = False
                    self.manual_ready = False
                    self._ble_send_async({"command": "stop"}, "stop")
            error_text = message.get("message", "Неизвестная ошибка Bluetooth.")
            self._set_ble_status("Ошибка: " + error_text)
            messagebox.showerror("Ошибка Bluetooth", error_text)
        self._refresh_ble_controls()

    def _ble_send_async(self, command, error_operation):
        def send_command():
            try:
                self._send_ble_command(command)
            except (OSError, RuntimeError, subprocess.SubprocessError) as error:
                self.root.after(
                    0,
                    lambda error=error: self._handle_ble_message(
                        {
                            "event": "error",
                            "operation": error_operation,
                            "message": str(error),
                        }
                    ),
                )

        threading.Thread(target=send_command, daemon=True).start()

    def _disconnect_bluetooth(self):
        if not self.ble_connected or self.ble_disconnecting:
            return
        if self.ble_running and not messagebox.askyesno(
            "Отключить хаб",
            "Робот сейчас выполняет команду. Перед отключением он будет остановлен. "
            "Продолжить?",
        ):
            return
        self.ble_disconnecting = True
        self._set_ble_status("Останавливаю робота и отключаю хаб...")
        self._refresh_ble_controls()
        self._ble_send_async({"command": "disconnect"}, "disconnect")

    def _test_over_bluetooth(self):
        if not self.ble_connected or self.ble_running:
            return
        if not messagebox.askyesno(
            "Тест моторов",
            "Робот проверит движение по прямой: проедет вперёд и назад "
            "по 50 мм на малой скорости. Поворотов в тесте нет.\n\n"
            "Поставь его на свободное место. Продолжить?",
        ):
            return
        self._run_ble_program(
            generate_pybricks_test_program(self.reverse_motor_directions.get()),
            "Тест моторов",
        )

    def _run_route_over_bluetooth(self):
        if not self.ble_connected or self.ble_running:
            return
        if self.start is None or len(self.route) < 2:
            messagebox.showerror(
                "Нет маршрута",
                "Добавь хотя бы один шаг после стартовой точки.",
            )
            return
        self._run_ble_program(
            generate_pybricks_program(
                self.route,
                self.heading.get(),
                self.reverse_motor_directions.get(),
                cell_distance_mm=self.cell_distance.get(),
                segments=self.segments,
                markers=self.markers,
            ),
            "Маршрут",
        )

    def _run_ble_program(self, program, task_name):
        self.ble_running = True
        self._set_ble_status(task_name + " отправляется на хаб...")
        self._refresh_ble_controls()
        self._clear_ble_run_timeout()
        self.ble_run_timeout_id = self.root.after(
            PROGRAM_RUN_TIMEOUT_SECONDS * 1000,
            self._on_ble_run_timeout,
        )
        self._ble_send_async(
            {"command": "run", "name": task_name, "source": program}, "run"
        )

    def _clear_ble_run_timeout(self):
        if self.ble_run_timeout_id is not None:
            try:
                self.root.after_cancel(self.ble_run_timeout_id)
            except tk.TclError:
                pass
            self.ble_run_timeout_id = None

    def _on_ble_run_timeout(self):
        self.ble_run_timeout_id = None
        if not self.ble_running or self.ble_program_started:
            return

        message = (
            "Хаб не подтвердил запуск за {} секунд. Отправляю команду "
            "остановки и жду ответа. Не закрывай окно, пока не появится "
            "подтверждение остановки.".format(
                PROGRAM_RUN_TIMEOUT_SECONDS
            )
        )
        self._set_ble_status("Ошибка: " + message.splitlines()[0])
        self._refresh_ble_controls()
        self._ble_send_async({"command": "stop"}, "stop")
        messagebox.showwarning("Запуск не подтверждён", message)

    def _stop_bluetooth_run(self):
        if not self.ble_connected or not self.ble_running:
            return
        self._set_ble_status("Останавливаю робота...")
        self._ble_send_async({"command": "stop"}, "stop")

    def _find_pybricks_python(self):
        candidates = [sys.executable]
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            candidates.extend(
                glob.glob(
                    os.path.join(local_app_data, "Python", "pythoncore-*", "python.exe")
                )
            )
            candidates.extend(
                glob.glob(
                    os.path.join(
                        local_app_data, "Programs", "Python", "Python*", "python.exe"
                    )
                )
            )

        checked = set()
        for interpreter in candidates:
            interpreter = os.path.abspath(interpreter)
            if interpreter in checked:
                continue
            checked.add(interpreter)
            try:
                result = subprocess.run(
                    [interpreter, "-m", "pybricksdev", "--version"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True,
                    timeout=8,
                )
            except (OSError, subprocess.SubprocessError):
                continue
            if result.returncode == 0:
                return interpreter

        raise RuntimeError(
            "Не найден Python 3.10+ с установленным pybricksdev. "
            "Установи pybricksdev для Python 3.10 или новее, затем перезапусти "
            "редактор."
        )

    def _on_close(self):
        if self.ble_closing:
            return
        if self.ble_running and not messagebox.askyesno(
            "Остановить робота и закрыть?",
            "Маршрут ещё загружается или выполняется. При закрытии я отправлю "
            "команду остановки и дождусь ответа хаба. Это может занять до "
            "{} секунд.\n\nЗакрыть редактор?".format(
                PROGRAM_DOWNLOAD_TIMEOUT_SECONDS + 20
            ),
        ):
            return

        process = self.ble_process
        if process is None or process.poll() is not None:
            self.root.destroy()
            return

        self.ble_closing = True
        self._set_ble_status("Останавливаю робота и жду отключения хаба...")
        self._refresh_ble_controls()

        def shutdown():
            try:
                self._send_ble_command({"command": "shutdown"}, process)
                process.wait(timeout=PROGRAM_DOWNLOAD_TIMEOUT_SECONDS + 20)
            except subprocess.TimeoutExpired:
                self.root.after(
                    0,
                    lambda: self._on_close_failed(
                        process,
                        "Хаб не подтвердил остановку за отведённое время. "
                        "Окно оставлено открытым, чтобы можно было повторить "
                        "остановку или отключение.",
                    ),
                )
            except (OSError, RuntimeError, subprocess.SubprocessError) as error:
                if process.poll() is not None:
                    self.root.after(0, self.root.destroy)
                else:
                    self.root.after(
                        0,
                        lambda error=error: self._on_close_failed(
                            process, "Не удалось безопасно закрыть соединение: "
                            + str(error)
                        ),
                    )
            else:
                self.root.after(0, self.root.destroy)

        threading.Thread(target=shutdown, daemon=True).start()

    def _on_close_failed(self, process, message):
        if process is not self.ble_process or process.poll() is not None:
            self.root.destroy()
            return
        self.ble_closing = False
        self._set_ble_status("Ошибка: " + message.splitlines()[0])
        self._refresh_ble_controls()
        messagebox.showerror("Хаб ещё подключён", message)

    def _export_pybricks(self):
        if self.start is None or not self.route:
            messagebox.showerror(
                "Нельзя создать программу",
                "Сначала задайте старт робота и нарисуйте маршрут.",
            )
            return
        path = filedialog.asksaveasfilename(
            title="Создать программу Pybricks",
            defaultextension=".py",
            initialfile="robot_route.py",
            filetypes=(("Программа Python", "*.py"), ("Все файлы", "*.*")),
        )
        if not path:
            return
        program = generate_pybricks_program(
            self.route, self.heading.get(), self.reverse_motor_directions.get(),
            cell_distance_mm=self.cell_distance.get(), segments=self.segments, markers=self.markers,
        )
        try:
            with open(path, "w", encoding="utf-8") as program_file:
                program_file.write(program)
        except OSError as error:
            messagebox.showerror("Ошибка создания программы", str(error))
            return
        messagebox.showinfo(
            "Программа готова",
            "Pybricks-программа сохранена.\n"
            "Открой её в Pybricks Code, загрузи на хаб и запусти.\n\n"
            "Перед запуском поставь робота в стартовую клетку и "
            "направь его так же, как на карте.",
        )

    def _save(self):
        if self.route_file_path is None:
            self._save_as()
            return
        self._write_route(self.route_file_path)

    def _save_as(self):
        path = filedialog.asksaveasfilename(
            title="Сохранить маршрут",
            defaultextension=".json",
            initialfile="route.json",
            filetypes=(("Файл маршрута", "*.json"), ("Все файлы", "*.*")),
        )
        if not path:
            return
        if self._write_route(path):
            self.route_file_path = path
            self.route_dirty = False
            self._update_window_title()

    def _write_route(self, path):
        if self.start is None or not self.route:
            messagebox.showerror(
                "Нельзя сохранить",
                "Сначала поставь старт робота на карту.",
            )
            return False
        columns, rows = self._grid_dimensions()
        data = {
            "version": 2,
            "grid": {"columns": columns, "rows": rows, "cell_mm": self.cell_distance.get()},
            "start": {
                "x": self.start[0],
                "y": self.start[1],
                "heading": self.heading.get(),
            },
            "route": [{"x": x, "y": y} for x, y in self.route],
            "segments": self.segments,
            "markers": {str(index): entries for index, entries in self.markers.items()},
        }
        try:
            with open(path, "w", encoding="utf-8") as route_file:
                json.dump(data, route_file, ensure_ascii=False, indent=2)
        except OSError as error:
            messagebox.showerror("Ошибка сохранения", str(error))
            return False
        self.route_dirty = False
        self._update_window_title()
        return True

    def _new_route(self):
        if not self._confirm_discard_changes("Создать новую карту?"):
            return
        self.start = None
        self.route = []
        self.segments = []
        self.markers = {}
        self.route_file_path = None
        self.route_dirty = False
        self._update_window_title()
        self._draw_grid()
        self._update_status()

    def _confirm_discard_changes(self, action):
        if not self.route_dirty:
            return True
        return messagebox.askyesno(
            action,
            "Есть несохранённые изменения. Продолжить без сохранения?",
        )

    def _mark_route_dirty(self):
        self.route_dirty = True
        self._update_window_title()

    def _update_window_title(self):
        if hasattr(self, "project_title"):
            project = os.path.basename(self.route_file_path) if self.route_file_path else "Новый маршрут"
            self.project_title.configure(text=("●  " if self.route_dirty else "") + project)
        if self.route_file_path:
            name = os.path.basename(self.route_file_path)
            self.root.title(
                "Pybricks — {}{}".format("*" if self.route_dirty else "", name)
            )
        else:
            self.root.title(
                "Pybricks — редактор маршрута{}".format(
                    "*" if self.route_dirty else ""
                )
            )

    def _load(self):
        path = filedialog.askopenfilename(
            title="Открыть маршрут",
            filetypes=(("Файл маршрута", "*.json"), ("Все файлы", "*.*")),
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as route_file:
                data = json.load(route_file)
            columns, rows, start, heading, route = validate_route_data(data)
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
        ) as error:
            messagebox.showerror("Ошибка маршрута", str(error))
            return

        if not self._confirm_discard_changes("Открыть маршрут"):
            return
        self.columns.set(columns)
        self.rows.set(rows)
        self.grid_columns = columns
        self.grid_rows = rows
        self._fit_grid_to_canvas()
        self.start = start
        self.heading.set(heading)
        self.route = route
        self.segments = data.get("segments", [{"mode": "forward"} for _ in route[1:]])
        self.markers = {int(index): entries for index, entries in data.get("markers", {}).items()}
        self.cell_distance.set(data.get("grid", {}).get("cell_mm", CELL_DISTANCE_MM))
        self.route_file_path = path
        self.route_dirty = False
        self._update_window_title()
        self._draw_grid()
        self._update_status()


def main():
    root = tk.Tk()
    RouteEditor(root)
    root.mainloop()


if __name__ == "__main__":
    main()
