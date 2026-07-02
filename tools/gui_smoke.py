from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from interface_tester.app import InterfaceTesterApp  # noqa: E402
from interface_tester.light_logic import (  # noqa: E402
    INTENSITY_MODE_LABELS,
    INTENSITY_MODE_RAW,
    LIGHT_FILTER_BACKLIGHT,
    LIGHT_FILTER_LABELS,
)
from interface_tester.output_logic import (  # noqa: E402
    OUTPUT_CATEGORY_DISCRETE_CB,
    OUTPUT_CATEGORY_FILTER_LABELS,
)
from interface_tester.serial_diagnostics import make_serial_trace_event  # noqa: E402
from interface_tester.serial_client import BoardInfo  # noqa: E402
from interface_tester.session_results import RESULT_OK, make_panel_result  # noqa: E402
from interface_tester.session_store import load_test_session, save_test_session  # noqa: E402


DAT_PATH = ROOT / "InterfaceDefinition" / "3014029.dat"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def smoke() -> list[str]:
    checks: list[str] = []
    app = InterfaceTesterApp()
    try:
        app.update()
        require(app.assign_address_button.winfo_exists(), "No existe el control global de cambio de direccion")
        app.main_notebook.select(1)
        app.update()
        require(app.input_event_tree.winfo_height() >= 120, "La tabla de entradas quedo demasiado baja")
        require(app.input_console_text.winfo_height() >= 75, "La consola VER 3 quedo demasiado baja")
        app.main_notebook.select(2)
        app.update()
        require(app.display_test_button.winfo_width() >= 120, "El control de test display no quedo visible")
        app.main_notebook.select(4)
        app.update()
        require(app.log_text.winfo_height() >= 200, "La terminal general quedo demasiado baja")
        app.main_notebook.select(0)
        app.withdraw()
        checks.append("layout 1180x760: tablas y consolas visibles")

        require(DAT_PATH.exists(), f"No existe el .dat esperado: {DAT_PATH}")
        require(app.load_dat_file(DAT_PATH), "No se pudo cargar el .dat A320")
        require(app.current_aircraft is not None, "No quedo avion cargado")
        require(app.current_panel_families, "No se enumeraron familias de panel")
        require(len(app.main_notebook.tabs()) == 5, "La navegacion principal no tiene cinco pestanas")
        require(app.input_event_tree.winfo_exists(), "No existe la tabla de entradas en vivo")
        checks.append(f".dat cargado: {app.current_aircraft.name}")

        app.light_filter_var.set(LIGHT_FILTER_LABELS[LIGHT_FILTER_BACKLIGHT])
        app.intensity_mode_var.set(INTENSITY_MODE_LABELS[INTENSITY_MODE_RAW])
        require(app.select_family_name("ADIRS"), "No se pudo seleccionar ADIRS")
        adirs_test = app.get_selected_test_target()
        require(adirs_test is not None, "ADIRS no produjo target de prueba")
        require("w 38 ffff" in adirs_test.on_commands, "ADIRS no genero comando ON esperado")
        require("w 38 0000" in adirs_test.off_commands, "ADIRS no genero comando OFF esperado")
        checks.append("luces ADIRS: comandos ON/OFF generados")

        command_plan = app.light_command_preview_text(adirs_test)
        require("ON" in command_plan and "OFF" in command_plan, "Preview de comandos incompleto")
        require(app.selected_light_group_commands(show_warning=False), "No hay word seleccionado")
        require(app.selected_signal_commands(show_warning=False), "No hay senal seleccionada")
        checks.append("tabla de words/senales: seleccion inicial valida")

        require(app.select_family_name("ATCTCAS"), "No se pudo seleccionar ATCTCAS")
        app.update_display_test_summary()
        require("w30, w31, w32" in app.display_test_summary_var.get(), "Resumen display ATCTCAS incompleto")
        require(len(app.selected_display_test_signals(show_warning=False)) == 4, "Campos display ATCTCAS incorrectos")
        checks.append("display ATCTCAS: words 30/31/32 detectados")

        require(app.select_family_name("VU123"), "No se pudo seleccionar VU123")
        input_plan = app.selected_input_plan_text(show_warning=False)
        require(input_plan and "bVU125_CF_1_CB_In" in input_plan, "Plan de entradas VU123 incompleto")
        app.output_filter_var.set(OUTPUT_CATEGORY_FILTER_LABELS[OUTPUT_CATEGORY_DISCRETE_CB])
        output_plan = app.selected_output_plan_text(show_warning=False)
        require(output_plan and "CB_Out" in output_plan, "Plan de salidas Discrete/CB incompleto")
        checks.append("planes entradas/salidas: generados")

        app.panel_results["ADIRS"] = make_panel_result("ADIRS", RESULT_OK, "Smoke OK", "2026-06-15 12:00:00")
        app.command_history.append(
            {"time": "2026-06-15 12:01:00", "status": "OK", "command": "w 38 ffff", "response": "OK"}
        )
        app.input_word_values[36] = 0x0100
        app.serial_trace_events = [
            make_serial_trace_event("2026-06-15 12:01:00.100", "TX", "smoke", b"w 38 ffff\r"),
            make_serial_trace_event("2026-06-15 12:01:00.220", "RX", "smoke", "OK\r\n"),
        ]
        app.serial_trace_discarded_count = 1

        report_text = app.build_report_text("2026-06-15 12:02:00")
        status_text = app.build_operational_status_snapshot("2026-06-15 12:03:00")
        checklist_text = app.build_pre_hardware_checklist_snapshot("2026-06-15 12:04:00")
        require("# Interface Tester Report" in report_text, "Reporte Markdown incompleto")
        require("Interface Tester Operational Status" in status_text, "Estado operativo incompleto")
        require("Pre-Hardware Checklist" in checklist_text, "Checklist pre-HW incompleto")
        require("Sim Host is already downloaded" in checklist_text, "Pre-HW checklist missing Direct Mode note")
        checks.append("reporte/estado/checklist pre-HW: generados")

        session = app.build_test_session()
        with TemporaryDirectory() as temp_dir:
            session_path = Path(temp_dir) / "smoke_session.json"
            save_test_session(session, session_path)
            loaded_session = load_test_session(session_path)
        require(loaded_session.serial_trace_discarded_count == 1, "Sesion no preservo contador de traza")
        require(loaded_session.input_word_values.get(36) == 0x0100, "Sesion no preservo baseline VER3")
        app.apply_test_session(loaded_session)
        require(app.get_selected_family_name() == "VU123", "Sesion no restauro seleccion VU123")
        require(len(app.serial_trace_events) == 2, "Sesion no restauro traza serial")
        checks.append("sesion: round-trip y restauracion OK")

        app.active_board_address = 154
        app.command_history.append(
            {"time": "2026-06-15 12:05:00", "status": "OK", "command": "i", "response": "CAN addr 140"}
        )
        app.serial_trace_events.extend(
            [
                make_serial_trace_event("2026-06-15 12:05:00.100", "TX", "info", b"i\r"),
                make_serial_trace_event("2026-06-15 12:05:00.200", "RX", "info", "CAN addr 140\r"),
            ]
        )
        app.start_new_board_session_if_needed(BoardInfo(raw="CAN addr 140", address=140))
        require(app.active_board_address == 140, "No se actualizo la direccion de sesion")
        require(len(app.command_history) == 1 and app.command_history[0]["command"] == "i", "Se mezclaron comandos de tarjetas")
        require(not app.input_history and not app.panel_results, "Se mezclaron resultados de tarjetas")
        require(app.serial_trace_events and all(event.source == "info" for event in app.serial_trace_events), "Se mezclo la traza serial")
        checks.append("cambio de tarjeta: contexto reiniciado")

        return checks
    finally:
        app.on_close()


def main() -> int:
    try:
        checks = smoke()
    except Exception as exc:  # noqa: BLE001 - smoke output for operators.
        print(f"GUI smoke FAIL: {exc}", file=sys.stderr)
        return 1

    print("GUI smoke OK")
    for check in checks:
        print(f"- {check}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
