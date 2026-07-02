from __future__ import annotations

import queue
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import __version__
from .app_config import AppSettings, load_app_settings, save_app_settings
from .dat_parser import parse_interface_file
from .input_logic import (
    DecodedInputSignal,
    build_input_test_plan_text,
    decode_input_update_with_fallback,
    format_ver3_decoded_lines,
    input_signals_for_panels,
    parse_ver3_word_values,
    signal_flags_text,
)
from .light_logic import (
    INTENSITY_MODE_LABELS,
    INTENSITY_MODE_RAW,
    LIGHT_FILTER_ALL,
    LIGHT_FILTER_LABELS,
    PanelFamilyLightTest,
    PanelLightTest,
    WordLightGroup,
    build_command_plan_text,
    command_target_label,
    panel_family_name,
    signal_command_label,
    signal_off_command,
    signal_on_command,
    test_target_includes_panel,
)
from .models import AircraftDefinition, PanelDefinition
from .panel_detail import build_panel_capability_detail_text
from .panel_assignment import (
    address_assignment_panels,
    panel_assignment_search_text,
    panel_side_label,
)
from .output_logic import (
    OUTPUT_CATEGORY_FILTER_LABELS,
    OUTPUT_CATEGORY_DISPLAY,
    OUTPUT_FILTER_ALL,
    build_display_sweep_frames,
    build_special_output_plan_text,
    display_word_groups,
    normalize_display_sweep_characters,
    special_output_signals_for_panels,
)
from .panel_inventory import PanelCapabilityStats, build_panel_inventory
from .pre_hardware import build_pre_hardware_checklist_text
from .readiness import READINESS_INFO, READINESS_OK, READINESS_WARNING, ReadinessCheck, build_operational_status_text
from .report_export import write_report_csvs
from .serial_client import (
    BoardInfo,
    NEWLINES,
    SerialConnection,
    SerialDependencyError,
    SerialLineBuffer,
    line_payload,
    list_serial_ports,
    pyserial_available,
)
from .serial_diagnostics import (
    SERIAL_TRACE_MAX_EVENTS,
    SerialTraceEvent,
    make_serial_trace_event,
    trim_serial_trace_events,
    write_serial_trace_log,
)
from .session_results import (
    PanelResult,
    RESULT_FILTER_ALL,
    RESULT_FILTER_OPTIONS,
    RESULT_FILTER_PENDING,
    RESULT_FAIL,
    RESULT_NA,
    RESULT_NOT_TESTED,
    RESULT_OK,
    RESULT_OPTIONS,
    make_panel_result,
    result_matches_filter,
    should_keep_result,
    summarize_family_result,
)
from .session_store import TestSession, load_test_session, save_test_session
from .validation import ValidationReport, validate_aircraft_definition


APP_BG = "#eef2f6"
SURFACE = "#ffffff"
BORDER = "#d6dde6"
TEXT = "#17202a"
MUTED = "#5d6d7e"
PRIMARY = "#2457a6"
PRIMARY_ACTIVE = "#1f4b8f"
DANGER = "#9f2d2d"
DANGER_ACTIVE = "#842424"
WARNING_BG = "#fff5d6"
WARNING_TEXT = "#694b00"
LOG_BG = "#101828"
LOG_TEXT = "#dbe7ff"
FONT = "Segoe UI"
COMMAND_STATUS_OK = "OK"
COMMAND_STATUS_NO_RESPONSE = "No response"
COMMAND_STATUS_STARTED = "Started"


class InterfaceTesterApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"Interface Tester v{__version__}")
        self.geometry("1180x760")
        self.minsize(980, 620)

        self.settings = load_app_settings()
        saved_definition_dir = Path(self.settings.last_definition_dir) if self.settings.last_definition_dir else None
        self.definition_dir = saved_definition_dir if saved_definition_dir and saved_definition_dir.exists() else find_definition_dir()
        self.current_aircraft: AircraftDefinition | None = None
        self.current_panel_families: list[PanelFamilyLightTest] = []
        self.current_family_stats: dict[str, PanelCapabilityStats] = {}
        self.current_validation_report: ValidationReport | None = None
        self.tree_item_to_family: dict[str, str] = {}
        self.light_item_to_commands: dict[str, tuple[str, str, str]] = {}
        self.light_item_to_group: dict[str, WordLightGroup] = {}
        self.signal_item_to_commands: dict[str, tuple[str, str, str]] = {}
        self.port_display_to_device: dict[str, str] = {}
        self.serial_connection = SerialConnection()
        self.serial_lock = threading.Lock()
        self.serial_trace_lock = threading.Lock()
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.input_view_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.input_command_queue: queue.Queue[str] = queue.Queue()
        self.command_history: list[dict[str, str]] = []
        self.serial_trace_events: list[SerialTraceEvent] = []
        self.serial_trace_discarded_count = 0
        self.serial_trace_limit_notice_shown = False
        self.input_word_values: dict[int, int] = {}
        self.input_history: list[dict[str, str]] = []
        self.panel_results: dict[str, PanelResult] = {}
        self.current_result_key: str | None = None
        self.current_result_label = ""
        self.detected_panel: PanelDefinition | None = None
        self.active_board_address: int | None = None
        self.pending_address_assignment: PanelDefinition | None = None
        self.address_assignment_running = False

        self.dat_path_var = tk.StringVar(value="No .dat file loaded")
        self.validation_summary_var = tk.StringVar(value="Validation: no file loaded")
        self.port_var = tk.StringVar()
        self.baud_var = tk.StringVar(value=self.settings.baud_rate or "115200")
        self.newline_var = tk.StringVar(value=self.settings.newline if self.settings.newline in NEWLINES else "CR")
        self.search_var = tk.StringVar()
        self.result_filter_var = tk.StringVar(value=RESULT_FILTER_ALL)
        self.response_wait_var = tk.DoubleVar(value=max(0.05, self.settings.response_wait_seconds))
        self.response_quiet_var = tk.DoubleVar(value=max(0.0, self.settings.response_quiet_seconds))
        self.command_delay_var = tk.DoubleVar(value=max(0.0, self.settings.command_delay_seconds))
        self.diagnostic_seconds_var = tk.DoubleVar(value=max(0.1, self.settings.diagnostic_seconds))
        self.duration_var = tk.DoubleVar(value=max(0.1, self.settings.duration_seconds))
        self.detected_var = tk.StringVar(value="Not detected")
        self.board_info_var = tk.StringVar(value="Board: no information")
        self.status_var = tk.StringVar(value="Disconnected")
        self.connection_status_text = "Disconnected"
        self.custom_command_var = tk.StringVar()
        self.command_preview_var = tk.StringVar(value="Select a panel to view ON/OFF commands.")
        self.signal_preview_var = tk.StringVar(value="Select a word to view its signals.")
        self.display_word_var = tk.StringVar(value=self.settings.display_word or "38")
        self.display_text_var = tk.StringVar(value=self.settings.display_text or "105435")
        self.display_sweep_var = tk.StringVar(value="0123456789")
        self.display_step_var = tk.DoubleVar(value=0.6)
        self.display_restore_var = tk.BooleanVar(value=True)
        self.display_test_summary_var = tk.StringVar(value="Select or detect a panel with display fields.")
        self.report_result_var = tk.StringVar(value=RESULT_NOT_TESTED)
        self.report_comment_var = tk.StringVar()
        self.report_summary_var = tk.StringVar(value="Results: no panels loaded")
        self.checklist_summary_var = tk.StringVar(value="Checklist: load a .dat file to begin.")
        self.intensity_mode_var = tk.StringVar(
            value=INTENSITY_MODE_LABELS.get(self.settings.intensity_mode, INTENSITY_MODE_LABELS[INTENSITY_MODE_RAW])
        )
        self.light_filter_var = tk.StringVar(
            value=LIGHT_FILTER_LABELS.get(self.settings.light_filter, LIGHT_FILTER_LABELS[LIGHT_FILTER_ALL])
        )
        self.output_filter_var = tk.StringVar(
            value=OUTPUT_CATEGORY_FILTER_LABELS.get(self.settings.output_filter, OUTPUT_CATEGORY_FILTER_LABELS[OUTPUT_FILTER_ALL])
        )
        self.auto_off_var = tk.BooleanVar(value=self.settings.auto_off)
        self.direct_mode_confirmed = False
        self.auto_test_stop_event = threading.Event()
        self.auto_test_running = False
        self.input_monitor_stop_event = threading.Event()
        self.input_monitor_running = False
        self.display_test_stop_event = threading.Event()
        self.display_test_running = False

        self._configure_style()
        self._build_ui()
        self._bind_events()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self._load_initial_data()
        self.after(100, self._drain_log_queue)

    def _configure_style(self) -> None:
        self.configure(background=APP_BG)
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(".", font=(FONT, 10), foreground=TEXT)
        style.configure("TFrame", background=APP_BG)
        style.configure("Card.TFrame", background=SURFACE)
        style.configure("TLabel", background=SURFACE, foreground=TEXT)
        style.configure("Muted.TLabel", background=SURFACE, foreground=MUTED)
        style.configure("Status.TFrame", background=SURFACE, relief="solid", borderwidth=1)
        style.configure("Status.TLabel", background=SURFACE, foreground=MUTED, padding=(8, 4))
        style.configure("Warning.TLabel", background=WARNING_BG, foreground=WARNING_TEXT, padding=(8, 5))
        style.configure(
            "Section.TLabelframe",
            background=SURFACE,
            bordercolor=BORDER,
            borderwidth=1,
            relief="solid",
        )
        style.configure(
            "Section.TLabelframe.Label",
            background=APP_BG,
            foreground=MUTED,
            font=(FONT, 9, "bold"),
        )
        style.configure("TEntry", fieldbackground=SURFACE, bordercolor=BORDER, padding=4)
        style.configure("TCombobox", fieldbackground=SURFACE, bordercolor=BORDER, padding=4)
        style.configure("TSpinbox", fieldbackground=SURFACE, bordercolor=BORDER, padding=4)
        style.configure("TButton", padding=(12, 6), borderwidth=0)
        style.configure("Primary.TButton", background=PRIMARY, foreground="#ffffff")
        style.map("Primary.TButton", background=[("active", PRIMARY_ACTIVE), ("pressed", PRIMARY_ACTIVE)])
        style.configure("Danger.TButton", background=DANGER, foreground="#ffffff")
        style.map("Danger.TButton", background=[("active", DANGER_ACTIVE), ("pressed", DANGER_ACTIVE)])
        style.configure("Secondary.TButton", background="#e6ebf2", foreground=TEXT)
        style.map("Secondary.TButton", background=[("active", "#d8e0ea"), ("pressed", "#d8e0ea")])
        style.configure(
            "Treeview",
            background=SURFACE,
            fieldbackground=SURFACE,
            foreground=TEXT,
            rowheight=28,
            borderwidth=0,
            font=(FONT, 9),
        )
        style.configure(
            "Treeview.Heading",
            background="#e8edf5",
            foreground=MUTED,
            relief="flat",
            font=(FONT, 9, "bold"),
            padding=(6, 6),
        )
        style.map("Treeview", background=[("selected", PRIMARY)], foreground=[("selected", "#ffffff")])

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        file_bar = ttk.LabelFrame(self, text="Interface definition", padding=12, style="Section.TLabelframe")
        file_bar.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))
        file_bar.columnconfigure(1, weight=1)

        ttk.Label(file_bar, text=".dat file").grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Entry(file_bar, textvariable=self.dat_path_var, state="readonly").grid(row=0, column=1, sticky="ew", padx=(0, 8))
        ttk.Button(file_bar, text="Load .dat", command=self.choose_dat_file, style="Primary.TButton").grid(row=0, column=2)
        ttk.Label(file_bar, textvariable=self.validation_summary_var, style="Muted.TLabel").grid(row=1, column=0, columnspan=3, sticky="ew", pady=(8, 0))

        serial_bar = ttk.LabelFrame(self, text="Serial connection", padding=12, style="Section.TLabelframe")
        serial_bar.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))
        serial_bar.columnconfigure(1, weight=1)

        ttk.Label(serial_bar, text="Port").grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.port_combo = ttk.Combobox(serial_bar, textvariable=self.port_var, state="readonly")
        self.port_combo.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        ttk.Button(serial_bar, text="Refresh", command=self.refresh_ports, style="Secondary.TButton").grid(row=0, column=2, padx=(0, 14))

        ttk.Label(serial_bar, text="Baud").grid(row=0, column=3, sticky="w", padx=(0, 6))
        ttk.Entry(serial_bar, textvariable=self.baud_var, width=10).grid(row=0, column=4, sticky="w", padx=(0, 14))

        ttk.Label(serial_bar, text="Fin").grid(row=0, column=5, sticky="w", padx=(0, 6))
        ttk.Combobox(
            serial_bar,
            textvariable=self.newline_var,
            values=list(NEWLINES),
            state="readonly",
            width=7,
        ).grid(row=0, column=6, sticky="w", padx=(0, 14))

        self.connect_button = ttk.Button(serial_bar, text="Connect", command=self.toggle_connection, style="Primary.TButton")
        self.connect_button.grid(row=0, column=7, padx=(0, 8))
        ttk.Button(serial_bar, text="Info", command=self.request_info, style="Secondary.TButton").grid(row=0, column=8)
        ttk.Button(serial_bar, text="?", command=self.request_help, style="Secondary.TButton").grid(row=0, column=9, padx=(8, 0))

        self.main_notebook = ttk.Notebook(self)
        self.main_notebook.grid(row=3, column=0, sticky="nsew", padx=12, pady=(0, 8))

        lights_tab = ttk.Frame(self.main_notebook, padding=8)
        inputs_tab = ttk.Frame(self.main_notebook, padding=8)
        outputs_tab = ttk.Frame(self.main_notebook, padding=8)
        report_tab = ttk.Frame(self.main_notebook, padding=8)
        console_tab = ttk.Frame(self.main_notebook, padding=8)
        self.main_notebook.add(lights_tab, text="Lights")
        self.main_notebook.add(inputs_tab, text="Inputs")
        self.main_notebook.add(outputs_tab, text="Outputs")
        self.main_notebook.add(report_tab, text="Report")
        self.main_notebook.add(console_tab, text="Terminal")
        for tab in (lights_tab, inputs_tab, outputs_tab, report_tab, console_tab):
            tab.columnconfigure(0, weight=1)
        lights_tab.rowconfigure(2, weight=1)
        inputs_tab.rowconfigure(1, weight=2, minsize=170)
        inputs_tab.rowconfigure(2, weight=1, minsize=120)
        console_tab.rowconfigure(1, weight=1)

        diagnostic_bar = ttk.LabelFrame(console_tab, text="Serial diagnostics", padding=12, style="Section.TLabelframe")
        diagnostic_bar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        diagnostic_bar.columnconfigure(7, weight=1)

        ttk.Label(diagnostic_bar, text="Seconds").grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Spinbox(
            diagnostic_bar,
            textvariable=self.diagnostic_seconds_var,
            from_=0.1,
            to=60.0,
            increment=0.1,
            width=7,
        ).grid(row=0, column=1, sticky="w", padx=(0, 10))
        ttk.Button(diagnostic_bar, text="Read raw", command=self.read_raw_serial_window, style="Secondary.TButton").grid(row=0, column=2, padx=(0, 8))
        ttk.Button(diagnostic_bar, text="Save serial log", command=self.save_serial_trace_log, style="Secondary.TButton").grid(row=0, column=3, padx=(0, 8))
        ttk.Button(diagnostic_bar, text="Clear serial log", command=self.clear_serial_trace_log, style="Secondary.TButton").grid(row=0, column=4, padx=(0, 12))
        ttk.Label(
            diagnostic_bar,
            text="Captures TX/RX with timestamp, escaped text, and hex.",
            style="Muted.TLabel",
        ).grid(row=0, column=5, columnspan=3, sticky="w")

        ttk.Label(diagnostic_bar, text="Resp. s").grid(row=1, column=0, sticky="w", padx=(0, 6), pady=(8, 0))
        ttk.Spinbox(
            diagnostic_bar,
            textvariable=self.response_wait_var,
            from_=0.05,
            to=30.0,
            increment=0.05,
            width=7,
        ).grid(row=1, column=1, sticky="w", padx=(0, 10), pady=(8, 0))
        ttk.Label(diagnostic_bar, text="Quiet time (s)").grid(row=1, column=2, sticky="w", padx=(0, 6), pady=(8, 0))
        ttk.Spinbox(
            diagnostic_bar,
            textvariable=self.response_quiet_var,
            from_=0.0,
            to=10.0,
            increment=0.05,
            width=7,
        ).grid(row=1, column=3, sticky="w", padx=(0, 10), pady=(8, 0))
        ttk.Label(diagnostic_bar, text="Command delay (s)").grid(row=1, column=4, sticky="w", padx=(0, 6), pady=(8, 0))
        ttk.Spinbox(
            diagnostic_bar,
            textvariable=self.command_delay_var,
            from_=0.0,
            to=5.0,
            increment=0.01,
            width=7,
        ).grid(row=1, column=5, sticky="w", padx=(0, 12), pady=(8, 0))
        ttk.Label(
            diagnostic_bar,
            text="Timings used by Info, ?, commands, and tests.",
            style="Muted.TLabel",
        ).grid(row=1, column=6, columnspan=2, sticky="w", pady=(8, 0))

        panel_bar = ttk.LabelFrame(lights_tab, text="Panel", padding=12, style="Section.TLabelframe")
        panel_bar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        panel_bar.columnconfigure(1, weight=1)

        ttk.Label(panel_bar, text="Search").grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Entry(panel_bar, textvariable=self.search_var).grid(row=0, column=1, sticky="ew", padx=(0, 14))

        ttk.Label(panel_bar, text="Status").grid(row=0, column=2, sticky="w", padx=(0, 6))
        ttk.Combobox(
            panel_bar,
            textvariable=self.result_filter_var,
            values=RESULT_FILTER_OPTIONS,
            state="readonly",
            width=13,
        ).grid(row=0, column=3, sticky="w", padx=(0, 14))
        ttk.Button(panel_bar, text="Next pending", command=self.select_next_pending_panel, style="Secondary.TButton").grid(row=0, column=4, sticky="w")

        ttk.Label(panel_bar, text="Detected").grid(row=1, column=0, sticky="w", padx=(0, 6), pady=(8, 0))
        ttk.Label(panel_bar, textvariable=self.detected_var, style="Muted.TLabel").grid(row=1, column=1, sticky="w", pady=(8, 0))
        ttk.Label(panel_bar, textvariable=self.board_info_var, style="Muted.TLabel").grid(row=1, column=2, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Button(panel_bar, text="Set detected", command=self.set_detected_from_selection, style="Secondary.TButton").grid(row=1, column=4, sticky="e", pady=(8, 0))
        ttk.Button(panel_bar, text="Panel details", command=self.show_selected_panel_detail, style="Secondary.TButton").grid(row=1, column=5, sticky="e", padx=(8, 0), pady=(8, 0))

        button_bar = ttk.LabelFrame(lights_tab, text="Light test", padding=12, style="Section.TLabelframe")
        button_bar.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        button_bar.columnconfigure(1, weight=1)

        ttk.Button(button_bar, text="Turn lights on", command=self.turn_lights_on, style="Primary.TButton").grid(row=0, column=0, padx=(0, 8))
        ttk.Button(button_bar, text="Turn lights off", command=self.turn_lights_off, style="Secondary.TButton").grid(row=0, column=1, padx=(0, 8))
        self.auto_test_button = ttk.Button(button_bar, text="Automatic test", command=self.run_auto_test, style="Primary.TButton")
        self.auto_test_button.grid(row=0, column=2, padx=(0, 14))
        ttk.Label(button_bar, text="Type").grid(row=0, column=3, padx=(0, 6))
        ttk.Combobox(
            button_bar,
            textvariable=self.light_filter_var,
            values=list(LIGHT_FILTER_LABELS.values()),
            state="readonly",
            width=12,
        ).grid(row=0, column=4, padx=(0, 14))
        ttk.Label(button_bar, text="Intensity").grid(row=0, column=5, padx=(0, 6))
        ttk.Combobox(
            button_bar,
            textvariable=self.intensity_mode_var,
            values=list(INTENSITY_MODE_LABELS.values()),
            state="readonly",
            width=13,
        ).grid(row=0, column=6, padx=(0, 14))
        ttk.Label(button_bar, text="Seconds").grid(row=0, column=7, padx=(0, 6))
        ttk.Spinbox(
            button_bar,
            textvariable=self.duration_var,
            from_=0.1,
            to=30.0,
            increment=0.1,
            width=7,
        ).grid(row=0, column=8, padx=(0, 18))
        ttk.Label(button_bar, text="Command").grid(row=1, column=0, padx=(0, 6), pady=(10, 0), sticky="w")
        ttk.Entry(button_bar, textvariable=self.custom_command_var, width=32).grid(row=1, column=1, columnspan=2, padx=(0, 8), pady=(10, 0), sticky="ew")
        ttk.Button(button_bar, text="Send", command=self.send_custom_command, style="Secondary.TButton").grid(row=1, column=3, pady=(10, 0), sticky="w")
        ttk.Checkbutton(button_bar, text="Turn off when finished", variable=self.auto_off_var).grid(row=1, column=4, padx=(14, 8), pady=(10, 0), sticky="w")
        self.stop_auto_button = ttk.Button(button_bar, text="Stop and turn off", command=self.stop_auto_test_and_turn_off, style="Danger.TButton")
        self.stop_auto_button.grid(row=1, column=5, padx=(0, 8), pady=(10, 0), sticky="w")
        ttk.Label(
            button_bar,
            text="Direct Mode: use only after Sim Host is downloaded. This app does not control or verify Sim Host.",
            style="Warning.TLabel",
        ).grid(row=2, column=0, columnspan=9, sticky="ew", pady=(10, 0))

        input_bar = ttk.LabelFrame(inputs_tab, text="Input monitor", padding=12, style="Section.TLabelframe")
        input_bar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        input_bar.columnconfigure(5, weight=1)

        self.input_monitor_button = ttk.Button(input_bar, text="Monitor VER 3", command=self.start_input_monitor, style="Primary.TButton")
        self.input_monitor_button.grid(row=0, column=0, padx=(0, 8))
        self.stop_input_monitor_button = ttk.Button(input_bar, text="Stop monitor", command=self.stop_input_monitor, style="Secondary.TButton")
        self.stop_input_monitor_button.grid(row=0, column=1, padx=(0, 8))
        ttk.Button(input_bar, text="Reset panel", command=self.reset_panel, style="Danger.TButton").grid(row=0, column=2, padx=(0, 14))
        ttk.Button(input_bar, text="Input details", command=self.show_selected_input_detail, style="Secondary.TButton").grid(row=0, column=3, padx=(0, 8))
        ttk.Button(input_bar, text="Export inputs", command=self.export_selected_input_plan, style="Secondary.TButton").grid(row=0, column=4, padx=(0, 14))
        ttk.Button(input_bar, text="Clear view", command=self.clear_input_monitor_view, style="Secondary.TButton").grid(row=0, column=5, padx=(0, 14))
        ttk.Label(input_bar, text="VER 0 pending hardware validation.", style="Muted.TLabel").grid(row=0, column=6, sticky="w")
        ttk.Label(input_bar, text="Detected panel:", style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Label(input_bar, textvariable=self.detected_var).grid(row=1, column=1, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(input_bar, textvariable=self.board_info_var, style="Muted.TLabel").grid(row=1, column=3, columnspan=4, sticky="w", pady=(8, 0))
        ttk.Button(
            input_bar,
            text="Event meanings",
            command=self.show_input_event_help,
            style="Secondary.TButton",
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))

        display_bar = ttk.LabelFrame(outputs_tab, text="Displays and indicators", padding=12, style="Section.TLabelframe")
        display_bar.grid(row=0, column=0, sticky="ew")
        display_bar.columnconfigure(3, weight=1)

        ttk.Label(display_bar, text="Word").grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Entry(display_bar, textvariable=self.display_word_var, width=8).grid(row=0, column=1, sticky="w", padx=(0, 10))
        ttk.Label(display_bar, text="Display text").grid(row=0, column=2, sticky="w", padx=(0, 6))
        ttk.Entry(display_bar, textvariable=self.display_text_var, width=18).grid(row=0, column=3, sticky="ew", padx=(0, 8))
        ttk.Button(display_bar, text="Send display", command=self.send_display_text, style="Primary.TButton").grid(row=0, column=4, padx=(0, 14))
        ttk.Button(display_bar, text="demo", command=self.send_demo_command, style="Secondary.TButton").grid(row=0, column=5, padx=(0, 8))
        ttk.Button(display_bar, text="ST", command=self.send_st_command, style="Secondary.TButton").grid(row=0, column=6, padx=(0, 8))
        ttk.Button(display_bar, text="ST_Brushless", command=self.send_brushless_st_command, style="Secondary.TButton").grid(row=0, column=7)
        ttk.Button(display_bar, text="Output details", command=self.show_selected_output_detail, style="Secondary.TButton").grid(row=1, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Button(display_bar, text="Export outputs", command=self.export_selected_output_plan, style="Secondary.TButton").grid(row=1, column=2, sticky="w", pady=(10, 0))
        ttk.Label(display_bar, text="Category").grid(row=1, column=3, sticky="e", padx=(0, 6), pady=(10, 0))
        ttk.Combobox(
            display_bar,
            textvariable=self.output_filter_var,
            values=list(OUTPUT_CATEGORY_FILTER_LABELS.values()),
            state="readonly",
            width=14,
        ).grid(row=1, column=4, sticky="w", pady=(10, 0))
        ttk.Label(display_bar, text="Sequence").grid(row=2, column=0, sticky="w", pady=(10, 0), padx=(0, 6))
        ttk.Entry(display_bar, textvariable=self.display_sweep_var, width=16).grid(
            row=2, column=1, sticky="w", pady=(10, 0), padx=(0, 10)
        )
        ttk.Label(display_bar, text="Step s").grid(row=2, column=2, sticky="e", pady=(10, 0), padx=(0, 6))
        ttk.Spinbox(
            display_bar,
            textvariable=self.display_step_var,
            from_=0.1,
            to=10.0,
            increment=0.1,
            width=7,
        ).grid(row=2, column=3, sticky="w", pady=(10, 0), padx=(0, 10))
        self.display_test_button = ttk.Button(
            display_bar,
            text="Automatic display test",
            command=self.start_display_test,
            style="Primary.TButton",
        )
        self.display_test_button.grid(row=2, column=4, sticky="w", pady=(10, 0), padx=(0, 8))
        self.stop_display_test_button = ttk.Button(
            display_bar,
            text="Stop",
            command=self.stop_display_test,
            style="Danger.TButton",
        )
        self.stop_display_test_button.grid(row=2, column=5, sticky="w", pady=(10, 0), padx=(0, 8))
        self.stop_display_test_button.configure(state="disabled")
        ttk.Checkbutton(display_bar, text="Restore 00", variable=self.display_restore_var).grid(
            row=2, column=6, columnspan=2, sticky="w", pady=(10, 0)
        )
        ttk.Label(display_bar, textvariable=self.display_test_summary_var, style="Muted.TLabel").grid(
            row=3, column=0, columnspan=8, sticky="ew", pady=(8, 0)
        )

        report_bar = ttk.LabelFrame(report_tab, text="Report", padding=12, style="Section.TLabelframe")
        report_bar.grid(row=0, column=0, sticky="ew")
        report_bar.columnconfigure(3, weight=1)

        ttk.Label(report_bar, text="Result").grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Combobox(
            report_bar,
            textvariable=self.report_result_var,
            values=RESULT_OPTIONS,
            state="readonly",
            width=12,
        ).grid(row=0, column=1, sticky="w", padx=(0, 14))
        ttk.Label(report_bar, text="Comment").grid(row=0, column=2, sticky="w", padx=(0, 6))
        ttk.Entry(report_bar, textvariable=self.report_comment_var).grid(row=0, column=3, sticky="ew", padx=(0, 8))
        ttk.Button(report_bar, text="Save panel", command=self.save_selected_panel_result, style="Secondary.TButton").grid(row=0, column=4, padx=(0, 8))
        ttk.Button(report_bar, text="Save report", command=self.save_report, style="Primary.TButton").grid(row=0, column=5)
        ttk.Label(report_bar, textvariable=self.report_summary_var, style="Muted.TLabel").grid(row=1, column=0, columnspan=4, sticky="w", pady=(8, 0))
        ttk.Button(report_bar, text="Save and next", command=self.save_selected_panel_result_and_next, style="Secondary.TButton").grid(row=1, column=4, padx=(0, 8), pady=(8, 0), sticky="w")
        ttk.Button(report_bar, text="Clear results", command=self.clear_panel_results, style="Secondary.TButton").grid(row=1, column=5, pady=(8, 0), sticky="w")
        ttk.Label(report_bar, textvariable=self.checklist_summary_var, style="Muted.TLabel").grid(row=2, column=0, columnspan=4, sticky="w", pady=(8, 0))
        ttk.Button(report_bar, text="Start checklist", command=self.start_checklist, style="Primary.TButton").grid(row=2, column=4, padx=(0, 8), pady=(8, 0), sticky="w")
        ttk.Button(report_bar, text="OK and next", command=lambda: self.save_checklist_result_and_next(RESULT_OK), style="Secondary.TButton").grid(row=2, column=5, pady=(8, 0), sticky="w")
        ttk.Button(report_bar, text="FAIL and next", command=lambda: self.save_checklist_result_and_next(RESULT_FAIL), style="Secondary.TButton").grid(row=3, column=4, padx=(0, 8), pady=(8, 0), sticky="w")
        ttk.Button(report_bar, text="N/A and next", command=lambda: self.save_checklist_result_and_next(RESULT_NA), style="Secondary.TButton").grid(row=3, column=5, pady=(8, 0), sticky="w")
        ttk.Button(report_bar, text="Clear history", command=self.clear_command_history, style="Secondary.TButton").grid(row=4, column=4, padx=(0, 8), pady=(8, 0), sticky="w")
        ttk.Button(report_bar, text="Save session", command=self.save_session, style="Secondary.TButton").grid(row=4, column=5, pady=(8, 0), sticky="w")
        ttk.Button(report_bar, text="Load session", command=self.choose_session_file, style="Secondary.TButton").grid(row=5, column=5, pady=(8, 0), sticky="w")

        status = ttk.Frame(self, padding=(0, 0, 0, 0), style="Status.TFrame")
        status.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 8))
        status.columnconfigure(3, weight=1)
        ttk.Label(status, textvariable=self.status_var, style="Status.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(status, text="Panel:", style="Status.TLabel").grid(row=0, column=1, sticky="w", padx=(8, 0))
        ttk.Label(status, textvariable=self.detected_var, style="Status.TLabel").grid(row=0, column=2, sticky="w")
        ttk.Label(status, textvariable=self.board_info_var, style="Status.TLabel").grid(row=0, column=3, sticky="w")
        self.assign_address_button = ttk.Button(
            status,
            text="Change address",
            command=self.open_address_assignment,
            style="Secondary.TButton",
        )
        self.assign_address_button.grid(row=0, column=4, padx=(8, 0), pady=4, sticky="e")
        ttk.Button(status, text="Operational status", command=self.show_operational_status, style="Secondary.TButton").grid(row=0, column=5, padx=(8, 8), pady=4, sticky="e")
        ttk.Button(status, text="Pre-HW checklist", command=self.show_pre_hardware_checklist, style="Secondary.TButton").grid(row=0, column=6, pady=4, sticky="e")

        work_frame = ttk.PanedWindow(lights_tab, orient=tk.HORIZONTAL)
        work_frame.grid(row=2, column=0, sticky="nsew")

        panel_frame = ttk.LabelFrame(work_frame, text="Available panels", padding=(10, 8), style="Section.TLabelframe")
        panel_frame.columnconfigure(0, weight=1)
        panel_frame.rowconfigure(0, weight=1)
        self.panel_tree = ttk.Treeview(
            panel_frame,
            columns=("panel", "variants", "lights", "inputs", "outputs", "words", "result"),
            show="headings",
            selectmode="browse",
            height=14,
        )
        self.panel_tree.heading("panel", text="Panel")
        self.panel_tree.heading("variants", text="Vars")
        self.panel_tree.heading("lights", text="Lights")
        self.panel_tree.heading("inputs", text="Inputs")
        self.panel_tree.heading("outputs", text="Outputs")
        self.panel_tree.heading("words", text="Words")
        self.panel_tree.heading("result", text="Result")
        self.panel_tree.column("panel", width=150, anchor="w")
        self.panel_tree.column("variants", width=55, anchor="center", stretch=False)
        self.panel_tree.column("lights", width=70, anchor="center", stretch=False)
        self.panel_tree.column("inputs", width=80, anchor="center", stretch=False)
        self.panel_tree.column("outputs", width=75, anchor="center", stretch=False)
        self.panel_tree.column("words", width=70, anchor="center", stretch=False)
        self.panel_tree.column("result", width=110, anchor="center", stretch=False)
        self.panel_tree.grid(row=0, column=0, sticky="nsew")
        panel_scroll = ttk.Scrollbar(panel_frame, orient=tk.VERTICAL, command=self.panel_tree.yview)
        panel_scroll.grid(row=0, column=1, sticky="ns")
        self.panel_tree.configure(yscrollcommand=panel_scroll.set)
        self.panel_tree.tag_configure("even", background=SURFACE)
        self.panel_tree.tag_configure("odd", background="#f7f9fc")
        work_frame.add(panel_frame, weight=1)

        table_frame = ttk.LabelFrame(work_frame, text="Generated commands", padding=(10, 8), style="Section.TLabelframe")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        table_frame.rowconfigure(2, weight=0)
        self.light_tree = ttk.Treeview(
            table_frame,
            columns=("word", "on", "mask", "count", "signals"),
            show="headings",
            height=12,
        )
        self.light_tree.heading("word", text="Word")
        self.light_tree.heading("on", text="ON")
        self.light_tree.heading("mask", text="Mask")
        self.light_tree.heading("count", text="Lights")
        self.light_tree.heading("signals", text="Signals")
        self.light_tree.column("word", width=70, anchor="center", stretch=False)
        self.light_tree.column("on", width=90, anchor="center", stretch=False)
        self.light_tree.column("mask", width=90, anchor="center", stretch=False)
        self.light_tree.column("count", width=70, anchor="center", stretch=False)
        self.light_tree.column("signals", width=760, anchor="w")
        self.light_tree.grid(row=0, column=0, sticky="nsew")
        tree_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.light_tree.yview)
        tree_scroll.grid(row=0, column=1, sticky="ns")
        self.light_tree.configure(yscrollcommand=tree_scroll.set)
        self.light_tree.tag_configure("even", background=SURFACE)
        self.light_tree.tag_configure("odd", background="#f7f9fc")

        command_actions = ttk.Frame(table_frame, style="Card.TFrame")
        command_actions.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        command_actions.columnconfigure(0, weight=1)
        ttk.Label(command_actions, textvariable=self.command_preview_var, style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(command_actions, text="Copy ON", command=self.copy_selected_on_commands, style="Secondary.TButton").grid(row=0, column=1, padx=(8, 0))
        ttk.Button(command_actions, text="Copy OFF", command=self.copy_selected_off_commands, style="Secondary.TButton").grid(row=0, column=2, padx=(8, 0))
        ttk.Button(command_actions, text="Copy details", command=self.copy_selected_command_plan, style="Secondary.TButton").grid(row=0, column=3, padx=(8, 0))
        ttk.Button(command_actions, text="Export commands", command=self.export_selected_command_plan, style="Secondary.TButton").grid(row=0, column=4, padx=(8, 0))
        ttk.Button(command_actions, text="Turn word on", command=self.turn_selected_word_on, style="Primary.TButton").grid(row=1, column=1, padx=(8, 0), pady=(8, 0), sticky="e")
        ttk.Button(command_actions, text="Turn word off", command=self.turn_selected_word_off, style="Secondary.TButton").grid(row=1, column=2, padx=(8, 0), pady=(8, 0), sticky="e")

        signal_area = ttk.Frame(table_frame, style="Card.TFrame")
        signal_area.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        signal_area.columnconfigure(0, weight=1)
        ttk.Label(signal_area, text="Signals in selected word", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        self.signal_tree = ttk.Treeview(
            signal_area,
            columns=("panel", "signal", "bits", "on", "comment"),
            show="headings",
            height=5,
        )
        self.signal_tree.heading("panel", text="Panel")
        self.signal_tree.heading("signal", text="Signal")
        self.signal_tree.heading("bits", text="Bits")
        self.signal_tree.heading("on", text="ON")
        self.signal_tree.heading("comment", text="Comment")
        self.signal_tree.column("panel", width=90, anchor="w", stretch=False)
        self.signal_tree.column("signal", width=220, anchor="w", stretch=False)
        self.signal_tree.column("bits", width=70, anchor="center", stretch=False)
        self.signal_tree.column("on", width=90, anchor="center", stretch=False)
        self.signal_tree.column("comment", width=540, anchor="w")
        self.signal_tree.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        signal_scroll = ttk.Scrollbar(signal_area, orient=tk.VERTICAL, command=self.signal_tree.yview)
        signal_scroll.grid(row=1, column=1, sticky="ns", pady=(4, 0))
        self.signal_tree.configure(yscrollcommand=signal_scroll.set)
        self.signal_tree.tag_configure("even", background=SURFACE)
        self.signal_tree.tag_configure("odd", background="#f7f9fc")

        signal_actions = ttk.Frame(table_frame, style="Card.TFrame")
        signal_actions.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        signal_actions.columnconfigure(0, weight=1)
        ttk.Label(signal_actions, textvariable=self.signal_preview_var, style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(signal_actions, text="Turn signal on", command=self.turn_selected_signal_on, style="Primary.TButton").grid(row=0, column=1, padx=(8, 0), sticky="e")
        ttk.Button(signal_actions, text="Turn signal off", command=self.turn_selected_signal_off, style="Secondary.TButton").grid(row=0, column=2, padx=(8, 0), sticky="e")
        work_frame.add(table_frame, weight=3)

        input_events_frame = ttk.LabelFrame(inputs_tab, text="Decoded changes", padding=(10, 8), style="Section.TLabelframe")
        input_events_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 6))
        input_events_frame.columnconfigure(0, weight=1)
        input_events_frame.rowconfigure(0, weight=1)
        self.input_event_tree = ttk.Treeview(
            input_events_frame,
            columns=("time", "event", "word", "value", "change", "signal", "bits", "raw", "logical"),
            show="headings",
            height=10,
        )
        input_headings = {
            "time": "Time",
            "event": "Event",
            "word": "Word",
            "value": "Value",
            "change": "Change",
            "signal": "Signal",
            "bits": "Bits",
            "raw": "Raw",
            "logical": "Logical",
        }
        input_widths = {"time": 80, "event": 120, "word": 65, "value": 70, "change": 70, "signal": 260, "bits": 65, "raw": 90, "logical": 90}
        for column, heading in input_headings.items():
            self.input_event_tree.heading(column, text=heading)
            self.input_event_tree.column(column, width=input_widths[column], anchor="w" if column == "signal" else "center")
        self.input_event_tree.grid(row=0, column=0, sticky="nsew")
        input_event_scroll = ttk.Scrollbar(input_events_frame, orient=tk.VERTICAL, command=self.input_event_tree.yview)
        input_event_scroll.grid(row=0, column=1, sticky="ns")
        self.input_event_tree.configure(yscrollcommand=input_event_scroll.set)
        self.input_event_tree.tag_configure("unmapped", background="#fff5d6")
        self.input_event_tree.tag_configure("changed", background="#eef8f0")
        input_console_frame = ttk.LabelFrame(inputs_tab, text="VER 3 console", padding=(10, 8), style="Section.TLabelframe")
        input_console_frame.grid(row=2, column=0, sticky="nsew")
        input_console_frame.columnconfigure(0, weight=1)
        input_console_frame.rowconfigure(0, weight=1)
        self.input_console_text = tk.Text(
            input_console_frame,
            height=10,
            wrap="none",
            state="disabled",
            background=LOG_BG,
            foreground=LOG_TEXT,
            insertbackground=LOG_TEXT,
            relief="flat",
            padx=10,
            pady=8,
            font=("Consolas", 9),
        )
        self.input_console_text.grid(row=0, column=0, sticky="nsew")
        self.input_console_text.tag_configure("tx", foreground="#8fd3ff")
        self.input_console_text.tag_configure("rx", foreground="#f4f7fb")
        self.input_console_text.tag_configure("decoded", foreground="#9ee6ad")
        self.input_console_text.tag_configure("warning", foreground="#ffd477")
        input_console_scroll = ttk.Scrollbar(input_console_frame, orient=tk.VERTICAL, command=self.input_console_text.yview)
        input_console_scroll.grid(row=0, column=1, sticky="ns")
        self.input_console_text.configure(yscrollcommand=input_console_scroll.set)
        input_terminal_bar = ttk.Frame(inputs_tab)
        input_terminal_bar.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        input_terminal_bar.columnconfigure(1, weight=1)
        ttk.Label(input_terminal_bar, text="Custom command").grid(row=0, column=0, padx=(0, 8))
        input_command_entry = ttk.Entry(input_terminal_bar, textvariable=self.custom_command_var)
        input_command_entry.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        input_command_entry.bind("<Return>", lambda _event: self.send_custom_command())
        ttk.Button(input_terminal_bar, text="Send", command=self.send_custom_command, style="Primary.TButton").grid(row=0, column=2)

        log_frame = ttk.LabelFrame(console_tab, text="Serial terminal", padding=(10, 8), style="Section.TLabelframe")
        log_frame.grid(row=1, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_text = tk.Text(
            log_frame,
            height=12,
            wrap="word",
            state="disabled",
            background=LOG_BG,
            foreground=LOG_TEXT,
            insertbackground=LOG_TEXT,
            relief="flat",
            padx=10,
            pady=8,
            font=(FONT, 9),
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        log_scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=log_scroll.set)

        terminal_bar = ttk.Frame(console_tab)
        terminal_bar.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        terminal_bar.columnconfigure(1, weight=1)
        ttk.Label(terminal_bar, text="Custom command").grid(row=0, column=0, padx=(0, 8))
        terminal_command_entry = ttk.Entry(terminal_bar, textvariable=self.custom_command_var)
        terminal_command_entry.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        terminal_command_entry.bind("<Return>", lambda _event: self.send_custom_command())
        ttk.Button(terminal_bar, text="Send", command=self.send_custom_command, style="Primary.TButton").grid(row=0, column=2, padx=(0, 8))
        ttk.Button(terminal_bar, text="Clear terminal", command=self.clear_terminal_view, style="Secondary.TButton").grid(row=0, column=3)

    def _bind_events(self) -> None:
        self.panel_tree.bind("<<TreeviewSelect>>", lambda _event: self.on_panel_changed())
        self.light_tree.bind("<<TreeviewSelect>>", lambda _event: self.on_light_group_changed())
        self.signal_tree.bind("<<TreeviewSelect>>", lambda _event: self.on_signal_changed())
        self.search_var.trace_add("write", lambda *_args: self.populate_panels())
        self.result_filter_var.trace_add("write", lambda *_args: self.populate_panels())
        self.custom_command_var.trace_add("write", lambda *_args: None)
        self.intensity_mode_var.trace_add("write", lambda *_args: self.on_intensity_mode_changed())
        self.light_filter_var.trace_add("write", lambda *_args: self.on_light_filter_changed())
        self.output_filter_var.trace_add("write", lambda *_args: self.on_output_filter_changed())
        self.response_wait_var.trace_add("write", lambda *_args: self.save_current_settings())
        self.response_quiet_var.trace_add("write", lambda *_args: self.save_current_settings())
        self.command_delay_var.trace_add("write", lambda *_args: self.save_current_settings())
        self.diagnostic_seconds_var.trace_add("write", lambda *_args: self.save_current_settings())

    def _load_initial_data(self) -> None:
        self.refresh_ports()
        self.log("Load a .dat file to list the available panels.")
        if not pyserial_available():
            self.log("pyserial is not installed. Install dependencies with: python -m pip install -r requirements.txt")
        if self.settings.last_dat_path:
            last_dat_path = Path(self.settings.last_dat_path)
            if last_dat_path.exists():
                self.load_dat_file(last_dat_path, show_errors=False)
            else:
                self.log(f"Last .dat file not found: {last_dat_path}")

    def choose_dat_file(self) -> None:
        initial_dir = self.definition_dir if self.definition_dir.exists() else Path.cwd()
        selected = filedialog.askopenfilename(
            title="Select interface definition",
            initialdir=initial_dir,
            filetypes=(("Interface definition", "*.dat"), ("All files", "*.*")),
        )
        if selected:
            self.load_dat_file(Path(selected))

    def load_dat_file(self, path: Path, *, show_errors: bool = True) -> bool:
        try:
            aircraft = parse_interface_file(path)
        except Exception as exc:  # noqa: BLE001 - surfaced to operator.
            if show_errors:
                messagebox.showerror(".dat file", f"Could not load the file:\n{exc}")
            else:
                self.log(f"Could not load the last .dat file: {exc}")
            return False

        self.current_aircraft = aircraft
        self.definition_dir = path.parent
        self.current_validation_report = validate_aircraft_definition(aircraft)
        self.active_board_address = None
        self.input_word_values.clear()
        self.input_history.clear()
        self.clear_input_monitor_view()
        self.panel_results.clear()
        self.current_result_key = None
        self.current_result_label = ""
        self.detected_panel = None
        self.detected_var.set("Not detected")
        self.board_info_var.set("Board: no information")
        self.report_result_var.set(RESULT_NOT_TESTED)
        self.report_comment_var.set("")
        self.search_var.set("")
        self.dat_path_var.set(str(path))
        self.validation_summary_var.set(self.current_validation_report.summary)
        self.current_panel_families = self.build_current_panel_families()
        self.populate_panels()
        self.update_report_summary()
        capability_totals = self.current_capability_totals()
        self.log(
            f"Loaded {aircraft.name}: {len(aircraft.panels)} defined panels, "
            f"{len(self.current_panel_families)} testable families "
            f"({capability_totals.light_count} lights, "
            f"{capability_totals.input_count} inputs, "
            f"{capability_totals.output_count} special outputs)."
        )
        self.log_validation_report(self.current_validation_report)
        self.save_current_settings()
        return True

    def current_intensity_mode(self) -> str:
        selected_label = self.intensity_mode_var.get()
        for mode, label in INTENSITY_MODE_LABELS.items():
            if label == selected_label:
                return mode
        return INTENSITY_MODE_RAW

    def current_light_filter(self) -> str:
        selected_label = self.light_filter_var.get()
        for light_filter, label in LIGHT_FILTER_LABELS.items():
            if label == selected_label:
                return light_filter
        return LIGHT_FILTER_ALL

    def current_output_filter(self) -> str:
        selected_label = self.output_filter_var.get()
        for category_filter, label in OUTPUT_CATEGORY_FILTER_LABELS.items():
            if label == selected_label:
                return category_filter
        return OUTPUT_FILTER_ALL

    def build_current_panel_families(self) -> list[PanelFamilyLightTest]:
        if not self.current_aircraft:
            self.current_family_stats = {}
            return []
        families, stats = build_panel_inventory(
            self.current_aircraft,
            self.current_intensity_mode(),
            self.current_light_filter(),
        )
        self.current_family_stats = stats
        return families

    def current_capability_totals(self) -> PanelCapabilityStats:
        return PanelCapabilityStats(
            light_count=sum(stats.light_count for stats in self.current_family_stats.values()),
            light_word_count=sum(stats.light_word_count for stats in self.current_family_stats.values()),
            input_count=sum(stats.input_count for stats in self.current_family_stats.values()),
            input_word_count=sum(stats.input_word_count for stats in self.current_family_stats.values()),
            output_count=sum(stats.output_count for stats in self.current_family_stats.values()),
            output_word_count=sum(stats.output_word_count for stats in self.current_family_stats.values()),
        )

    def on_intensity_mode_changed(self) -> None:
        self.save_current_settings()
        if not self.current_aircraft:
            return
        self.current_panel_families = self.build_current_panel_families()
        self.populate_panels()
        self.log(f"Intensity profile: {self.intensity_mode_var.get()}")

    def on_light_filter_changed(self) -> None:
        self.save_current_settings()
        if not self.current_aircraft:
            return
        self.current_panel_families = self.build_current_panel_families()
        self.populate_panels()
        self.log(f"Light type: {self.light_filter_var.get()}")

    def refresh_ports(self) -> None:
        previous_display = self.port_var.get()
        previous_device = self.port_display_to_device.get(previous_display, previous_display)
        self.port_display_to_device.clear()
        displays = []
        for port in list_serial_ports():
            display = port.display_name
            displays.append(display)
            self.port_display_to_device[display] = port.device
        self.port_combo["values"] = displays
        if not displays:
            self.port_var.set("")
            return

        preferred_device = previous_device or self.settings.serial_port
        preferred_display = self.display_for_serial_device(preferred_device)
        if preferred_display:
            self.port_var.set(preferred_display)
        elif previous_display in displays:
            self.port_var.set(previous_display)
        else:
            self.port_var.set(displays[0])

    def display_for_serial_device(self, device: str) -> str | None:
        if not device:
            return None
        for display, port_device in self.port_display_to_device.items():
            if port_device == device or display == device:
                return display
        return None

    def populate_panels(self) -> None:
        query = self.search_var.get().strip().lower()
        result_filter = self.result_filter_var.get()
        selected_family = self.get_selected_family_name()
        self.tree_item_to_family.clear()
        for item in self.panel_tree.get_children():
            self.panel_tree.delete(item)

        first_item = None
        for index, family in enumerate(self.current_panel_families):
            haystack = f"{family.family_name} {' '.join(family.variant_names)}".lower()
            if query and query not in haystack:
                continue
            result_summary = summarize_family_result(family.family_name, family.variant_names, self.panel_results)
            if not result_matches_filter(result_summary, result_filter):
                continue
            stats = self.current_family_stats.get(family.family_name, PanelCapabilityStats())

            item_id = f"panel_{index}"
            self.panel_tree.insert(
                "",
                tk.END,
                iid=item_id,
                tags=("even" if index % 2 == 0 else "odd",),
                values=(
                    family.family_name,
                    family.variant_count,
                    stats.light_count,
                    stats.input_count,
                    stats.output_count,
                    len(family.groups),
                    result_summary,
                ),
            )
            self.tree_item_to_family[item_id] = family.family_name
            if first_item is None:
                first_item = item_id
            if selected_family == family.family_name:
                self.panel_tree.selection_set(item_id)
                self.panel_tree.focus(item_id)

        if self.panel_tree.selection():
            self.on_panel_changed()
        elif first_item:
            self.panel_tree.selection_set(first_item)
            self.panel_tree.focus(first_item)
            self.on_panel_changed()
        else:
            self.clear_light_table()

    def on_panel_changed(self) -> None:
        self.store_current_panel_result()
        test = self.get_selected_test_target()
        self.clear_light_table()
        if not test:
            self.current_result_key = None
            self.current_result_label = ""
            self.report_result_var.set(RESULT_NOT_TESTED)
            self.report_comment_var.set("")
            self.update_display_test_summary()
            return
        self.load_panel_result(test)
        for index, group in enumerate(test.groups):
            item_id = f"light_{index}"
            self.light_tree.insert(
                "",
                tk.END,
                iid=item_id,
                tags=("even" if index % 2 == 0 else "odd",),
                values=(f"w{group.word}", f"{group.command_value:04x}", f"{group.mask:04x}", len(group.signals), group.signal_names),
            )
            self.light_item_to_commands[item_id] = (f"w{group.word}", group.on_command, group.off_command)
            self.light_item_to_group[item_id] = group
            if index == 0:
                self.light_tree.selection_set(item_id)
                self.light_tree.focus(item_id)
        self.command_preview_var.set(self.light_command_preview_text(test))
        self.on_light_group_changed()
        self.log_preview(test)
        self.update_display_test_summary()

    def on_output_filter_changed(self) -> None:
        self.save_current_settings()
        self.update_display_test_summary()

    def clear_light_table(self) -> None:
        self.light_item_to_commands.clear()
        self.light_item_to_group.clear()
        for item in self.light_tree.get_children():
            self.light_tree.delete(item)
        self.command_preview_var.set("Select a panel to view ON/OFF commands.")
        self.clear_signal_table()

    def selected_light_group_commands(self, *, show_warning: bool = True) -> tuple[str, str, str] | None:
        selection = self.light_tree.selection()
        if not selection:
            if show_warning:
                messagebox.showwarning("Word", "Select a generated command row.")
            return None

        commands = self.light_item_to_commands.get(selection[0])
        if not commands and show_warning:
            messagebox.showwarning("Word", "The selected row has no available commands.")
        return commands

    def selected_light_group(self, *, show_warning: bool = True) -> WordLightGroup | None:
        selection = self.light_tree.selection()
        if not selection:
            if show_warning:
                messagebox.showwarning("Word", "Select a generated command row.")
            return None
        group = self.light_item_to_group.get(selection[0])
        if not group and show_warning:
            messagebox.showwarning("Word", "The selected row has no available signals.")
        return group

    def on_light_group_changed(self) -> None:
        commands = self.selected_light_group_commands(show_warning=False)
        if commands:
            word_label, on_command, off_command = commands
            self.command_preview_var.set(f"{word_label}: ON {on_command} / OFF {off_command}")
            group = self.selected_light_group(show_warning=False)
            if group:
                self.populate_signal_table(group)
            return

        self.clear_signal_table()
        test = self.get_selected_test_target()
        if test:
            self.command_preview_var.set(self.light_command_preview_text(test))
        else:
            self.command_preview_var.set("Select a panel to view ON/OFF commands.")

    def light_command_preview_text(self, test: PanelLightTest | PanelFamilyLightTest) -> str:
        if not test.on_commands:
            return (
                f"{command_target_label(test)}: no light commands with the current filter. "
                "Use Panel details, Input details, or Output details."
            )
        return f"{command_target_label(test)}: {len(test.on_commands)} ON, {len(test.off_commands)} OFF"

    def populate_signal_table(self, group: WordLightGroup) -> None:
        self.clear_signal_table()
        intensity_mode = self.current_intensity_mode()
        for index, signal in enumerate(group.signals):
            item_id = f"signal_{index}"
            on_command = signal_on_command(signal, intensity_mode)
            off_command = signal_off_command(signal)
            self.signal_tree.insert(
                "",
                tk.END,
                iid=item_id,
                tags=("even" if index % 2 == 0 else "odd",),
                values=(
                    signal.panel_name,
                    signal.name,
                    signal.bit_range,
                    on_command.split(" ", maxsplit=1)[1],
                    signal.comment,
                ),
            )
            self.signal_item_to_commands[item_id] = (
                signal_command_label(signal),
                on_command,
                off_command,
            )
            if index == 0:
                self.signal_tree.selection_set(item_id)
                self.signal_tree.focus(item_id)
        self.on_signal_changed()

    def clear_signal_table(self) -> None:
        self.signal_item_to_commands.clear()
        if hasattr(self, "signal_tree"):
            for item in self.signal_tree.get_children():
                self.signal_tree.delete(item)
        self.signal_preview_var.set("Select a word to view its signals.")

    def selected_signal_commands(self, *, show_warning: bool = True) -> tuple[str, str, str] | None:
        selection = self.signal_tree.selection()
        if not selection:
            if show_warning:
                messagebox.showwarning("Signal", "Select a signal within the word.")
            return None
        commands = self.signal_item_to_commands.get(selection[0])
        if not commands and show_warning:
            messagebox.showwarning("Signal", "The selected signal has no available commands.")
        return commands

    def on_signal_changed(self) -> None:
        commands = self.selected_signal_commands(show_warning=False)
        if commands:
            signal_label, on_command, off_command = commands
            self.signal_preview_var.set(f"{signal_label}: ON {on_command} / OFF {off_command}")
        else:
            self.signal_preview_var.set("Select a word to view its signals.")

    def turn_selected_word_on(self) -> None:
        self.send_selected_word_command("on")

    def turn_selected_word_off(self) -> None:
        self.send_selected_word_command("off")

    def send_selected_word_command(self, direction: str) -> None:
        commands = self.selected_light_group_commands()
        if not commands:
            return
        test = self.require_selected_test()
        if not test:
            return

        word_label, on_command, off_command = commands
        command = on_command if direction == "on" else off_command
        self.log(f"{word_label}: sending {command}")
        self.run_worker(f"word-{direction}", lambda: self._send_commands_worker([command]))

    def turn_selected_signal_on(self) -> None:
        self.send_selected_signal_command("on")

    def turn_selected_signal_off(self) -> None:
        self.send_selected_signal_command("off")

    def send_selected_signal_command(self, direction: str) -> None:
        commands = self.selected_signal_commands()
        if not commands:
            return
        test = self.require_selected_test()
        if not test:
            return

        signal_label, on_command, off_command = commands
        command = on_command if direction == "on" else off_command
        self.log(f"{signal_label}: sending {command}")
        self.run_worker(f"signal-{direction}", lambda: self._send_commands_worker([command]))

    def get_selected_family_name(self) -> str | None:
        selection = self.panel_tree.selection() if hasattr(self, "panel_tree") else ()
        if not selection:
            return None
        return self.tree_item_to_family.get(selection[0])

    def get_selected_family(self) -> PanelFamilyLightTest | None:
        family_name = self.get_selected_family_name()
        if not family_name:
            return None
        for family in self.current_panel_families:
            if family.family_name == family_name:
                return family
        return None

    def get_selected_test_target(self) -> PanelLightTest | PanelFamilyLightTest | None:
        if not self.current_aircraft:
            return None
        family = self.get_selected_family()
        if not family:
            return None
        if self.detected_panel and panel_family_name(self.detected_panel.name) == family.family_name:
            exact_test = family.test_for_panel(self.detected_panel.name)
            if exact_test:
                return exact_test
        return family

    def log_preview(self, test: PanelLightTest | PanelFamilyLightTest) -> None:
        if isinstance(test, PanelLightTest):
            label = test.panel.display_name
        else:
            variants = ", ".join(test.variant_names)
            label = f"{test.family_name} ({variants})"
        self.log(f"Selected panel: {label}")
        if not test.on_commands:
            self.log("No light commands with the current filter")
            return
        on_commands = "  ".join(test.on_commands)
        off_commands = "  ".join(test.off_commands)
        self.log(f"ON : {on_commands}")
        self.log(f"OFF: {off_commands}")

    def require_selected_test_for_preview(self) -> PanelLightTest | PanelFamilyLightTest | None:
        if not self.current_aircraft:
            messagebox.showwarning(".dat file", "Load a .dat file before copying or exporting commands.")
            return None
        test = self.get_selected_test_target()
        if not test:
            messagebox.showwarning("Panel", "Select an available panel to view its commands.")
            return None
        if not test.on_commands:
            messagebox.showwarning(
                "Light commands",
                "The selected panel has no ON/OFF light commands with the current filter.\n\n"
                "Use Panel details, Input details, or Output details to review other available tests.",
            )
            return None
        return test

    def require_selected_test_for_detail(self) -> PanelLightTest | PanelFamilyLightTest | None:
        if not self.current_aircraft:
            messagebox.showwarning(".dat file", "Load a .dat file before viewing panel details.")
            return None
        test = self.get_selected_test_target()
        if not test:
            messagebox.showwarning("Panel", "Select an available panel to view its details.")
            return None
        return test

    def command_plan_metadata(self) -> dict[str, str]:
        return {
            "Generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Aircraft": self.current_aircraft.name if self.current_aircraft else "No .dat file loaded",
            "File": str(self.current_aircraft.path) if self.current_aircraft else self.dat_path_var.get(),
            "Detected panel": self.detected_panel_label(),
            "Light type": self.light_filter_var.get(),
            "Intensity": self.intensity_mode_var.get(),
            "Port": self.selected_serial_device() or "No port",
            "Baud": self.baud_var.get(),
            "Line ending": self.newline_var.get(),
        }

    def panel_detail_metadata(self) -> dict[str, str]:
        return {
            "Generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Aircraft": self.current_aircraft.name if self.current_aircraft else "No .dat file loaded",
            "File": str(self.current_aircraft.path) if self.current_aircraft else self.dat_path_var.get(),
            "Detected panel": self.detected_panel_label(),
            "Light type": self.light_filter_var.get(),
            "Intensity": self.intensity_mode_var.get(),
            "Result": self.report_result_var.get(),
            "Board": self.board_info_var.get(),
        }

    def selected_panel_detail_text(self) -> str | None:
        test = self.require_selected_test_for_detail()
        if not test:
            return None
        panel_names = self.panel_names_for_test_target(test)
        input_signals = input_signals_for_panels(self.current_aircraft, panel_names) if self.current_aircraft else []
        output_signals = special_output_signals_for_panels(self.current_aircraft, panel_names) if self.current_aircraft else []
        stats = self.current_family_stats.get(test.family_name) if isinstance(test, PanelFamilyLightTest) else None
        return build_panel_capability_detail_text(
            test,
            input_signals,
            output_signals,
            stats,
            self.panel_detail_metadata(),
            self.current_intensity_mode(),
        )

    def panel_names_for_test_target(self, test: PanelLightTest | PanelFamilyLightTest) -> list[str]:
        if isinstance(test, PanelLightTest):
            return [test.panel.name]
        return test.variant_names

    def show_selected_panel_detail(self) -> None:
        detail_text = self.selected_panel_detail_text()
        if detail_text is None:
            return

        dialog = tk.Toplevel(self)
        dialog.title("Panel details")
        dialog.transient(self)
        dialog.configure(background=SURFACE)
        dialog.geometry("920x620")
        dialog.minsize(720, 420)
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(0, weight=1)

        text_frame = ttk.Frame(dialog, style="Card.TFrame", padding=12)
        text_frame.grid(row=0, column=0, sticky="nsew")
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)

        detail_widget = tk.Text(
            text_frame,
            wrap="none",
            background=SURFACE,
            foreground=TEXT,
            insertbackground=TEXT,
            relief="solid",
            borderwidth=1,
            padx=10,
            pady=8,
            font=("Consolas", 9),
        )
        detail_widget.grid(row=0, column=0, sticky="nsew")
        detail_widget.insert("1.0", detail_text)
        detail_widget.configure(state="disabled")

        y_scroll = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=detail_widget.yview)
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll = ttk.Scrollbar(text_frame, orient=tk.HORIZONTAL, command=detail_widget.xview)
        x_scroll.grid(row=1, column=0, sticky="ew")
        detail_widget.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        button_frame = ttk.Frame(dialog, style="Card.TFrame", padding=(12, 0, 12, 12))
        button_frame.grid(row=1, column=0, sticky="e")
        ttk.Button(
            button_frame,
            text="Copy",
            command=lambda: self.copy_text_to_clipboard(
                detail_text,
                "Panel details",
                "Panel details copied to the clipboard",
            ),
            style="Secondary.TButton",
        ).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(
            button_frame,
            text="Export",
            command=lambda: self.export_panel_detail_text(detail_text),
            style="Secondary.TButton",
        ).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(button_frame, text="Close", command=dialog.destroy, style="Primary.TButton").grid(row=0, column=2)

        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        detail_widget.focus_set()

    def export_panel_detail_text(self, detail_text: str) -> Path | None:
        test = self.get_selected_test_target()
        if not test:
            messagebox.showwarning("Panel", "Select an available panel to export its details.")
            return None

        details_dir = Path.cwd() / "PanelDetails"
        details_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        panel_slug = safe_filename_fragment(command_target_label(test))
        detail_path = details_dir / f"panel_detail_{panel_slug}_{timestamp}.md"
        try:
            detail_path.write_text(detail_text, encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Panel details", f"Could not save the panel details:\n{exc}")
            return None
        self.log(f"Panel details saved: {detail_path}")
        messagebox.showinfo("Panel details", f"Details saved to:\n{detail_path}")
        return detail_path

    def build_operational_status_snapshot(self, generated_at: str | None = None) -> str:
        self.store_current_panel_result(refresh_table=True)
        now = generated_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        metadata = self.report_metadata(now)
        metadata = {
            "generated_at": now,
            "app_version": __version__,
            **metadata,
            "connection_status": self.connection_status_text,
        }
        return build_operational_status_text(
            metadata,
            self.operational_status_checks(),
            self.operational_status_sections(),
        )

    def operational_status_checks(self) -> list[ReadinessCheck]:
        checks: list[ReadinessCheck] = []
        selected_test = self.get_selected_test_target()
        selected_port = self.selected_serial_device()

        if self.current_aircraft:
            checks.append(
                ReadinessCheck(
                    "Definition",
                    READINESS_OK,
                    f"{self.current_aircraft.name}: {len(self.current_aircraft.panels)} defined panels",
                )
            )
        else:
            checks.append(ReadinessCheck("Definition", READINESS_WARNING, "Load a .dat file before testing."))

        if self.current_validation_report:
            status = READINESS_WARNING if self.current_validation_report.warning_count else READINESS_OK
            checks.append(ReadinessCheck("Validation .dat", status, self.current_validation_report.summary))
        else:
            checks.append(ReadinessCheck("Validation .dat", READINESS_INFO, "No validation available."))

        checks.append(
            ReadinessCheck(
                "Port",
                READINESS_OK if selected_port else READINESS_WARNING,
                selected_port or "Select a serial port.",
            )
        )
        checks.append(
            ReadinessCheck(
                "Connection",
                READINESS_OK if self.serial_connection.is_open else READINESS_WARNING,
                self.connection_status_text,
            )
        )

        baud = self.baud_var.get().strip()
        checks.append(
            ReadinessCheck(
                "Baud",
                READINESS_OK if baud.isdigit() and int(baud) > 0 else READINESS_WARNING,
                baud or "Enter the baud rate.",
            )
        )

        if selected_test:
            checks.append(ReadinessCheck("Selected panel", READINESS_OK, self.selected_panel_label()))
            checks.append(
                ReadinessCheck(
                    "Commands",
                    READINESS_OK if selected_test.on_commands else READINESS_WARNING,
                    f"{len(selected_test.on_commands)} ON, {len(selected_test.off_commands)} OFF, {len(selected_test.groups)} words",
                )
            )
        else:
            checks.append(ReadinessCheck("Selected panel", READINESS_WARNING, "Select an available panel."))
            checks.append(ReadinessCheck("Commands", READINESS_WARNING, "No generated commands."))

        if not self.detected_panel:
            checks.append(ReadinessCheck("Detected panel", READINESS_INFO, "No Info/manual."))
        elif selected_test and test_target_includes_panel(selected_test, self.detected_panel):
            checks.append(ReadinessCheck("Detected panel", READINESS_OK, self.detected_panel.display_name))
        else:
            checks.append(
                ReadinessCheck(
                    "Detected panel",
                    READINESS_WARNING,
                    f"Detected {self.detected_panel.display_name}; selected {self.selected_panel_label()}",
                )
            )

        total, tested, fail, pending = self.panel_progress_counts()
        checks.append(
            ReadinessCheck(
                "Checklist",
                READINESS_INFO if total else READINESS_WARNING,
                f"{tested}/{total} with status, {fail} FAIL, {pending} pending",
            )
        )
        checks.append(
            ReadinessCheck(
                "Direct Mode",
                READINESS_INFO,
                "Sim Host must be downloaded; this app does not control or verify it.",
            )
        )
        return checks

    def operational_status_sections(self) -> dict[str, list[str]]:
        selected_test = self.get_selected_test_target()
        total, tested, fail, pending = self.panel_progress_counts()
        capability_totals = self.current_capability_totals()
        sections = {
            "Test summary": [
                self.report_summary_var.get(),
                self.checklist_summary_var.get(),
                f"Families with tests: {total}",
                f"Lights mapped: {capability_totals.light_count}",
                f"Inputs mapped: {capability_totals.input_count}",
                f"Mapped non-light CO outputs: {capability_totals.output_count}",
                f"With status: {tested}",
                f"FAIL: {fail}",
                f"Pending: {pending}",
                f"History commands: {len(self.command_history)} events",
                self.serial_trace_summary_text(),
                f"Baseline inputs VER3: {len(self.input_word_values)} words",
                f"Decoded input history: {len(self.input_history)} events",
            ],
            "Test configuration": [
                f"Light type: {self.light_filter_var.get()}",
                f"Output category: {self.output_filter_var.get()}",
                f"Intensity: {self.intensity_mode_var.get()}",
                f"Automatic test duration: {self.duration_seconds():.2f} s",
                f"Turn off when finished: {'Yes' if self.auto_off_var.get() else 'No'}",
                f"Espera response: {self.response_wait_seconds():.2f} s",
                f"Response quiet time: {self.response_quiet_seconds():.2f} s",
                f"Command delay: {self.command_delay_seconds():.2f} s",
            ],
            "Commands selecteds": self.selected_command_summary_lines(selected_test),
        }
        if self.current_validation_report:
            sections["Validation"] = [
                self.current_validation_report.summary,
                *[
                    f"{issue.severity.upper()}: {issue.title}"
                    for issue in self.current_validation_report.issues[:12]
                ],
            ]
        return sections

    def selected_command_summary_lines(self, selected_test: PanelLightTest | PanelFamilyLightTest | None) -> list[str]:
        if not selected_test:
            return ["No panel selected."]

        max_commands = 12
        lines = [
            f"Panel: {command_target_label(selected_test)}",
            f"Words: {len(selected_test.groups)}",
            f"Lights/signales: {selected_test.light_count}",
            "ON:",
            *selected_test.on_commands[:max_commands],
        ]
        if len(selected_test.on_commands) > max_commands:
            lines.append(f"... {len(selected_test.on_commands) - max_commands} additional ON commands")
        lines.extend(["OFF:", *selected_test.off_commands[:max_commands]])
        if len(selected_test.off_commands) > max_commands:
            lines.append(f"... {len(selected_test.off_commands) - max_commands} additional OFF commands")
        return lines

    def serial_trace_summary_text(self) -> str:
        with self.serial_trace_lock:
            kept_count = len(self.serial_trace_events)
            discarded_count = self.serial_trace_discarded_count
        if discarded_count:
            return (
                f"Traza serial: {kept_count} events TX/RX, "
                f"{discarded_count} old discarded (limit {SERIAL_TRACE_MAX_EVENTS})"
            )
        return f"Traza serial: {kept_count} events TX/RX"

    def serial_trace_discarded_session_text(self, session: TestSession) -> str:
        if not session.serial_trace_discarded_count:
            return ""
        return f", {session.serial_trace_discarded_count} old discarded"

    def panel_progress_counts(self) -> tuple[int, int, int, int]:
        total = len(self.current_panel_families)
        tested = 0
        fail = 0
        for family in self.current_panel_families:
            summary = summarize_family_result(family.family_name, family.variant_names, self.panel_results)
            if summary == RESULT_NOT_TESTED:
                continue
            tested += 1
            if "FAIL" in summary:
                fail += 1
        pending = max(0, total - tested)
        return total, tested, fail, pending

    def show_operational_status(self) -> None:
        status_text = self.build_operational_status_snapshot()

        dialog = tk.Toplevel(self)
        dialog.title("Operational status")
        dialog.transient(self)
        dialog.configure(background=SURFACE)
        dialog.geometry("900x620")
        dialog.minsize(720, 420)
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(0, weight=1)

        text_frame = ttk.Frame(dialog, style="Card.TFrame", padding=12)
        text_frame.grid(row=0, column=0, sticky="nsew")
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)

        status_widget = tk.Text(
            text_frame,
            wrap="none",
            background=SURFACE,
            foreground=TEXT,
            insertbackground=TEXT,
            relief="solid",
            borderwidth=1,
            padx=10,
            pady=8,
            font=("Consolas", 9),
        )
        status_widget.grid(row=0, column=0, sticky="nsew")
        status_widget.insert("1.0", status_text)
        status_widget.configure(state="disabled")

        y_scroll = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=status_widget.yview)
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll = ttk.Scrollbar(text_frame, orient=tk.HORIZONTAL, command=status_widget.xview)
        x_scroll.grid(row=1, column=0, sticky="ew")
        status_widget.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        button_frame = ttk.Frame(dialog, style="Card.TFrame", padding=(12, 0, 12, 12))
        button_frame.grid(row=1, column=0, sticky="e")
        ttk.Button(
            button_frame,
            text="Copy",
            command=lambda: self.copy_text_to_clipboard(
                status_text,
                "Operational status",
                "Operational status copied to the clipboard",
            ),
            style="Secondary.TButton",
        ).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(
            button_frame,
            text="Export",
            command=lambda: self.export_operational_status_text(status_text),
            style="Secondary.TButton",
        ).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(button_frame, text="Close", command=dialog.destroy, style="Primary.TButton").grid(row=0, column=2)

        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        status_widget.focus_set()

    def export_operational_status_text(self, status_text: str) -> Path | None:
        snapshots_dir = Path.cwd() / "StatusSnapshots"
        snapshots_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        selected_slug = safe_filename_fragment(self.selected_panel_label())
        snapshot_path = snapshots_dir / f"operational_status_{selected_slug}_{timestamp}.md"
        try:
            snapshot_path.write_text(status_text, encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Operational status", f"Could not save Operational Status:\n{exc}")
            return None
        self.log(f"Operational status saved: {snapshot_path}")
        messagebox.showinfo("Operational status", f"Operational status saved to:\n{snapshot_path}")
        return snapshot_path

    def build_pre_hardware_checklist_snapshot(self, generated_at: str | None = None) -> str:
        self.store_current_panel_result(refresh_table=True)
        now = generated_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        metadata = {
            "generated_at": now,
            "app_version": __version__,
            **self.report_metadata(now),
            "connection_status": self.connection_status_text,
        }
        return build_pre_hardware_checklist_text(metadata)

    def show_pre_hardware_checklist(self) -> None:
        checklist_text = self.build_pre_hardware_checklist_snapshot()

        dialog = tk.Toplevel(self)
        dialog.title("Pre-HW checklist")
        dialog.transient(self)
        dialog.configure(background=SURFACE)
        dialog.geometry("900x620")
        dialog.minsize(720, 420)
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(0, weight=1)

        text_frame = ttk.Frame(dialog, style="Card.TFrame", padding=12)
        text_frame.grid(row=0, column=0, sticky="nsew")
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)

        checklist_widget = tk.Text(
            text_frame,
            wrap="none",
            background=SURFACE,
            foreground=TEXT,
            insertbackground=TEXT,
            relief="solid",
            borderwidth=1,
            padx=10,
            pady=8,
            font=("Consolas", 9),
        )
        checklist_widget.grid(row=0, column=0, sticky="nsew")
        checklist_widget.insert("1.0", checklist_text)
        checklist_widget.configure(state="disabled")

        y_scroll = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=checklist_widget.yview)
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll = ttk.Scrollbar(text_frame, orient=tk.HORIZONTAL, command=checklist_widget.xview)
        x_scroll.grid(row=1, column=0, sticky="ew")
        checklist_widget.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        button_frame = ttk.Frame(dialog, style="Card.TFrame", padding=(12, 0, 12, 12))
        button_frame.grid(row=1, column=0, sticky="e")
        ttk.Button(
            button_frame,
            text="Copy",
            command=lambda: self.copy_text_to_clipboard(
                checklist_text,
                "Pre-HW checklist",
                "Pre-HW checklist copied to the clipboard",
            ),
            style="Secondary.TButton",
        ).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(
            button_frame,
            text="Export",
            command=lambda: self.export_pre_hardware_checklist_text(checklist_text),
            style="Secondary.TButton",
        ).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(button_frame, text="Close", command=dialog.destroy, style="Primary.TButton").grid(row=0, column=2)

        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        checklist_widget.focus_set()

    def export_pre_hardware_checklist_text(self, checklist_text: str) -> Path | None:
        checklists_dir = Path.cwd() / "PreHardwareChecklists"
        checklists_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        selected_slug = safe_filename_fragment(self.selected_panel_label())
        checklist_path = checklists_dir / f"pre_hardware_checklist_{selected_slug}_{timestamp}.md"
        try:
            checklist_path.write_text(checklist_text, encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Pre-HW checklist", f"Could not save the checklist:\n{exc}")
            return None
        self.log(f"Pre-HW checklist saved: {checklist_path}")
        messagebox.showinfo("Pre-HW checklist", f"Checklist saved to:\n{checklist_path}")
        return checklist_path

    def selected_input_plan_text(self, *, show_warning: bool = True) -> str | None:
        if not self.current_aircraft:
            if show_warning:
                messagebox.showwarning(".dat file", "Load a .dat file before viewing inputs.")
            return None

        panel_names = self.input_decode_panel_names()
        signals = input_signals_for_panels(self.current_aircraft, panel_names)
        return build_input_test_plan_text(
            signals,
            self.input_target_label(panel_names),
            self.input_plan_metadata(panel_names, len(signals)),
        )

    def input_target_label(self, panel_names: list[str] | None) -> str:
        if self.detected_panel:
            return self.detected_panel.display_name

        selected = self.get_selected_test_target()
        if isinstance(selected, PanelLightTest):
            return selected.panel.display_name
        if isinstance(selected, PanelFamilyLightTest):
            return f"{selected.family_name} ({', '.join(selected.variant_names)})"
        if panel_names:
            return ", ".join(panel_names)
        return "All CI inputs"

    def input_plan_metadata(self, panel_names: list[str] | None, signal_count: int) -> dict[str, str]:
        return {
            "Generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Aircraft": self.current_aircraft.name if self.current_aircraft else "No .dat file loaded",
            "File": str(self.current_aircraft.path) if self.current_aircraft else self.dat_path_var.get(),
            "Detected panel": self.detected_panel_label(),
            "Selected panel": self.selected_panel_label(),
            "Input filter": ", ".join(panel_names) if panel_names else "All CI inputs",
            "Inputs CI": str(signal_count),
            "Port": self.selected_serial_device() or "No port",
            "Baud": self.baud_var.get(),
            "Line ending": self.newline_var.get(),
            "Direct Mode": "Sim Host downloaded; the app does not control or verify it.",
        }

    def show_selected_input_detail(self) -> None:
        plan_text = self.selected_input_plan_text()
        if plan_text is None:
            return

        dialog = tk.Toplevel(self)
        dialog.title("Input details")
        dialog.transient(self)
        dialog.configure(background=SURFACE)
        dialog.geometry("920x620")
        dialog.minsize(720, 420)
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(0, weight=1)

        text_frame = ttk.Frame(dialog, style="Card.TFrame", padding=12)
        text_frame.grid(row=0, column=0, sticky="nsew")
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)

        input_widget = tk.Text(
            text_frame,
            wrap="none",
            background=SURFACE,
            foreground=TEXT,
            insertbackground=TEXT,
            relief="solid",
            borderwidth=1,
            padx=10,
            pady=8,
            font=("Consolas", 9),
        )
        input_widget.grid(row=0, column=0, sticky="nsew")
        input_widget.insert("1.0", plan_text)
        input_widget.configure(state="disabled")

        y_scroll = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=input_widget.yview)
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll = ttk.Scrollbar(text_frame, orient=tk.HORIZONTAL, command=input_widget.xview)
        x_scroll.grid(row=1, column=0, sticky="ew")
        input_widget.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        button_frame = ttk.Frame(dialog, style="Card.TFrame", padding=(12, 0, 12, 12))
        button_frame.grid(row=1, column=0, sticky="e")
        ttk.Button(
            button_frame,
            text="Copy",
            command=lambda: self.copy_text_to_clipboard(
                plan_text,
                "Input details",
                "Input details copied to the clipboard",
            ),
            style="Secondary.TButton",
        ).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(
            button_frame,
            text="Export",
            command=lambda: self.export_input_plan_text(plan_text),
            style="Secondary.TButton",
        ).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(button_frame, text="Close", command=dialog.destroy, style="Primary.TButton").grid(row=0, column=2)

        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        input_widget.focus_set()

    def export_selected_input_plan(self) -> None:
        plan_text = self.selected_input_plan_text()
        if plan_text is not None:
            self.export_input_plan_text(plan_text)

    def export_input_plan_text(self, plan_text: str) -> Path | None:
        input_dir = Path.cwd() / "InputPlans"
        input_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target_slug = safe_filename_fragment(self.input_target_label(self.input_decode_panel_names()))
        input_path = input_dir / f"input_plan_{target_slug}_{timestamp}.md"
        try:
            input_path.write_text(plan_text, encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Inputs", f"Could not save the input plan:\n{exc}")
            return None
        self.log(f"Plan for inputs saved: {input_path}")
        messagebox.showinfo("Inputs", f"Input plan saved to:\n{input_path}")
        return input_path

    def selected_output_plan_text(self, *, show_warning: bool = True) -> str | None:
        if not self.current_aircraft:
            if show_warning:
                messagebox.showwarning(".dat file", "Load a .dat file before viewing outputs.")
            return None

        panel_names = self.input_decode_panel_names()
        signals = special_output_signals_for_panels(
            self.current_aircraft,
            panel_names,
            self.current_output_filter(),
        )
        return build_special_output_plan_text(
            signals,
            self.output_target_label(panel_names),
            self.output_plan_metadata(panel_names, len(signals)),
        )

    def output_target_label(self, panel_names: list[str] | None) -> str:
        if self.detected_panel:
            return self.detected_panel.display_name

        selected = self.get_selected_test_target()
        if isinstance(selected, PanelLightTest):
            return selected.panel.display_name
        if isinstance(selected, PanelFamilyLightTest):
            return f"{selected.family_name} ({', '.join(selected.variant_names)})"
        if panel_names:
            return ", ".join(panel_names)
        return "All non-light CO outputs"

    def output_plan_metadata(self, panel_names: list[str] | None, signal_count: int) -> dict[str, str]:
        return {
            "Generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Aircraft": self.current_aircraft.name if self.current_aircraft else "No .dat file loaded",
            "File": str(self.current_aircraft.path) if self.current_aircraft else self.dat_path_var.get(),
            "Detected panel": self.detected_panel_label(),
            "Selected panel": self.selected_panel_label(),
            "Output filter": ", ".join(panel_names) if panel_names else "All non-light CO outputs",
            "Output category": self.output_filter_var.get(),
            "Non-light CO outputs": str(signal_count),
            "Port": self.selected_serial_device() or "No port",
            "Baud": self.baud_var.get(),
            "Line ending": self.newline_var.get(),
            "Direct Mode": "Sim Host downloaded; the app does not control or verify it.",
        }

    def show_selected_output_detail(self) -> None:
        plan_text = self.selected_output_plan_text()
        if plan_text is None:
            return

        dialog = tk.Toplevel(self)
        dialog.title("Output details")
        dialog.transient(self)
        dialog.configure(background=SURFACE)
        dialog.geometry("960x640")
        dialog.minsize(720, 420)
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(0, weight=1)

        text_frame = ttk.Frame(dialog, style="Card.TFrame", padding=12)
        text_frame.grid(row=0, column=0, sticky="nsew")
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)

        output_widget = tk.Text(
            text_frame,
            wrap="none",
            background=SURFACE,
            foreground=TEXT,
            insertbackground=TEXT,
            relief="solid",
            borderwidth=1,
            padx=10,
            pady=8,
            font=("Consolas", 9),
        )
        output_widget.grid(row=0, column=0, sticky="nsew")
        output_widget.insert("1.0", plan_text)
        output_widget.configure(state="disabled")

        y_scroll = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=output_widget.yview)
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll = ttk.Scrollbar(text_frame, orient=tk.HORIZONTAL, command=output_widget.xview)
        x_scroll.grid(row=1, column=0, sticky="ew")
        output_widget.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        button_frame = ttk.Frame(dialog, style="Card.TFrame", padding=(12, 0, 12, 12))
        button_frame.grid(row=1, column=0, sticky="e")
        ttk.Button(
            button_frame,
            text="Copy",
            command=lambda: self.copy_text_to_clipboard(
                plan_text,
                "Output details",
                "Output details copied to the clipboard",
            ),
            style="Secondary.TButton",
        ).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(
            button_frame,
            text="Export",
            command=lambda: self.export_output_plan_text(plan_text),
            style="Secondary.TButton",
        ).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(button_frame, text="Close", command=dialog.destroy, style="Primary.TButton").grid(row=0, column=2)

        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        output_widget.focus_set()

    def export_selected_output_plan(self) -> None:
        plan_text = self.selected_output_plan_text()
        if plan_text is not None:
            self.export_output_plan_text(plan_text)

    def export_output_plan_text(self, plan_text: str) -> Path | None:
        output_dir = Path.cwd() / "OutputPlans"
        output_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target_slug = safe_filename_fragment(self.output_target_label(self.input_decode_panel_names()))
        category_slug = safe_filename_fragment(self.output_filter_var.get())
        output_path = output_dir / f"output_plan_{target_slug}_{category_slug}_{timestamp}.md"
        try:
            output_path.write_text(plan_text, encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Outputs", f"Could not save the output plan:\n{exc}")
            return None
        self.log(f"Plan for outputs saved: {output_path}")
        messagebox.showinfo("Outputs", f"Output plan saved to:\n{output_path}")
        return output_path

    def copy_selected_on_commands(self) -> None:
        test = self.require_selected_test_for_preview()
        if test:
            self.copy_text_to_clipboard("\n".join(test.on_commands), "Commands ON")

    def copy_selected_off_commands(self) -> None:
        test = self.require_selected_test_for_preview()
        if test:
            self.copy_text_to_clipboard("\n".join(test.off_commands), "Commands OFF")

    def copy_selected_command_plan(self) -> None:
        test = self.require_selected_test_for_preview()
        if test:
            self.copy_text_to_clipboard(
                build_command_plan_text(test, self.command_plan_metadata()),
                "Command details",
            )

    def copy_text_to_clipboard(self, text: str, label: str, status_message: str | None = None) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()
        message = status_message or f"{label} copied to the clipboard"
        self.status_var.set(message)
        self.log(message)

    def export_selected_command_plan(self) -> None:
        test = self.require_selected_test_for_preview()
        if not test:
            return

        plans_dir = Path.cwd() / "CommandPlans"
        plans_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        panel_slug = safe_filename_fragment(command_target_label(test))
        plan_path = plans_dir / f"command_plan_{panel_slug}_{timestamp}.md"
        try:
            plan_path.write_text(build_command_plan_text(test, self.command_plan_metadata()), encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Commands", f"Could not save the command plan:\n{exc}")
            return
        self.log(f"Plan for commands saved: {plan_path}")
        messagebox.showinfo("Commands", f"Command plan saved to:\n{plan_path}")

    def result_key_for_test(self, test: PanelLightTest | PanelFamilyLightTest) -> str:
        if isinstance(test, PanelLightTest):
            return test.panel.name
        return test.family_name

    def result_label_for_test(self, test: PanelLightTest | PanelFamilyLightTest) -> str:
        if isinstance(test, PanelLightTest):
            return test.panel.display_name
        return f"{test.family_name} ({', '.join(test.variant_names)})"

    def load_panel_result(self, test: PanelLightTest | PanelFamilyLightTest) -> None:
        key = self.result_key_for_test(test)
        self.current_result_key = key
        self.current_result_label = self.result_label_for_test(test)
        stored = self.panel_results.get(key)
        if stored:
            self.report_result_var.set(stored.result)
            self.report_comment_var.set(stored.comment)
        else:
            self.report_result_var.set(RESULT_NOT_TESTED)
            self.report_comment_var.set("")
        self.update_report_summary()

    def store_current_panel_result(self, *, show_log: bool = False, refresh_table: bool = False) -> None:
        if not self.current_result_key:
            return

        target = self.current_result_label or self.current_result_key
        selected = self.get_selected_test_target()
        if selected and self.result_key_for_test(selected) == self.current_result_key:
            target = self.result_label_for_test(selected)
        elif self.current_result_key in self.panel_results:
            target = self.panel_results[self.current_result_key].target

        result = self.report_result_var.get()
        comment = self.report_comment_var.get().strip()
        existing = self.panel_results.get(self.current_result_key)
        if existing and existing.result == result and existing.comment == comment:
            panel_result = existing
        else:
            panel_result = make_panel_result(
                target=target,
                result=result,
                comment=comment,
            )
        if should_keep_result(panel_result):
            self.panel_results[self.current_result_key] = panel_result
            if show_log:
                self.log(f"Result saved: {panel_result.target} -> {panel_result.result}")
        else:
            self.panel_results.pop(self.current_result_key, None)
            if show_log:
                self.log(f"Result cleared: {target}")

        self.update_report_summary()
        if refresh_table:
            self.refresh_panel_listing_after_result_change()

    def save_selected_panel_result(self) -> bool:
        test = self.get_selected_test_target()
        if not test:
            messagebox.showwarning("Panel", "Select a panel before saving the result.")
            return False
        self.current_result_key = self.result_key_for_test(test)
        self.current_result_label = self.result_label_for_test(test)
        self.store_current_panel_result(show_log=True, refresh_table=True)
        return True

    def save_selected_panel_result_and_next(self) -> None:
        test = self.get_selected_test_target()
        if not test:
            messagebox.showwarning("Panel", "Select a panel before saving the result.")
            return
        self.current_result_key = self.result_key_for_test(test)
        self.current_result_label = self.result_label_for_test(test)
        self.store_current_panel_result(show_log=True, refresh_table=False)
        self.select_next_pending_panel()

    def start_checklist(self) -> None:
        if not self.current_panel_families:
            messagebox.showwarning("Checklist", "Load a .dat file before starting the checklist.")
            return

        target = self.first_pending_family()
        if not target:
            messagebox.showinfo("Checklist", "There are no pending panels in the current session.")
            self.update_checklist_summary()
            return

        if self.search_var.get().strip():
            self.search_var.set("")
        if self.result_filter_var.get() != RESULT_FILTER_PENDING:
            self.result_filter_var.set(RESULT_FILTER_PENDING)

        self.populate_panels()
        if not self.select_family_name(target.family_name):
            self.result_filter_var.set(RESULT_FILTER_ALL)
            self.populate_panels()
            self.select_family_name(target.family_name)

        self.log(f"Checklist started at pending panel: {target.family_name}")
        self.update_checklist_summary()

    def save_checklist_result_and_next(self, result: str) -> None:
        test = self.get_selected_test_target()
        if not test:
            messagebox.showwarning("Checklist", "Select a panel before saving the result.")
            return

        self.report_result_var.set(result)
        self.current_result_key = self.result_key_for_test(test)
        self.current_result_label = self.result_label_for_test(test)
        self.store_current_panel_result(show_log=True, refresh_table=False)

        target = self.next_pending_family()
        if not target:
            self.refresh_panel_listing_after_result_change()
            self.update_checklist_summary()
            messagebox.showinfo("Checklist", "Checklist complete: no pending panels remain.")
            return

        if self.search_var.get().strip():
            self.search_var.set("")
        if self.result_filter_var.get() != RESULT_FILTER_PENDING:
            self.result_filter_var.set(RESULT_FILTER_PENDING)

        self.populate_panels()
        if not self.select_family_name(target.family_name):
            self.result_filter_var.set(RESULT_FILTER_ALL)
            self.populate_panels()
            self.select_family_name(target.family_name)
        self.update_checklist_summary()

    def select_next_pending_panel(self) -> None:
        if not self.current_panel_families:
            messagebox.showwarning("Panel", "Load a .dat file before navigating pending panels.")
            return

        target = self.next_pending_family()
        if not target:
            messagebox.showinfo("Panels", "There are no pending panels in the current session.")
            return

        if self.search_var.get().strip():
            self.search_var.set("")
        if self.result_filter_var.get() not in {RESULT_FILTER_ALL, RESULT_FILTER_PENDING}:
            self.result_filter_var.set(RESULT_FILTER_PENDING)

        self.populate_panels()
        if not self.select_family_name(target.family_name):
            self.result_filter_var.set(RESULT_FILTER_ALL)
            self.populate_panels()
            self.select_family_name(target.family_name)

    def first_pending_family(self) -> PanelFamilyLightTest | None:
        for family in self.current_panel_families:
            summary = summarize_family_result(family.family_name, family.variant_names, self.panel_results)
            if summary == RESULT_NOT_TESTED:
                return family
        return None

    def next_pending_family(self) -> PanelFamilyLightTest | None:
        if not self.current_panel_families:
            return None

        current_family_name = self.get_selected_family_name()
        start_index = 0
        if current_family_name:
            for index, family in enumerate(self.current_panel_families):
                if family.family_name == current_family_name:
                    start_index = (index + 1) % len(self.current_panel_families)
                    break

        for offset in range(len(self.current_panel_families)):
            family = self.current_panel_families[(start_index + offset) % len(self.current_panel_families)]
            summary = summarize_family_result(family.family_name, family.variant_names, self.panel_results)
            if summary == RESULT_NOT_TESTED:
                return family
        return None

    def select_family_name(self, family_name: str) -> bool:
        for item_id, item_family in self.tree_item_to_family.items():
            if item_family == family_name:
                self.panel_tree.selection_set(item_id)
                self.panel_tree.focus(item_id)
                self.panel_tree.see(item_id)
                self.on_panel_changed()
                return True
        return False

    def clear_panel_results(self) -> None:
        if not self.panel_results:
            self.log("There are no panel results to clear")
            return
        confirmed = messagebox.askyesno(
            "Clear results",
            "This clears the panel results from the current session. Command history will not be changed.",
        )
        if not confirmed:
            return
        self.panel_results.clear()
        self.current_result_key = None
        self.current_result_label = ""
        self.report_result_var.set(RESULT_NOT_TESTED)
        self.report_comment_var.set("")
        self.refresh_panel_result_cells()
        self.update_report_summary()
        self.log("Panel results cleared")

    def refresh_panel_listing_after_result_change(self) -> None:
        if self.result_filter_var.get() == RESULT_FILTER_ALL:
            self.refresh_panel_result_cells()
        else:
            self.populate_panels()

    def refresh_panel_result_cells(self) -> None:
        for item_id, family_name in self.tree_item_to_family.items():
            family = next((item for item in self.current_panel_families if item.family_name == family_name), None)
            if not family:
                continue
            values = list(self.panel_tree.item(item_id, "values"))
            if len(values) >= 7:
                values[6] = summarize_family_result(family.family_name, family.variant_names, self.panel_results)
                self.panel_tree.item(item_id, values=values)

    def update_report_summary(self) -> None:
        if not self.current_panel_families:
            self.report_summary_var.set("Results: no panels loaded")
            self.update_checklist_summary()
            return

        total, tested_families, fail_families, pending = self.panel_progress_counts()
        self.report_summary_var.set(
            f"Results: {tested_families}/{total} with status, "
            f"{fail_families} FAIL, {pending} pending"
        )
        self.update_checklist_summary()

    def update_checklist_summary(self) -> None:
        if not hasattr(self, "checklist_summary_var"):
            return
        if not self.current_panel_families:
            self.checklist_summary_var.set("Checklist: load a .dat file to begin.")
            return

        total, tested_families, fail_families, pending = self.panel_progress_counts()
        selected = self.selected_panel_label()
        connection = "connected" if self.serial_connection.is_open else "not connected"
        if self.detected_panel:
            test = self.get_selected_test_target()
            detection = "detected coincide" if test and test_target_includes_panel(test, self.detected_panel) else "detected distinto"
        else:
            detection = "no Info/manual selection"

        self.checklist_summary_var.set(
            f"Checklist: {tested_families}/{total} hechos, "
            f"{pending} pending, {fail_families} FAIL | {selected} | {connection}, {detection}"
        )

    def toggle_connection(self) -> None:
        if self.serial_connection.is_open:
            self.input_monitor_stop_event.set()
            self.auto_test_stop_event.set()
            self.display_test_stop_event.set()
            with self.serial_lock:
                self.serial_connection.close()
            self.connect_button.configure(text="Connect", style="Primary.TButton")
            self.connection_status_text = "Disconnected"
            self.status_var.set(self.connection_status_text)
            self.log("Port serial cerrado")
            self.update_checklist_summary()
            return

        display = self.port_var.get()
        port = self.port_display_to_device.get(display, display)
        if not port:
            messagebox.showwarning("Port serial", "Select a serial port.")
            return
        try:
            baudrate = int(self.baud_var.get())
        except ValueError:
            messagebox.showerror("Baud", "The baud rate must be an integer.")
            return

        try:
            self.serial_connection.open(port, baudrate)
        except SerialDependencyError:
            messagebox.showerror("Dependencies", "pyserial is not installed. Run: python -m pip install -r requirements.txt")
            return
        except Exception as exc:  # noqa: BLE001 - surfaced to operator.
            messagebox.showerror("Connection serial", str(exc))
            return

        self.connect_button.configure(text="Disconnect", style="Danger.TButton")
        self.connection_status_text = f"Connected a {port} @ {baudrate}"
        self.status_var.set(self.connection_status_text)
        self.log(f"Connected a {port} @ {baudrate}")
        self.save_current_settings()
        self.update_checklist_summary()

    def request_info(self) -> None:
        if not self.serial_connection.is_open:
            messagebox.showwarning("Connection", "Connect a serial port first.")
            return
        self.run_worker("info", self._request_info_worker)

    def request_help(self) -> None:
        if not self.serial_connection.is_open:
            messagebox.showwarning("Connection", "Connect a serial port first.")
            return
        self.run_worker("help", self._request_help_worker)

    def _request_info_worker(self) -> None:
        wait_seconds, quiet_seconds = self.response_timing()
        with self.serial_lock:
            self.record_serial_trace_bytes("TX", "info", line_payload("i", self.newline_var.get()))
            info = self.serial_connection.request_info(self.newline_var.get(), wait_seconds, quiet_seconds)
        self.queue_log("> i")
        if info.raw:
            self.record_serial_trace_text("RX", "info", info.raw)
        if info.raw.strip():
            self.queue_log(info.raw.strip())
        else:
            self.queue_log("No response to command i")
        self.record_command_event("i", info.raw.strip())
        self.after(0, lambda: self.handle_board_info(info))

    def _request_help_worker(self) -> None:
        wait_seconds, quiet_seconds = self.response_timing()
        with self.serial_lock:
            self.record_serial_trace_bytes("TX", "help", line_payload("?", self.newline_var.get()))
            response = self.serial_connection.request_command("?", self.newline_var.get(), wait_seconds, quiet_seconds)
        self.queue_log("> ?")
        if response:
            self.record_serial_trace_text("RX", "help", response)
        if response.strip():
            self.queue_log(response.strip())
        else:
            self.queue_log("No response to command ?")
        self.record_command_event("?", response.strip())

    def handle_board_info(self, info: BoardInfo) -> None:
        self.start_new_board_session_if_needed(info)
        pieces = []
        if info.channel is not None:
            pieces.append(f"channel {info.channel}")
        if info.address is not None:
            pieces.append(f"address {info.address}")
        self.detected_var.set(", ".join(pieces) if pieces else "Not recognized")
        self.board_info_var.set(self.format_board_info(info))
        self.finalize_address_assignment(info)

        if not self.current_aircraft or info.address is None:
            self.detected_panel = None
            return

        candidates = self.current_aircraft.panels_by_address(info.address)
        if info.channel is not None:
            exact = [panel for panel in candidates if panel.channel == info.channel]
            if exact:
                candidates = exact

        if not candidates:
            self.detected_panel = None
            self.log(f"No panel is defined with address {info.address} in {self.current_aircraft.name}")
            return

        if len(candidates) > 1:
            self.detected_panel = None
            names = ", ".join(panel.display_name for panel in candidates)
            self.log(f"Ambiguous address: {names}")
            selected_panel = self.choose_ambiguous_panel(candidates, info)
            if not selected_panel:
                if info.channel is not None:
                    self.detected_var.set(f"@{info.channel}.{info.address} ambiguous")
                else:
                    self.detected_var.set(f"address {info.address} ambiguous")
                return
            self.detected_panel = selected_panel
            self.select_panel(selected_panel)
            return

        self.detected_panel = candidates[0]
        self.select_panel(candidates[0])

    def start_new_board_session_if_needed(self, info: BoardInfo) -> None:
        if info.address is None:
            return
        previous_address = self.active_board_address
        self.active_board_address = info.address
        if previous_address is None or previous_address == info.address:
            return

        current_info_event = None
        if self.command_history and self.command_history[-1].get("command") == "i":
            current_info_event = dict(self.command_history[-1])
        assignment_events: list[dict[str, str]] = []
        pending_panel = self.pending_address_assignment
        if pending_panel and pending_panel.address == info.address:
            expected = [f"A {info.address}", "SAVE", "i"]
            trailing = self.command_history[-3:]
            if [event.get("command") for event in trailing] == expected:
                assignment_events = [dict(event) for event in trailing]

        with self.serial_trace_lock:
            current_info_trace: list[SerialTraceEvent] = []
            for event in reversed(self.serial_trace_events):
                if event.source != "info":
                    break
                current_info_trace.append(event)
            self.serial_trace_events = list(reversed(current_info_trace))
            self.serial_trace_discarded_count = 0
            self.serial_trace_limit_notice_shown = False

        self.command_history = assignment_events or ([current_info_event] if current_info_event else [])
        self.input_history.clear()
        self.input_word_values.clear()
        self.panel_results.clear()
        self.detected_panel = None
        self.current_result_key = None
        self.current_result_label = ""
        self.report_result_var.set(RESULT_NOT_TESTED)
        self.report_comment_var.set("")
        while True:
            try:
                self.input_command_queue.get_nowait()
            except queue.Empty:
                break
        self.refresh_input_monitor_view()
        self.clear_terminal_view()
        self.refresh_panel_result_cells()
        self.update_report_summary()
        self.log(f"New board session: address {previous_address} -> {info.address}")

    def choose_ambiguous_panel(
        self,
        candidates: list[PanelDefinition],
        info: BoardInfo,
    ) -> PanelDefinition | None:
        address_label = (
            f"@{info.channel}.{info.address}"
            if info.channel is not None
            else f"address {info.address}"
        )
        return self.choose_panel_candidate(
            candidates,
            "Ambiguous address",
            (
                f"The board reported {address_label}, but the .dat file has multiple panels "
                "with that address. Select the connected panel."
            ),
        )

    def open_address_assignment(self) -> None:
        if not self.current_aircraft:
            messagebox.showwarning(".dat file", "Load the .dat file before changing an address.")
            return
        if not self.serial_connection.is_open:
            messagebox.showwarning("Connection", "Connect the panel through the serial port first.")
            return
        if self.active_board_address is None:
            messagebox.showwarning("Board", "Press Info to read the current address before changing it.")
            return
        if self.input_monitor_running:
            messagebox.showwarning("Inputs", "Stop the VER 3 monitor before changing the address.")
            return
        if self.auto_test_running:
            messagebox.showwarning("Test", "Wait for the automatic test to finish before changing the address.")
            return
        if self.address_assignment_running:
            messagebox.showwarning("Address", "An address assignment is already running.")
            return

        panel = self.choose_address_assignment_panel()
        if not panel or panel.address is None:
            return
        if panel.address == self.active_board_address:
            messagebox.showinfo(
                "Address",
                f"The board already uses address {panel.address}, corresponding to {panel.name}.",
            )
            return
        if not self.confirm_direct_mode_ready():
            return

        side = panel_side_label(self.current_aircraft, panel)
        confirmed = messagebox.askyesno(
            "Confirm new address",
            "The persistent address of the connected board will be changed.\n\n"
            f"Current address: {self.active_board_address}\n"
            f"Target panel: {panel.name}\n"
            f"Side / variant: {side}\n"
            f"Channel from .dat: {panel.channel}\n"
            f"New address: {panel.address}\n\n"
            f"Commands: A {panel.address}, SAVE, i\n\n"
            "Continue?",
        )
        if not confirmed:
            return

        self.pending_address_assignment = panel
        self.address_assignment_running = True
        self.assign_address_button.configure(state="disabled")
        self.status_var.set(f"Assigning address {panel.address}...")
        self.run_worker("assign-address", lambda: self._assign_address_worker(panel))

    def choose_address_assignment_panel(self) -> PanelDefinition | None:
        if not self.current_aircraft:
            return None
        aircraft = self.current_aircraft
        candidates = address_assignment_panels(aircraft)

        dialog = tk.Toplevel(self)
        dialog.title("Assign panel address")
        dialog.transient(self)
        dialog.geometry("720x480")
        dialog.minsize(620, 380)
        dialog.configure(background=SURFACE)
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(2, weight=1)

        ttk.Label(
            dialog,
            text="Select the panel that the connected board should represent.",
        ).grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 8))

        search_var = tk.StringVar()
        search_frame = ttk.Frame(dialog, style="Card.TFrame")
        search_frame.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 8))
        search_frame.columnconfigure(1, weight=1)
        ttk.Label(search_frame, text="Search").grid(row=0, column=0, padx=(0, 8))
        search_entry = ttk.Entry(search_frame, textvariable=search_var)
        search_entry.grid(row=0, column=1, sticky="ew")

        table_frame = ttk.Frame(dialog, style="Card.TFrame")
        table_frame.grid(row=2, column=0, sticky="nsew", padx=14, pady=(0, 10))
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        tree = ttk.Treeview(
            table_frame,
            columns=("panel", "side", "channel", "address"),
            show="headings",
            selectmode="browse",
        )
        tree.heading("panel", text="Panel")
        tree.heading("side", text="Side / variant")
        tree.heading("channel", text="Channel")
        tree.heading("address", text="Address")
        tree.column("panel", width=330, anchor="w")
        tree.column("side", width=120, anchor="center")
        tree.column("channel", width=75, anchor="center")
        tree.column("address", width=90, anchor="center")
        tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=scroll.set)

        item_to_panel: dict[str, PanelDefinition] = {}

        def populate(*_args) -> None:
            query = search_var.get().strip().lower()
            tree.delete(*tree.get_children())
            item_to_panel.clear()
            first_item = ""
            detected_item = ""
            for candidate in candidates:
                if query and query not in panel_assignment_search_text(aircraft, candidate):
                    continue
                item_id = tree.insert(
                    "",
                    tk.END,
                    values=(
                        candidate.name,
                        panel_side_label(aircraft, candidate),
                        "" if candidate.channel is None else candidate.channel,
                        candidate.address,
                    ),
                )
                item_to_panel[item_id] = candidate
                first_item = first_item or item_id
                if self.detected_panel and candidate.name == self.detected_panel.name:
                    detected_item = item_id
            selected_item = detected_item or first_item
            if selected_item:
                tree.selection_set(selected_item)
                tree.focus(selected_item)
                tree.see(selected_item)

        selected: dict[str, PanelDefinition | None] = {"panel": None}

        def accept() -> None:
            selection = tree.selection()
            if not selection:
                return
            selected["panel"] = item_to_panel.get(selection[0])
            dialog.destroy()

        def cancel() -> None:
            dialog.destroy()

        button_frame = ttk.Frame(dialog, style="Card.TFrame")
        button_frame.grid(row=3, column=0, sticky="e", padx=14, pady=(0, 14))
        ttk.Button(button_frame, text="Cancel", command=cancel, style="Secondary.TButton").grid(
            row=0, column=0, padx=(0, 8)
        )
        ttk.Button(button_frame, text="Assign address", command=accept, style="Primary.TButton").grid(
            row=0, column=1
        )

        search_var.trace_add("write", populate)
        tree.bind("<Double-Button-1>", lambda _event: accept())
        dialog.bind("<Return>", lambda _event: accept())
        dialog.bind("<Escape>", lambda _event: cancel())
        dialog.protocol("WM_DELETE_WINDOW", cancel)
        populate()
        dialog.grab_set()
        search_entry.focus_set()
        self.wait_window(dialog)
        return selected["panel"]

    def _assign_address_worker(self, panel: PanelDefinition) -> None:
        try:
            self.queue_log(
                f"Address assignment: {self.active_board_address} -> {panel.address} ({panel.name})"
            )
            self._send_commands_worker([f"A {panel.address}", "SAVE"])
            time.sleep(0.25)
            self._request_info_worker()
        except Exception:
            self.after(0, self.fail_address_assignment)
            raise

    def fail_address_assignment(self) -> None:
        self.pending_address_assignment = None
        self.address_assignment_running = False
        self.assign_address_button.configure(state="normal")
        self.status_var.set(self.connection_status_text)
        messagebox.showerror(
            "Address change",
            "The assignment could not be completed. Review the history and request Info again.",
        )

    def finalize_address_assignment(self, info: BoardInfo) -> None:
        panel = self.pending_address_assignment
        if not panel:
            return
        self.pending_address_assignment = None
        self.address_assignment_running = False
        self.assign_address_button.configure(state="normal")
        self.status_var.set(self.connection_status_text)
        if info.address == panel.address:
            self.log(f"Address verified: {panel.name} -> {panel.address}")
            messagebox.showinfo(
                "Current addressizada",
                f"The board confirmed address {panel.address} for {panel.name}.",
            )
            return
        received = "no response" if info.address is None else str(info.address)
        self.log(f"Address not verified: expected {panel.address}, received {received}")
        messagebox.showwarning(
            "Address not verified",
            f"Expected address {panel.address}, but Info returned: {received}.\n"
            "Do not disconnect the board until you review the command history.",
        )

    def choose_panel_candidate(
        self,
        candidates: list[PanelDefinition],
        title: str,
        message: str,
    ) -> PanelDefinition | None:
        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.transient(self)
        dialog.resizable(False, False)
        dialog.configure(background=SURFACE)
        dialog.columnconfigure(0, weight=1)

        ttk.Label(
            dialog,
            text=message,
            wraplength=460,
            justify=tk.LEFT,
        ).grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 8))

        list_frame = ttk.Frame(dialog, style="Card.TFrame")
        list_frame.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 10))
        list_frame.columnconfigure(0, weight=1)

        listbox = tk.Listbox(
            list_frame,
            exportselection=False,
            height=min(8, max(3, len(candidates))),
            width=58,
            activestyle="dotbox",
            font=(FONT, 10),
        )
        listbox.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=listbox.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        listbox.configure(yscrollcommand=scroll.set)

        for panel in candidates:
            listbox.insert(tk.END, panel.display_name)

        selected_family = self.get_selected_family_name()
        initial_index = 0
        if selected_family:
            for index, panel in enumerate(candidates):
                if panel_family_name(panel.name) == selected_family:
                    initial_index = index
                    break
        listbox.selection_set(initial_index)
        listbox.activate(initial_index)
        listbox.see(initial_index)

        selected: dict[str, PanelDefinition | None] = {"panel": None}

        def accept() -> None:
            selection = listbox.curselection()
            if not selection:
                return
            selected["panel"] = candidates[int(selection[0])]
            dialog.destroy()

        def cancel() -> None:
            dialog.destroy()

        button_frame = ttk.Frame(dialog, style="Card.TFrame")
        button_frame.grid(row=2, column=0, sticky="e", padx=14, pady=(0, 14))
        ttk.Button(button_frame, text="Cancel", command=cancel, style="Secondary.TButton").grid(row=0, column=0, padx=(0, 8))
        ttk.Button(button_frame, text="Select", command=accept, style="Primary.TButton").grid(row=0, column=1)

        listbox.bind("<Double-Button-1>", lambda _event: accept())
        dialog.bind("<Return>", lambda _event: accept())
        dialog.bind("<Escape>", lambda _event: cancel())
        dialog.protocol("WM_DELETE_WINDOW", cancel)

        dialog.update_idletasks()
        x = self.winfo_rootx() + max(0, (self.winfo_width() - dialog.winfo_width()) // 2)
        y = self.winfo_rooty() + max(0, (self.winfo_height() - dialog.winfo_height()) // 2)
        dialog.geometry(f"+{x}+{y}")
        dialog.grab_set()
        listbox.focus_set()
        self.wait_window(dialog)
        return selected["panel"]

    def set_detected_from_selection(self) -> None:
        if not self.current_aircraft:
            messagebox.showwarning(".dat file", "Load a .dat file before setting the detected panel.")
            return

        family = self.get_selected_family()
        if not family:
            messagebox.showwarning("Panel", "Select an available panel before setting it as detected.")
            return

        candidates = [test.panel for test in family.tests]
        if not candidates:
            messagebox.showwarning("Panel", "The selected panel has no available variants.")
            return

        if len(candidates) == 1:
            selected_panel = candidates[0]
        else:
            selected_panel = self.choose_panel_candidate(
                candidates,
                "Set detected panel",
                (
                    f"The {family.family_name} family has multiple variants. "
                    "Select which one is connected to use the exact test."
                ),
            )

        if not selected_panel:
            return

        self.detected_panel = selected_panel
        self.select_panel(selected_panel)
        self.log(f"Detected panel set manually: {selected_panel.display_name}")

    def format_board_info(self, info: BoardInfo) -> str:
        fields = []
        if info.channel is not None:
            fields.append(f"channel {info.channel}")
        if info.address is not None:
            fields.append(f"address {info.address}")
        if info.firmware:
            fields.append(f"fw {info.firmware}")
        if info.hardware:
            fields.append(f"hw {info.hardware}")
        if info.baud_rate is not None:
            fields.append(f"baud {info.baud_rate}")
        if info.bus_status:
            fields.append(f"bus {info.bus_status}")
        if not fields:
            return "Board: response received with no recognized fields"
        return f"Board: {', '.join(fields)}"

    def select_panel(self, panel: PanelDefinition) -> None:
        family_name = panel_family_name(panel.name)
        for item_id, item_family in self.tree_item_to_family.items():
            if item_family == family_name:
                self.panel_tree.selection_set(item_id)
                self.panel_tree.focus(item_id)
                self.on_panel_changed()
                self.detected_var.set(f"{panel.display_name}")
                self.log(f"Detected panel: {panel.display_name}")
                return

        self.search_var.set("")
        self.populate_panels()
        for item_id, item_family in self.tree_item_to_family.items():
            if item_family == family_name:
                self.panel_tree.selection_set(item_id)
                self.panel_tree.focus(item_id)
                self.on_panel_changed()
                self.detected_var.set(f"{panel.display_name}")
                self.log(f"Detected panel: {panel.display_name}")
                return
        self.log(f"Detected panel has no available tests: {panel.display_name}")

    def turn_lights_on(self) -> None:
        test = self.require_selected_test()
        if test:
            self.send_commands(test.on_commands)

    def turn_lights_off(self) -> None:
        test = self.require_selected_test()
        if test:
            self.send_commands(test.off_commands)

    def run_auto_test(self) -> None:
        if self.auto_test_running:
            messagebox.showwarning("Automatic test", "An automatic test is already running.")
            return
        test = self.require_selected_test()
        if not test:
            return
        try:
            seconds = float(self.duration_var.get())
        except (TypeError, ValueError):
            messagebox.showerror("Time", "Time must be numeric.")
            return
        seconds = max(0.1, seconds)
        auto_off = bool(self.auto_off_var.get())
        self.auto_test_stop_event.clear()
        self.auto_test_running = True
        self.update_auto_test_controls()
        self.run_worker("auto-test", lambda: self._auto_test_worker(test, seconds, auto_off))

    def _auto_test_worker(self, test: PanelLightTest | PanelFamilyLightTest, seconds: float, auto_off: bool) -> None:
        try:
            self.queue_log(f"Automatic test started for {seconds:.1f} s")
            self._send_commands_worker(test.on_commands)
            stopped = self.auto_test_stop_event.wait(seconds)
            if stopped:
                self.queue_log("Automatic test stopped by the user")
                return
            if auto_off:
                self._send_commands_worker(test.off_commands)
                self.queue_log("Automatic test finished: OFF sent")
            else:
                self.queue_log("Automatic test finished: automatic shutdown skipped")
        finally:
            self.auto_test_running = False
            self.auto_test_stop_event.clear()
            self.after(0, self.update_auto_test_controls)

    def stop_auto_test_and_turn_off(self) -> None:
        test = self.require_selected_test()
        if not test:
            return
        if self.auto_test_running:
            self.auto_test_stop_event.set()
        self.run_worker("stop-off", lambda: self._stop_and_off_worker(test))

    def _stop_and_off_worker(self, test: PanelLightTest | PanelFamilyLightTest) -> None:
        self.queue_log("Stop and turn off: OFF sent to the selected panel")
        self._send_commands_worker(test.off_commands)

    def update_auto_test_controls(self) -> None:
        if self.auto_test_running:
            self.auto_test_button.configure(state="disabled")
            self.status_var.set("Automatic test running")
        else:
            self.auto_test_button.configure(state="normal")
            self.status_var.set(self.connection_status_text)

    def send_custom_command(self) -> None:
        command = self.custom_command_var.get().strip()
        if not command:
            return
        if not self.confirm_risky_custom_command(command):
            return
        if self.input_monitor_running:
            self.input_command_queue.put(command)
        else:
            self.send_commands([command])
        self.custom_command_var.set("")

    def confirm_risky_custom_command(self, command: str) -> bool:
        first_token = command.split(maxsplit=1)[0].upper()
        risky_commands = {
            "A",
            "ADDRESS",
            "BAUD",
            "CARDTYPE",
            "DECREMENT",
            "INC_DEC",
            "INCREMENT",
            "INIT_VIDEO_EEPROM",
            "IVE",
            "MOTOR",
            "MOTOR_MAX",
            "MOTOR_MIN",
            "NVI",
            "NVRAM_INIT",
            "PROG",
            "RESET",
            "SAVE",
            "TYPE",
            "WR",
            "WRITE_REGISTER",
        }
        if first_token not in risky_commands:
            return True
        return messagebox.askyesno(
            "Confirm command",
            f"The command '{first_token}' may change configuration or memory, or move hardware.\n\n"
            f"Send exactly:\n{command}",
        )

    def require_selected_test(self) -> PanelLightTest | PanelFamilyLightTest | None:
        if not self.current_aircraft:
            messagebox.showwarning(".dat file", "Load a .dat file before running a test.")
            return None
        test = self.get_selected_test_target()
        if not test:
            messagebox.showwarning("Panel", "Select an available panel to test.")
            return None
        if not test.on_commands:
            messagebox.showwarning(
                "Lights",
                "The selected panel has no light commands with the current filter. "
                "Use Input details or Output details to review other available tests.",
            )
            return None
        if not self.serial_connection.is_open:
            messagebox.showwarning("Connection", "Connect a serial port first.")
            return None
        if not self.confirm_detected_panel_matches_selection(test):
            return None
        if not self.confirm_direct_mode_ready():
            return None
        return test

    def confirm_detected_panel_matches_selection(self, test: PanelLightTest | PanelFamilyLightTest) -> bool:
        if test_target_includes_panel(test, self.detected_panel):
            return True

        detected = self.detected_panel.display_name if self.detected_panel else "Not detected"
        selected = self.result_label_for_test(test)
        confirmed = messagebox.askyesno(
            "Detected panel mismatch",
            "The panel detected with Info does not match the selected panel.\n\n"
            f"Detected: {detected}\n"
            f"Selected: {selected}\n\n"
            "Send commands to the selected panel anyway?",
        )
        if confirmed:
            self.log(f"Warning accepted: detected {detected}; selected {selected}")
        return confirmed

    def send_commands(self, commands: list[str]) -> None:
        if not self.require_serial_direct_mode():
            return
        self.run_worker("send", lambda: self._send_commands_worker(commands))

    def require_serial_direct_mode(self) -> bool:
        if not self.serial_connection.is_open:
            messagebox.showwarning("Connection", "Connect a serial port first.")
            return False
        return self.confirm_direct_mode_ready()

    def confirm_direct_mode_ready(self) -> bool:
        if self.direct_mode_confirmed:
            return True
        confirmed = messagebox.askyesno(
            "Direct Mode",
            "Confirm that Sim Host is downloaded before sending direct commands.\n\n"
            "The app does not control or verify the state of Sim Host.",
        )
        self.direct_mode_confirmed = confirmed
        return confirmed

    def _send_commands_worker(self, commands: list[str]) -> None:
        newline = self.newline_var.get()
        command_delay = self.command_delay_seconds()
        wait_seconds, quiet_seconds = self.response_timing()
        with self.serial_lock:
            for command in commands:
                self.serial_connection.send_line(command, newline)
                self.record_serial_trace_bytes("TX", "command", line_payload(command, newline))
                self.queue_log(f"> {command}")
                if command_delay > 0:
                    time.sleep(command_delay)
                response = self.serial_connection.read_until_quiet(wait_seconds, quiet_seconds)
                if response:
                    self.record_serial_trace_text("RX", "command", response)
                if response.strip():
                    self.queue_log(response.strip())
                else:
                    self.queue_log(f"No response to command {command} ({wait_seconds:.2f} s)")
                self.record_command_event(command, response.strip())

    def start_input_monitor(self) -> None:
        if self.input_monitor_running:
            messagebox.showwarning("Inputs", "Input monitoring is already running.")
            return
        if not self.require_serial_direct_mode():
            return
        self.input_monitor_stop_event.clear()
        self.input_word_values.clear()
        self.input_monitor_running = True
        self.update_input_monitor_controls()
        self.log("Input monitor: VER 3 baseline reset")
        self.log_input_monitor_context()
        self.run_worker("input-monitor", self._input_monitor_worker)

    def log_input_monitor_context(self) -> None:
        if not self.current_aircraft:
            return
        signals = input_signals_for_panels(self.current_aircraft, self.input_decode_panel_names())
        analog_words = sorted({signal.word for signal in signals if signal.signal_type == "FLOAT-FLD"})
        if not analog_words:
            return
        words = ", ".join(f"w{word}" for word in analog_words)
        message = (
            f"Analog inputs defined in {words}. If they do not appear in VER 3, "
            "check sensitivity with ANALOG from the custom command field."
        )
        self.queue_log(message)
        self.queue_input_console("warning", message)

    def _input_monitor_worker(self) -> None:
        newline = self.newline_var.get()
        line_buffer = SerialLineBuffer()
        last_rx_at = time.monotonic()
        try:
            with self.serial_lock:
                self.serial_connection.send_line("VER 3", newline)
                self.record_serial_trace_bytes("TX", "input-monitor", line_payload("VER 3", newline))
            self.queue_log("> VER 3")
            self.queue_input_console("tx", "VER 3")
            self.record_command_event("VER 3", "", status=COMMAND_STATUS_STARTED)
            self.queue_log("Input monitoring started")
            while not self.input_monitor_stop_event.is_set():
                self.send_queued_monitor_commands(newline)
                with self.serial_lock:
                    response = self.serial_connection.read_available()
                if response:
                    last_rx_at = time.monotonic()
                    self.record_serial_trace_text("RX", "input-monitor", response)
                    for line in line_buffer.feed(response):
                        self.process_input_monitor_line(line)
                elif line_buffer.pending and time.monotonic() - last_rx_at >= 0.25:
                    for line in line_buffer.flush():
                        self.process_input_monitor_line(line)
                self.input_monitor_stop_event.wait(0.1)
        finally:
            for line in line_buffer.flush():
                self.process_input_monitor_line(line)
            self.input_monitor_running = False
            self.input_monitor_stop_event.clear()
            self.after(0, self.update_input_monitor_controls)
            self.queue_log("Input monitoring stopped")
            self.queue_input_console("warning", "Monitor stopped; VER 0 was not sent because it still requires hardware validation.")

    def send_queued_monitor_commands(self, newline: str) -> None:
        while True:
            try:
                command = self.input_command_queue.get_nowait()
            except queue.Empty:
                return
            with self.serial_lock:
                self.serial_connection.send_line(command, newline)
                self.record_serial_trace_bytes("TX", "input-terminal", line_payload(command, newline))
            self.queue_log(f"> {command}")
            self.queue_input_console("tx", command)
            self.record_command_event(command, "Sent during VER 3 monitoring", status=COMMAND_STATUS_OK)

    def process_input_monitor_line(self, line: str) -> None:
        clean_line = line.strip()
        if not clean_line:
            return
        self.queue_log(clean_line)
        self.queue_input_console("rx", clean_line)
        decoded_lines = self.decode_ver3_response(clean_line)
        for decoded_line in decoded_lines:
            self.queue_log(decoded_line)
            lower_line = decoded_line.lower()
            kind = "warning" if "no " in lower_line or "inferred reversed" in lower_line else "decoded"
            self.queue_input_console(kind, decoded_line)
        self.record_command_event("VER 3 response", clean_line)

    def decode_ver3_response(self, response: str) -> list[str]:
        if not self.current_aircraft:
            return []

        updates = parse_ver3_word_values(response)
        if not updates:
            return []

        panel_names = self.input_decode_panel_names()
        signals = input_signals_for_panels(self.current_aircraft, panel_names)
        lines: list[str] = []
        for update in updates:
            previous_value = self.input_word_values.get(update.word)
            lines.extend(format_ver3_decoded_lines(update, signals, previous_value))
            self.record_decoded_input_update(update, signals, previous_value)
            self.input_word_values[update.word] = update.value
        return lines

    def record_decoded_input_update(self, update, signals, previous_value: int | None) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        decoded_items, mirrored = decode_input_update_with_fallback(update, signals, previous_value)
        if previous_value is None:
            self.append_input_history_event(self.input_history_word_event(timestamp, "baseline", update, previous_value))
            for item in decoded_items:
                if item.raw_value != 0:
                    self.append_input_history_event(
                        self.input_history_signal_event(timestamp, "baseline_signal", update, previous_value, item)
                    )
            return

        if previous_value == update.value:
            return

        changed_items = [item for item in decoded_items if item.changed]
        if not changed_items:
            self.append_input_history_event(
                self.input_history_word_event(timestamp, "unmapped_change", update, previous_value)
            )
            return

        for item in changed_items:
            self.append_input_history_event(
                self.input_history_signal_event(
                    timestamp,
                    "changed_mirrored" if mirrored else "changed",
                    update,
                    previous_value,
                    item,
                )
            )

    def show_input_event_help(self) -> None:
        messagebox.showinfo(
            "Input events",
            "baseline: first reading received for a word; establishes the reference.\n\n"
            "baseline_signal: active signal found in that first reading.\n\n"
            "changed: a later reading changed and matches a CI signal from the .dat file.\n\n"
            "unmapped_change: bits changed, but no CI signal from the selected panel uses that mask.",
        )

    def append_input_history_event(self, event: dict[str, str]) -> None:
        self.input_history.append(event)
        self.input_view_queue.put(("event", dict(event)))

    def input_history_word_event(self, timestamp: str, event: str, update, previous_value: int | None) -> dict[str, str]:
        changed_mask = "" if previous_value is None else f"{previous_value ^ update.value:04x}"
        unmapped_signal = f"No CI signal for mask {changed_mask}" if event == "unmapped_change" else ""
        return {
            "time": timestamp,
            "event": event,
            "word": f"w{update.word}",
            "previous_word_value": "" if previous_value is None else f"{previous_value:04x}",
            "word_value": f"{update.value:04x}",
            "changed_mask": changed_mask,
            "panel": "",
            "signal": unmapped_signal,
            "signal_type": "",
            "bits": "",
            "flags": "",
            "previous_raw": "",
            "raw": "",
            "previous_logical": "",
            "logical": "",
            "comment": "",
            "raw_line": update.raw_line,
        }

    def input_history_signal_event(
        self,
        timestamp: str,
        event: str,
        update,
        previous_value: int | None,
        item: DecodedInputSignal,
    ) -> dict[str, str]:
        signal = item.signal
        return {
            "time": timestamp,
            "event": event,
            "word": f"w{update.word}",
            "previous_word_value": "" if previous_value is None else f"{previous_value:04x}",
            "word_value": f"{update.value:04x}",
            "changed_mask": "" if previous_value is None else f"{previous_value ^ update.value:04x}",
            "panel": signal.panel_name,
            "signal": signal.name,
            "signal_type": signal.signal_type,
            "bits": signal.bit_range,
            "flags": signal_flags_text(signal),
            "previous_raw": "" if item.previous_raw_value is None else str(item.previous_raw_value),
            "raw": str(item.raw_value),
            "previous_logical": "" if item.previous_logical_value is None else str(item.previous_logical_value),
            "logical": str(item.logical_value),
            "comment": signal.comment,
            "raw_line": update.raw_line,
        }

    def input_decode_panel_names(self) -> list[str] | None:
        if self.detected_panel:
            return [self.detected_panel.name]

        selected = self.get_selected_test_target()
        if isinstance(selected, PanelLightTest):
            return [selected.panel.name]
        if isinstance(selected, PanelFamilyLightTest):
            return selected.variant_names
        return None

    def stop_input_monitor(self) -> None:
        if self.input_monitor_running:
            self.input_monitor_stop_event.set()
        else:
            self.log("Input monitoring is not running")

    def reset_panel(self) -> None:
        if not self.require_serial_direct_mode():
            return
        if self.input_monitor_running:
            self.input_monitor_stop_event.set()
        self.run_worker("reset", lambda: self._send_commands_worker(["reset"]))

    def send_display_text(self) -> None:
        word_text = self.display_word_var.get().strip()
        display_text = self.display_text_var.get().strip()
        if not word_text:
            messagebox.showwarning("Display", "Enter the first display word.")
            return
        if not display_text:
            messagebox.showwarning("Display", "Enter the text or number to send to the display.")
            return
        try:
            word = int(word_text, 10)
        except ValueError:
            messagebox.showerror("Display", "The word must be a decimal number.")
            return
        if word < 0:
            messagebox.showerror("Display", "The word cannot be negative.")
            return
        self.send_direct_command(f"S {word} {display_text}")

    def display_test_panel_names(self, *, show_warning: bool = True) -> list[str] | None:
        if self.detected_panel:
            return [self.detected_panel.name]
        selected = self.get_selected_test_target()
        if isinstance(selected, PanelLightTest):
            return [selected.panel.name]
        if isinstance(selected, PanelFamilyLightTest) and len(selected.variant_names) == 1:
            return selected.variant_names
        if show_warning:
            messagebox.showwarning(
                "Test display",
                "Detect the panel with Info or set an exact variant before the automatic test. "
                "Displays from multiple boards are not mixed.",
            )
        return None

    def selected_display_test_signals(self, *, show_warning: bool = True):
        if not self.current_aircraft:
            if show_warning:
                messagebox.showwarning(".dat file", "Load a .dat file before the display test.")
            return []
        panel_names = self.display_test_panel_names(show_warning=show_warning)
        if not panel_names:
            return []
        return special_output_signals_for_panels(
            self.current_aircraft,
            panel_names,
            OUTPUT_CATEGORY_DISPLAY,
        )

    def update_display_test_summary(self) -> None:
        signals = self.selected_display_test_signals(show_warning=False)
        groups = display_word_groups(signals)
        if not groups:
            self.display_test_summary_var.set("No display BIT-FLD fields compatible with S for the exact panel.")
            return
        words = ", ".join(f"w{group.word}" for group in groups)
        field_count = sum(len(group.signals) for group in groups)
        self.display_test_summary_var.set(
            f"Words S: {words} | {field_count} fields from the .dat file | 2 characters per word to avoid overlap."
        )

    def start_display_test(self) -> None:
        if self.display_test_running:
            messagebox.showwarning("Display test", "The automatic display test is already running.")
            return
        if self.auto_test_running:
            messagebox.showwarning("Display test", "Wait for the automatic light test to finish.")
            return
        if self.input_monitor_running:
            messagebox.showwarning("Test display", "Stop the VER 3 monitor before testing the display.")
            return
        signals = self.selected_display_test_signals()
        groups = display_word_groups(signals)
        if not groups:
            messagebox.showwarning(
                "Test display",
                "The panel has no 7- or 8-bit display BIT-FLD fields compatible with the S command.",
            )
            return
        characters = normalize_display_sweep_characters(self.display_sweep_var.get())
        if not characters:
            messagebox.showwarning("Test display", "Enter at least one ASCII alphanumeric character in the sequence.")
            return
        try:
            step_seconds = float(self.display_step_var.get())
        except (tk.TclError, ValueError):
            messagebox.showerror("Display test", "Step time must be numeric.")
            return
        if step_seconds < 0.1 or step_seconds > 10.0:
            messagebox.showerror("Display test", "Step time must be between 0.1 and 10 seconds.")
            return
        if not self.require_serial_direct_mode():
            return

        frames = build_display_sweep_frames(signals, characters)
        restore = bool(self.display_restore_var.get())
        self.display_test_stop_event.clear()
        self.display_test_running = True
        self.update_display_test_controls()
        words = ", ".join(f"w{group.word}" for group in groups)
        self.log(f"Display test started: {words}; sequence {characters}")
        self.run_worker(
            "display-test",
            lambda: self._display_test_worker(frames, groups, step_seconds, restore),
        )

    def display_step_seconds_for_report(self) -> float:
        try:
            return float(self.display_step_var.get())
        except (tk.TclError, ValueError):
            return 0.6

    def _display_test_worker(self, frames, groups, step_seconds: float, restore: bool) -> None:
        stopped = False
        try:
            for frame in frames:
                if self.display_test_stop_event.is_set():
                    stopped = True
                    break
                self.queue_log(f"Display: {frame.label}")
                self._send_commands_worker(list(frame.commands))
                if self.display_test_stop_event.wait(step_seconds):
                    stopped = True
                    break
            if restore and self.serial_connection.is_open:
                self.queue_log("Display: restoring 00")
                self._send_commands_worker([f"S {group.word} 00" for group in groups])
            self.queue_log("Display test stopped" if stopped else "Display test finished")
        finally:
            self.display_test_running = False
            self.display_test_stop_event.clear()
            self.after(0, self.update_display_test_controls)

    def stop_display_test(self) -> None:
        if not self.display_test_running:
            self.log("The automatic display test is not running")
            return
        self.display_test_stop_event.set()
        self.log("Display test stop requested")

    def update_display_test_controls(self) -> None:
        if self.display_test_running:
            self.display_test_button.configure(state="disabled")
            self.stop_display_test_button.configure(state="normal")
            self.status_var.set("Automatic display test running")
        else:
            self.display_test_button.configure(state="normal")
            self.stop_display_test_button.configure(state="disabled")
            if not self.auto_test_running and not self.input_monitor_running:
                self.status_var.set(self.connection_status_text)

    def send_demo_command(self) -> None:
        self.send_direct_command("demo")

    def send_st_command(self) -> None:
        self.send_direct_command("ST")

    def send_brushless_st_command(self) -> None:
        self.send_direct_command("ST_Brushless")

    def send_direct_command(self, command: str) -> None:
        if self.input_monitor_running:
            self.input_monitor_stop_event.set()
        self.send_commands([command])

    def update_input_monitor_controls(self) -> None:
        if self.input_monitor_running:
            self.input_monitor_button.configure(state="disabled")
            self.stop_input_monitor_button.configure(state="normal")
            self.status_var.set("Input monitoring running")
        else:
            self.input_monitor_button.configure(state="normal")
            self.stop_input_monitor_button.configure(state="normal")
            if not self.auto_test_running:
                self.status_var.set(self.connection_status_text)

    def run_worker(self, name: str, target) -> None:
        def guarded() -> None:
            try:
                target()
            except Exception as exc:  # noqa: BLE001 - surfaced to operator.
                self.queue_log(f"Error in {name}: {exc}")

        threading.Thread(target=guarded, daemon=True).start()

    def record_command_event(self, command: str, response: str = "", status: str | None = None) -> None:
        clean_response = response.strip()
        command_status = status or (COMMAND_STATUS_OK if clean_response else COMMAND_STATUS_NO_RESPONSE)
        self.command_history.append(
            {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "status": command_status,
                "command": command,
                "response": clean_response,
            }
        )

    def clear_command_history(self) -> None:
        self.command_history.clear()
        self.log("Command history cleared")

    def read_raw_serial_window(self) -> None:
        if not self.serial_connection.is_open:
            messagebox.showwarning("Connection", "Connect a serial port first.")
            return
        if self.input_monitor_running:
            messagebox.showwarning("Serial diagnostics", "Stop input monitoring before reading raw data.")
            return
        seconds = self.diagnostic_seconds()
        self.run_worker("diagnostic-read", lambda: self._read_raw_serial_window_worker(seconds))

    def _read_raw_serial_window_worker(self, seconds: float) -> None:
        self.queue_log(f"Raw reading started for {seconds:.1f} s")
        self.after(0, lambda: self.status_var.set("Serial diagnostics running"))
        deadline = time.monotonic() + seconds
        captured_bytes = 0
        captured_chunks = 0
        try:
            while time.monotonic() < deadline:
                with self.serial_lock:
                    data = self.serial_connection.read_available_bytes()
                if data:
                    captured_bytes += len(data)
                    captured_chunks += 1
                    event = self.record_serial_trace_bytes("RX", "diagnostic-read", data)
                    self.queue_log(f"RX crudo: {event.text}")
                time.sleep(0.03)
        finally:
            self.queue_log(
                f"Raw reading finished: {captured_chunks} blocks, {captured_bytes} bytes"
            )
            self.after(0, lambda: self.status_var.set(self.connection_status_text))

    def record_serial_trace_bytes(self, direction: str, source: str, data: bytes) -> SerialTraceEvent:
        event = make_serial_trace_event(
            datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            direction,
            source,
            data,
        )
        with self.serial_trace_lock:
            self.append_serial_trace_event_locked(event)
        return event

    def record_serial_trace_text(self, direction: str, source: str, text: str) -> SerialTraceEvent:
        event = make_serial_trace_event(
            datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            direction,
            source,
            text,
        )
        with self.serial_trace_lock:
            self.append_serial_trace_event_locked(event)
        return event

    def append_serial_trace_event_locked(self, event: SerialTraceEvent) -> None:
        self.serial_trace_events.append(event)
        removed_count = trim_serial_trace_events(self.serial_trace_events, SERIAL_TRACE_MAX_EVENTS)
        if not removed_count:
            return

        self.serial_trace_discarded_count += removed_count
        if not self.serial_trace_limit_notice_shown:
            self.serial_trace_limit_notice_shown = True
            self.queue_log(
                f"Serial trace limited to the latest {SERIAL_TRACE_MAX_EVENTS} events; "
                "older events will be discarded."
            )

    def clear_serial_trace_log(self) -> None:
        with self.serial_trace_lock:
            count = len(self.serial_trace_events)
            self.serial_trace_events.clear()
            discarded_count = self.serial_trace_discarded_count
            self.serial_trace_discarded_count = 0
            self.serial_trace_limit_notice_shown = False
        if discarded_count:
            self.log(f"Serial log cleared ({count} events, {discarded_count} old discarded)")
        else:
            self.log(f"Serial log cleared ({count} events)")

    def save_serial_trace_log(self) -> None:
        with self.serial_trace_lock:
            events = list(self.serial_trace_events)
        if not events:
            messagebox.showwarning("Serial diagnostics", "There are no serial events to save.")
            return

        diagnostics_dir = Path.cwd() / "Diagnostics"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        trace_path = diagnostics_dir / f"serial_trace_{timestamp}.txt"
        try:
            write_serial_trace_log(trace_path, events, self.serial_trace_metadata())
        except OSError as exc:
            messagebox.showerror("Serial diagnostics", f"Could not save the serial log:\n{exc}")
            return
        self.log(f"Log serial saved: {trace_path}")
        messagebox.showinfo("Serial diagnostics", f"Serial log saved to:\n{trace_path}")

    def serial_trace_metadata(self) -> dict[str, str]:
        with self.serial_trace_lock:
            trace_events_kept = len(self.serial_trace_events)
            trace_events_discarded = self.serial_trace_discarded_count
        return {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "port": self.selected_serial_device() or "No port",
            "baud_rate": self.baud_var.get(),
            "newline": self.newline_var.get(),
            "response_wait_seconds": f"{self.response_wait_seconds():.2f}",
            "response_quiet_seconds": f"{self.response_quiet_seconds():.2f}",
            "command_delay_seconds": f"{self.command_delay_seconds():.2f}",
            "diagnostic_seconds": f"{self.diagnostic_seconds():.2f}",
            "trace_events_kept": str(trace_events_kept),
            "trace_event_limit": str(SERIAL_TRACE_MAX_EVENTS),
            "trace_events_discarded": str(trace_events_discarded),
            "dat_path": str(self.current_aircraft.path) if self.current_aircraft else self.dat_path_var.get(),
            "panel": self.selected_panel_label(),
            "detected_panel": self.detected_panel_label(),
        }

    def save_session(self) -> None:
        if not self.current_aircraft:
            messagebox.showwarning("Session", "Load a .dat file before saving a session.")
            return
        self.store_current_panel_result(refresh_table=True)
        sessions_dir = Path.cwd() / "Sessions"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_path = sessions_dir / f"interface_session_{timestamp}.json"
        try:
            save_test_session(self.build_test_session(), session_path)
        except OSError as exc:
            messagebox.showerror("Session", f"Could not save the session:\n{exc}")
            return
        self.log(f"Session guardada: {session_path}")
        messagebox.showinfo("Session", f"Session saved to:\n{session_path}")

    def choose_session_file(self) -> None:
        sessions_dir = Path.cwd() / "Sessions"
        initial_dir = sessions_dir if sessions_dir.exists() else Path.cwd()
        selected = filedialog.askopenfilename(
            title="Load test session",
            initialdir=initial_dir,
            filetypes=(("Interface Tester session", "*.json"), ("All files", "*.*")),
        )
        if selected:
            self.load_session_file(Path(selected))

    def load_session_file(self, path: Path) -> bool:
        try:
            session = load_test_session(path)
        except ValueError as exc:
            messagebox.showerror("Session", str(exc))
            return False

        dat_path = Path(session.dat_path) if session.dat_path else None
        if not dat_path or not dat_path.exists():
            messagebox.showerror(
                "Session",
                "The session references a .dat file that does not exist on this machine:\n"
                f"{session.dat_path or 'No path'}",
            )
            return False

        self.apply_test_session(session)
        self.log(f"Session cargada: {path}")
        return True

    def build_test_session(self) -> TestSession:
        try:
            duration_seconds = float(self.duration_var.get())
        except (TypeError, ValueError, tk.TclError):
            duration_seconds = 1.0

        with self.serial_trace_lock:
            serial_trace_events = list(self.serial_trace_events)
            serial_trace_discarded_count = self.serial_trace_discarded_count

        return TestSession(
            saved_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            dat_path=str(self.current_aircraft.path) if self.current_aircraft else "",
            aircraft_name=self.current_aircraft.name if self.current_aircraft else "",
            panel_results=dict(self.panel_results),
            command_history=[dict(event) for event in self.command_history],
            input_history=[dict(event) for event in self.input_history],
            input_word_values=dict(self.input_word_values),
            serial_trace_events=serial_trace_events,
            serial_trace_discarded_count=serial_trace_discarded_count,
            report_result=self.report_result_var.get(),
            report_comment=self.report_comment_var.get(),
            current_result_key=self.current_result_key or "",
            detected_panel_name=self.detected_panel.name if self.detected_panel else "",
            board_info_text=self.board_info_var.get(),
            light_filter=self.current_light_filter(),
            output_filter=self.current_output_filter(),
            intensity_mode=self.current_intensity_mode(),
            duration_seconds=max(0.1, duration_seconds),
            response_wait_seconds=self.response_wait_seconds(),
            response_quiet_seconds=self.response_quiet_seconds(),
            command_delay_seconds=self.command_delay_seconds(),
            diagnostic_seconds=self.diagnostic_seconds(),
            auto_off=bool(self.auto_off_var.get()),
            display_word=self.display_word_var.get().strip() or "38",
            display_text=self.display_text_var.get().strip(),
        )

    def apply_test_session(self, session: TestSession) -> None:
        self.set_modes_from_session(session)
        loaded = self.load_dat_file(Path(session.dat_path), show_errors=True)
        if not loaded:
            return

        self.panel_results = dict(session.panel_results)
        self.command_history = [dict(event) for event in session.command_history]
        self.input_history = [dict(event) for event in session.input_history]
        self.input_word_values = dict(session.input_word_values)
        self.refresh_input_monitor_view()
        with self.serial_trace_lock:
            self.serial_trace_events = list(session.serial_trace_events)
            self.serial_trace_discarded_count = session.serial_trace_discarded_count
            self.serial_trace_limit_notice_shown = bool(session.serial_trace_discarded_count)
        self.report_result_var.set(session.report_result if session.report_result in RESULT_OPTIONS else RESULT_NOT_TESTED)
        self.report_comment_var.set(session.report_comment)
        self.duration_var.set(max(0.1, session.duration_seconds))
        self.response_wait_var.set(max(0.05, session.response_wait_seconds))
        self.response_quiet_var.set(max(0.0, session.response_quiet_seconds))
        self.command_delay_var.set(max(0.0, session.command_delay_seconds))
        self.diagnostic_seconds_var.set(max(0.1, session.diagnostic_seconds))
        self.auto_off_var.set(session.auto_off)
        self.display_word_var.set(session.display_word or "38")
        self.display_text_var.set(session.display_text)
        self.board_info_var.set(session.board_info_text or "Board: no information")
        self.restore_detected_panel(session.detected_panel_name)
        self.current_result_key = None
        self.current_result_label = ""
        self.populate_panels()
        self.restore_session_panel_selection(session.current_result_key)
        self.refresh_panel_result_cells()
        self.update_report_summary()
        self.log(
            f"Session restored: {len(self.panel_results)} results, "
            f"{len(self.command_history)} command events, "
            f"{len(self.input_history)} input events, "
            f"{len(session.serial_trace_events)} events seriales"
            f"{self.serial_trace_discarded_session_text(session)}."
        )

    def set_modes_from_session(self, session: TestSession) -> None:
        intensity_label = INTENSITY_MODE_LABELS.get(session.intensity_mode)
        light_filter_label = LIGHT_FILTER_LABELS.get(session.light_filter)
        output_filter_label = OUTPUT_CATEGORY_FILTER_LABELS.get(session.output_filter)
        if intensity_label:
            self.intensity_mode_var.set(intensity_label)
        if light_filter_label:
            self.light_filter_var.set(light_filter_label)
        if output_filter_label:
            self.output_filter_var.set(output_filter_label)

    def restore_session_panel_selection(self, result_key: str) -> None:
        if not result_key:
            return
        if self.select_result_key(result_key):
            return

        filters_changed = False
        if self.search_var.get().strip():
            self.search_var.set("")
            filters_changed = True
        if self.result_filter_var.get() != RESULT_FILTER_ALL:
            self.result_filter_var.set(RESULT_FILTER_ALL)
            filters_changed = True

        if filters_changed:
            self.populate_panels()
            if self.select_result_key(result_key):
                self.log(f"Panel filters cleared to restore session selection: {result_key}")
                return

        self.log(f"Session selection is not available in the current .dat file: {result_key}")

    def restore_detected_panel(self, panel_name: str) -> None:
        self.detected_panel = None
        if not self.current_aircraft or not panel_name:
            self.detected_var.set("Not detected")
            return

        panel = self.current_aircraft.panels.get(panel_name)
        if not panel:
            self.detected_var.set("Not detected")
            self.log(f"The session detected panel does not exist in the current .dat file: {panel_name}")
            return

        self.detected_panel = panel
        self.detected_var.set(panel.display_name)

    def select_result_key(self, result_key: str) -> bool:
        if not result_key:
            return False

        family_name = result_key
        if self.current_aircraft and result_key in self.current_aircraft.panels:
            family_name = panel_family_name(result_key)

        return self.select_family_name(family_name)

    def save_report(self) -> None:
        reports_dir = Path.cwd() / "Reports"
        reports_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = reports_dir / f"interface_test_{timestamp}.md"
        report_generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        report_path.write_text(self.build_report_text(report_generated_at), encoding="utf-8")
        results_path, commands_path, inputs_path = write_report_csvs(
            report_path,
            self.build_panel_result_report_rows(),
            self.command_history,
            self.input_history,
            self.report_metadata(report_generated_at),
        )
        self.log(f"Report saved: {report_path}")
        self.log(f"CSV results saved: {results_path}")
        self.log(f"CSV commands saved: {commands_path}")
        self.log(f"CSV inputs saved: {inputs_path}")
        messagebox.showinfo(
            "Report",
            "Report saved to:\n"
            f"{report_path}\n\n"
            "CSV results:\n"
            f"{results_path}\n\n"
            "CSV commands:\n"
            f"{commands_path}\n\n"
            "CSV inputs:\n"
            f"{inputs_path}",
        )

    def report_metadata(self, generated_at: str) -> dict[str, str]:
        return {
            "generated_at": generated_at,
            "aircraft": self.current_aircraft.name if self.current_aircraft else "No .dat file loaded",
            "dat_path": str(self.current_aircraft.path) if self.current_aircraft else self.dat_path_var.get(),
            "port": self.selected_serial_device() or "No port",
            "baud_rate": self.baud_var.get(),
            "newline": self.newline_var.get(),
            "board_info": self.board_info_var.get(),
            "detected_panel": self.detected_panel_label(),
            "selected_panel": self.selected_panel_label(),
            "light_filter": self.light_filter_var.get(),
            "output_filter": self.output_filter_var.get(),
            "intensity_mode": self.intensity_mode_var.get(),
            "auto_off": "Yes" if self.auto_off_var.get() else "No",
            "response_wait_seconds": f"{self.response_wait_seconds():.2f}",
            "response_quiet_seconds": f"{self.response_quiet_seconds():.2f}",
            "command_delay_seconds": f"{self.command_delay_seconds():.2f}",
            "diagnostic_seconds": f"{self.diagnostic_seconds():.2f}",
        }

    def build_report_text(self, generated_at: str | None = None) -> str:
        self.store_current_panel_result(refresh_table=True)
        now = generated_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        selected_panel = self.selected_panel_label()
        detected = self.detected_panel_label()
        aircraft = self.current_aircraft.name if self.current_aircraft else "No .dat file loaded"
        dat_path = str(self.current_aircraft.path) if self.current_aircraft else self.dat_path_var.get()
        comments = self.report_comment_var.get().strip() or "No comment"

        lines = [
            "# Interface Tester Report",
            "",
            f"- Fecha: {now}",
            f"- Version app: {__version__}",
            f"- Summary: {self.report_summary_var.get()}",
            f"- Result selected: {self.report_result_var.get()}",
            f"- Comment selected: {comments}",
            "",
            "## Definition",
            "",
            f"- File: {dat_path}",
            f"- Aircraft / proyecto: {aircraft}",
            "",
            "## Connection",
            "",
            f"- Estado: {self.connection_status_text}",
            f"- Port selected: {self.port_var.get() or 'No port'}",
            f"- Baud: {self.baud_var.get()}",
            f"- Line ending: {self.newline_var.get()}",
            f"- Board: {self.board_info_var.get()}",
            f"- Espera response: {self.response_wait_seconds():.2f} s",
            f"- Response quiet time: {self.response_quiet_seconds():.2f} s",
            f"- Command delay: {self.command_delay_seconds():.2f} s",
            f"- Secuencia test display: {normalize_display_sweep_characters(self.display_sweep_var.get())}",
            f"- Paso test display: {self.display_step_seconds_for_report():.2f} s",
            "",
            "## Panel",
            "",
            f"- Detected panel: {detected}",
            f"- Selected panel: {selected_panel}",
            f"- Light type: {self.light_filter_var.get()}",
            f"- Output category: {self.output_filter_var.get()}",
            f"- Intensity: {self.intensity_mode_var.get()}",
            f"- Turn off when finished: {'Yes' if self.auto_off_var.get() else 'No'}",
            "",
            "## Results by Panel",
            "",
        ]

        result_rows = self.build_panel_result_report_rows()
        if not result_rows:
            lines.append("No panels loaded.")
        else:
            lines.append("| Panel | Variants | Lights | Inputs | Outputs | Result | Comment | Updated |")
            lines.append("|---|---:|---:|---:|---:|---|---|---|")
            for row in result_rows:
                lines.append(
                    "| "
                    f"{markdown_cell(row['panel'])} | "
                    f"{markdown_cell(row['variants'])} | "
                    f"{markdown_cell(row.get('lights', ''))} | "
                    f"{markdown_cell(row.get('inputs', ''))} | "
                    f"{markdown_cell(row.get('outputs', ''))} | "
                    f"{markdown_cell(row['result'])} | "
                    f"{markdown_cell(row['comment'])} | "
                    f"{markdown_cell(row['updated_at'])} |"
                )

        lines.extend(
            [
                "",
                "## .dat Validation",
                "",
            ]
        )

        if not self.current_validation_report:
            lines.append("No validation available.")
        else:
            lines.append(f"- {self.current_validation_report.summary}")
            for issue in self.current_validation_report.issues:
                lines.append(f"- {issue.severity.upper()}: {issue.title}")
                for detail in issue.details[:20]:
                    lines.append(f"  - {detail}")
        lines.extend(
            [
                "",
                "## Command History",
                "",
            ]
        )

        if not self.command_history:
            lines.append("No commands recorded.")
        else:
            lines.append("| Time | Status | Command | Response |")
            lines.append("|---|---|---|---|")
            for event in self.command_history:
                response = event["response"].replace("\r", "\\r").replace("\n", "<br>")
                command = event["command"].replace("|", "\\|")
                status = event.get("status", "").replace("|", "\\|")
                response = response.replace("|", "\\|")
                lines.append(f"| {event['time']} | {status or 'No status'} | `{command}` | {response or 'No response'} |")

        lines.extend(
            [
                "",
                "## Decoded Inputs",
                "",
            ]
        )

        if not self.input_history:
            lines.append("No decoded inputs recorded.")
        else:
            lines.append("| Time | Event | Word | Value | Change | Panel | Signal | Bits | Raw | Logical |")
            lines.append("|---|---|---|---|---|---|---|---|---|---|")
            for event in self.input_history:
                raw_value = event.get("raw", "")
                previous_raw = event.get("previous_raw", "")
                logical = event.get("logical", "")
                previous_logical = event.get("previous_logical", "")
                raw_display = f"{previous_raw}->{raw_value}" if previous_raw else raw_value
                logical_display = f"{previous_logical}->{logical}" if previous_logical else logical
                lines.append(
                    "| "
                    f"{markdown_cell(event.get('time', ''))} | "
                    f"{markdown_cell(event.get('event', ''))} | "
                    f"{markdown_cell(event.get('word', ''))} | "
                    f"{markdown_cell(event.get('word_value', ''))} | "
                    f"{markdown_cell(event.get('changed_mask', ''))} | "
                    f"{markdown_cell(event.get('panel', ''))} | "
                    f"{markdown_cell(event.get('signal', ''))} | "
                    f"{markdown_cell(event.get('bits', ''))} | "
                    f"{markdown_cell(raw_display)} | "
                    f"{markdown_cell(logical_display)} |"
                )

        lines.append("")
        return "\n".join(lines)

    def selected_panel_label(self) -> str:
        selected = self.get_selected_test_target()
        if isinstance(selected, PanelLightTest):
            return selected.panel.display_name
        if isinstance(selected, PanelFamilyLightTest):
            return f"{selected.family_name} ({', '.join(selected.variant_names)})"
        return "No panel selected"

    def detected_panel_label(self) -> str:
        return self.detected_panel.display_name if self.detected_panel else "Not detected"

    def build_panel_result_report_rows(self) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for family in self.current_panel_families:
            stats = self.current_family_stats.get(family.family_name, PanelCapabilityStats())
            family_result = self.panel_results.get(family.family_name)
            if family_result and should_keep_result(family_result):
                rows.append(
                    {
                        "panel": family.family_name,
                        "variants": str(family.variant_count),
                        "lights": str(stats.light_count),
                        "light_words": str(stats.light_word_count),
                        "inputs": str(stats.input_count),
                        "input_words": str(stats.input_word_count),
                        "outputs": str(stats.output_count),
                        "output_words": str(stats.output_word_count),
                        "result": family_result.result,
                        "comment": family_result.comment,
                        "updated_at": family_result.updated_at,
                    }
                )
                continue

            variant_rows = []
            for variant_name in family.variant_names:
                panel_result = self.panel_results.get(variant_name)
                if panel_result and should_keep_result(panel_result):
                    variant_rows.append(
                        {
                            "panel": panel_result.target,
                            "variants": "1",
                            "lights": "",
                            "light_words": "",
                            "inputs": "",
                            "input_words": "",
                            "outputs": "",
                            "output_words": "",
                            "result": panel_result.result,
                            "comment": panel_result.comment,
                            "updated_at": panel_result.updated_at,
                        }
                    )

            if variant_rows:
                rows.extend(variant_rows)
                if len(variant_rows) < family.variant_count:
                    rows.append(
                        {
                            "panel": family.family_name,
                            "variants": str(family.variant_count - len(variant_rows)),
                            "lights": str(stats.light_count),
                            "light_words": str(stats.light_word_count),
                            "inputs": str(stats.input_count),
                            "input_words": str(stats.input_word_count),
                            "outputs": str(stats.output_count),
                            "output_words": str(stats.output_word_count),
                            "result": RESULT_NOT_TESTED,
                            "comment": "",
                            "updated_at": "",
                        }
                    )
                continue

            rows.append(
                {
                    "panel": family.family_name,
                    "variants": str(family.variant_count),
                    "lights": str(stats.light_count),
                    "light_words": str(stats.light_word_count),
                    "inputs": str(stats.input_count),
                    "input_words": str(stats.input_word_count),
                    "outputs": str(stats.output_count),
                    "output_words": str(stats.output_word_count),
                    "result": RESULT_NOT_TESTED,
                    "comment": "",
                    "updated_at": "",
                }
            )
        return rows

    def log_validation_report(self, report: ValidationReport) -> None:
        self.log(report.summary)
        for issue in report.issues:
            self.log(f"{issue.severity.upper()}: {issue.title}")
            for detail in issue.details[:10]:
                self.log(f"  - {detail}")
            if len(issue.details) > 10:
                self.log("  - ...")

    def log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")

    def clear_terminal_view(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state="disabled")

    def clear_input_monitor_view(self) -> None:
        if hasattr(self, "input_event_tree"):
            self.input_event_tree.delete(*self.input_event_tree.get_children())
        if hasattr(self, "input_console_text"):
            self.input_console_text.configure(state="normal")
            self.input_console_text.delete("1.0", tk.END)
            self.input_console_text.configure(state="disabled")

    def refresh_input_monitor_view(self) -> None:
        self.clear_input_monitor_view()
        for event in self.input_history[-1000:]:
            self.insert_input_event(event)

    def queue_input_console(self, kind: str, message: str) -> None:
        self.input_view_queue.put(("console", (kind, message)))

    def insert_input_console(self, kind: str, message: str) -> None:
        if not message:
            return
        tag = kind if kind in {"tx", "rx", "decoded", "warning"} else "rx"
        prefix = {"tx": "TX  ", "rx": "RX  ", "decoded": "DEC ", "warning": "!   "}.get(tag, "")
        self.input_console_text.configure(state="normal")
        self.input_console_text.insert(tk.END, f"{prefix}{message}\n", tag)
        self.input_console_text.see(tk.END)
        self.input_console_text.configure(state="disabled")

    def insert_input_event(self, event: dict[str, str]) -> None:
        raw_value = event.get("raw", "")
        previous_raw = event.get("previous_raw", "")
        logical_value = event.get("logical", "")
        previous_logical = event.get("previous_logical", "")
        signal = event.get("signal", "")
        panel = event.get("panel", "")
        signal_label = f"{panel}.{signal}" if panel and signal else signal
        event_name = event.get("event", "")
        tag = "unmapped" if event_name == "unmapped_change" else "changed" if event_name.startswith("changed") else ""
        item = self.input_event_tree.insert(
            "",
            tk.END,
            values=(
                event.get("time", "")[-8:],
                event.get("event", ""),
                event.get("word", ""),
                event.get("word_value", ""),
                event.get("changed_mask", ""),
                signal_label,
                event.get("bits", ""),
                f"{previous_raw}->{raw_value}" if previous_raw else raw_value,
                f"{previous_logical}->{logical_value}" if previous_logical else logical_value,
            ),
            tags=(tag,) if tag else (),
        )
        children = self.input_event_tree.get_children()
        if len(children) > 1000:
            self.input_event_tree.delete(children[0])
        self.input_event_tree.see(item)

    def queue_log(self, message: str) -> None:
        self.log_queue.put(message)

    def _drain_log_queue(self) -> None:
        while True:
            try:
                message = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self.log(message)
        while True:
            try:
                event_type, payload = self.input_view_queue.get_nowait()
            except queue.Empty:
                break
            if event_type == "event":
                self.insert_input_event(payload)
            elif event_type == "console":
                kind, message = payload
                self.insert_input_console(kind, message)
        self.after(100, self._drain_log_queue)

    def selected_serial_device(self) -> str:
        display = self.port_var.get().strip()
        return self.port_display_to_device.get(display, display)

    def _bounded_float_var(
        self,
        variable: tk.DoubleVar,
        default: float,
        minimum: float,
        maximum: float,
    ) -> float:
        try:
            value = float(variable.get())
        except (TypeError, ValueError, tk.TclError):
            return default
        return min(maximum, max(minimum, value))

    def response_wait_seconds(self) -> float:
        return self._bounded_float_var(self.response_wait_var, self.settings.response_wait_seconds, 0.05, 30.0)

    def response_quiet_seconds(self) -> float:
        value = self._bounded_float_var(self.response_quiet_var, self.settings.response_quiet_seconds, 0.0, 10.0)
        return min(value, self.response_wait_seconds())

    def command_delay_seconds(self) -> float:
        return self._bounded_float_var(self.command_delay_var, self.settings.command_delay_seconds, 0.0, 5.0)

    def diagnostic_seconds(self) -> float:
        return self._bounded_float_var(self.diagnostic_seconds_var, self.settings.diagnostic_seconds, 0.1, 60.0)

    def duration_seconds(self) -> float:
        return self._bounded_float_var(self.duration_var, self.settings.duration_seconds, 0.1, 30.0)

    def response_timing(self) -> tuple[float, float]:
        return self.response_wait_seconds(), self.response_quiet_seconds()

    def build_current_settings(self) -> AppSettings:
        dat_path = self.settings.last_dat_path
        if self.current_aircraft:
            dat_path = str(self.current_aircraft.path)
        else:
            displayed_dat = self.dat_path_var.get().strip()
            if displayed_dat and Path(displayed_dat).exists():
                dat_path = displayed_dat

        try:
            duration_seconds = float(self.duration_var.get())
        except (TypeError, ValueError, tk.TclError):
            duration_seconds = 1.0
        if duration_seconds <= 0:
            duration_seconds = 1.0

        return AppSettings(
            last_dat_path=dat_path,
            last_definition_dir=str(self.definition_dir),
            serial_port=self.selected_serial_device() or self.settings.serial_port,
            baud_rate=self.baud_var.get().strip() or "115200",
            newline=self.newline_var.get() if self.newline_var.get() in NEWLINES else "CR",
            intensity_mode=self.current_intensity_mode(),
            light_filter=self.current_light_filter(),
            output_filter=self.current_output_filter(),
            duration_seconds=duration_seconds,
            response_wait_seconds=self.response_wait_seconds(),
            response_quiet_seconds=self.response_quiet_seconds(),
            command_delay_seconds=self.command_delay_seconds(),
            diagnostic_seconds=self.diagnostic_seconds(),
            auto_off=bool(self.auto_off_var.get()),
            display_word=self.display_word_var.get().strip() or "38",
            display_text=self.display_text_var.get().strip(),
        )

    def save_current_settings(self) -> None:
        settings = self.build_current_settings()
        try:
            save_app_settings(settings)
        except OSError as exc:
            self.log(f"Could not save the configuration: {exc}")
            return
        self.settings = settings

    def on_close(self) -> None:
        self.input_monitor_stop_event.set()
        self.auto_test_stop_event.set()
        self.display_test_stop_event.set()
        self.save_current_settings()
        with self.serial_lock:
            self.serial_connection.close()
        self.destroy()


def find_definition_dir() -> Path:
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / "InterfaceDefinition")
    candidates.extend(
        [
            Path.cwd() / "InterfaceDefinition",
            Path(__file__).resolve().parents[1] / "InterfaceDefinition",
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return Path.cwd()


def markdown_cell(value: str) -> str:
    text = value.replace("\r", "\\r").replace("\n", "<br>")
    return text.replace("|", "\\|") or " "


def safe_filename_fragment(value: str) -> str:
    safe = []
    for character in value:
        if character.isalnum() or character in {"-", "_"}:
            safe.append(character)
        else:
            safe.append("_")
    fragment = "".join(safe).strip("_")
    while "__" in fragment:
        fragment = fragment.replace("__", "_")
    return fragment[:80] or "panel"


def main() -> None:
    app = InterfaceTesterApp()
    app.mainloop()
