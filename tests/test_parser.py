from __future__ import annotations

import csv
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from interface_tester.app import safe_filename_fragment
from interface_tester.app_config import AppSettings, load_app_settings, save_app_settings
from interface_tester.dat_parser import load_interface_definitions
from interface_tester.input_logic import (
    build_input_test_plan_text,
    decode_input_update,
    decode_input_update_with_fallback,
    format_ver3_decoded_lines,
    input_signals_for_panels,
    parse_ver3_word_values,
    signal_logical_value,
    signal_raw_value,
)
from interface_tester.output_logic import (
    OUTPUT_CATEGORY_DISPLAY,
    OUTPUT_CATEGORY_DISCRETE_CB,
    OUTPUT_CATEGORY_ENABLE,
    build_display_sweep_frames,
    build_special_output_plan_text,
    display_word_groups,
    special_output_category,
    special_output_signals_for_panels,
    special_outputs_by_word,
)
from interface_tester.panel_detail import build_panel_capability_detail_text
from interface_tester.panel_assignment import address_assignment_panels, panel_side_label
from interface_tester.panel_inventory import build_panel_inventory
from interface_tester.pre_hardware import build_pre_hardware_checklist_text
from interface_tester.light_logic import (
    INTENSITY_MODE_PERCENT,
    LIGHT_FILTER_BACKLIGHT,
    LIGHT_FILTER_LAMPS,
    build_command_plan_text,
    build_panel_detail_text,
    build_panel_light_test,
    command_target_label,
    list_panel_families_with_lights,
    panel_family_name,
    signal_off_command,
    signal_on_command,
    test_target_includes_panel,
)
from interface_tester.report_export import write_report_csvs
from interface_tester.readiness import (
    READINESS_INFO,
    READINESS_OK,
    READINESS_WARNING,
    ReadinessCheck,
    build_operational_status_text,
    readiness_status_counts,
)
from interface_tester.serial_client import SerialConnection, SerialLineBuffer
from interface_tester.serial_client import parse_board_info
from interface_tester.serial_client import line_payload
from interface_tester.serial_diagnostics import (
    SERIAL_TRACE_MAX_EVENTS,
    build_serial_trace_text,
    make_serial_trace_event,
    trim_serial_trace_events,
)
from interface_tester.session_results import (
    RESULT_FILTER_FAIL,
    RESULT_FILTER_MIXED,
    RESULT_FILTER_OK,
    RESULT_FILTER_PENDING,
    RESULT_FILTER_WITH_STATUS,
    RESULT_NOT_TESTED,
    make_panel_result,
    result_matches_filter,
    summarize_family_result,
)
from interface_tester.session_store import TestSession, load_test_session, save_test_session
from interface_tester.validation import validate_aircraft_definition


ROOT = Path(__file__).resolve().parents[1]


class ParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.definitions = {
            definition.name: definition
            for definition in load_interface_definitions(ROOT / "InterfaceDefinition")
        }

    def test_loads_both_aircraft(self) -> None:
        self.assertIn("A320 (3014029.dat)", self.definitions)
        self.assertIn("ATR (0010110600001.dat)", self.definitions)

    def test_a320_adirs_generates_full_word_38_for_lights(self) -> None:
        a320 = self.definitions["A320 (3014029.dat)"]
        test = build_panel_light_test(a320, "ADIRS")
        self.assertIsNotNone(test)
        masks_by_word = {group.word: group.mask for group in test.groups}
        self.assertEqual(masks_by_word[38], 0xFFFF)
        self.assertIn("w 38 ffff", test.on_commands)
        self.assertIn("w 38 0000", test.off_commands)

    def test_percent_mode_uses_decimal_100_for_float_fields(self) -> None:
        a320 = self.definitions["A320 (3014029.dat)"]
        test = build_panel_light_test(a320, "ADIRS", INTENSITY_MODE_PERCENT)
        self.assertIsNotNone(test)
        on_values_by_word = {group.word: group.command_value for group in test.groups}
        self.assertEqual(on_values_by_word[38], 0x6464)
        self.assertIn("w 38 6464", test.on_commands)

    def test_signal_commands_follow_dat_bit_order(self) -> None:
        a320 = self.definitions["A320 (3014029.dat)"]
        test = build_panel_light_test(a320, "ADIRS")
        self.assertIsNotNone(test)
        group = next(group for group in test.groups if group.word == 38)
        signals_by_range = {signal.bit_range: signal for signal in group.signals}

        self.assertEqual(signal_on_command(signals_by_range["0-7"]), "w 38 00ff")
        self.assertEqual(signal_on_command(signals_by_range["8-15"]), "w 38 ff00")
        self.assertEqual(signal_off_command(signals_by_range["0-7"]), "w 38 0000")

    def test_atr_cdu_half_word_light_commands_follow_firmware_write_order(self) -> None:
        atr = self.definitions["ATR (0010110600001.dat)"]
        test = build_panel_light_test(atr, "CDU[0]")
        self.assertIsNotNone(test)
        commands_by_word = {group.word: group.on_command for group in test.groups}

        self.assertEqual(commands_by_word[2], "w 2 00ff")
        self.assertEqual(commands_by_word[35], "w 35 ff00")

    def test_parser_keeps_input_flip_flag(self) -> None:
        a320 = self.definitions["A320 (3014029.dat)"]
        signal = next(item for item in a320.signals if item.name == "bVU125_CF_1_CB_In")

        self.assertEqual(signal.direction, "CI")
        self.assertIn("FLIP", signal.flags)

    def test_backlight_filter_keeps_only_backlight_signals(self) -> None:
        a320 = self.definitions["A320 (3014029.dat)"]
        test = build_panel_light_test(a320, "ADIRS", light_filter=LIGHT_FILTER_BACKLIGHT)
        self.assertIsNotNone(test)
        self.assertEqual(test.on_commands, ["w 38 ffff"])
        self.assertTrue(all("Bklt" in signal.name for group in test.groups for signal in group.signals))

    def test_command_plan_text_includes_on_off_and_word_details(self) -> None:
        a320 = self.definitions["A320 (3014029.dat)"]
        test = build_panel_light_test(a320, "ADIRS", light_filter=LIGHT_FILTER_BACKLIGHT)
        self.assertIsNotNone(test)
        label = command_target_label(test)

        text = build_command_plan_text(
            test,
            {
                "Avion": "A320",
                "Panel detectado": label,
            },
        )

        self.assertIn("ADIRS", label)
        self.assertIn("ON commands:", text)
        self.assertIn("w 38 ffff", text)
        self.assertIn("OFF commands:", text)
        self.assertIn("w 38 0000", text)
        self.assertIn("| w38 | `w 38 ffff` | `w 38 0000` | ffff | 2 |", text)
        self.assertIn(f"Panel detectado: {label}", text)

    def test_command_plan_text_handles_targets_without_lights(self) -> None:
        a320 = self.definitions["A320 (3014029.dat)"]
        families, _stats = build_panel_inventory(a320)
        vu123 = next(family for family in families if family.family_name == "VU123")

        text = build_command_plan_text(vu123, {"Avion": "A320"})

        self.assertIn("Panel: VU123", text)
        self.assertIn("No light ON commands", text)
        self.assertIn("No light OFF commands", text)
        self.assertIn("No CO lights mapped", text)

    def test_panel_detail_text_includes_variants_words_and_signals(self) -> None:
        a320 = self.definitions["A320 (3014029.dat)"]
        test = build_panel_light_test(a320, "ADIRS", light_filter=LIGHT_FILTER_BACKLIGHT)
        self.assertIsNotNone(test)

        text = build_panel_detail_text(
            test,
            {
                "Avion": "A320",
                "Intensidad": "Raw FF",
            },
        )

        self.assertIn("## Variants", text)
        self.assertIn("| ADIRS |", text)
        self.assertIn("## Word Summary", text)
        self.assertIn("| w38 | `w 38 ffff` | `w 38 0000` | ffff | 2 |", text)
        self.assertIn("## Signals", text)
        self.assertIn("| ADIRS | fADIRS_Bklt | FLOAT-FLD | w38 | 0-7 | `w 38 00ff` | `w 38 0000` |", text)

    def test_lamps_filter_excludes_backlight_signals(self) -> None:
        a320 = self.definitions["A320 (3014029.dat)"]
        test = build_panel_light_test(a320, "ADIRS", light_filter=LIGHT_FILTER_LAMPS)
        self.assertIsNotNone(test)
        self.assertNotIn("w 38 ffff", test.on_commands)
        self.assertTrue(all("Bklt" not in signal.name for group in test.groups for signal in group.signals))

    def test_seven_bit_fields_keep_exact_mask(self) -> None:
        a320 = self.definitions["A320 (3014029.dat)"]
        test = build_panel_light_test(a320, "VU110")
        self.assertIsNotNone(test)
        masks_by_word = {group.word: group.mask for group in test.groups}
        self.assertEqual(masks_by_word[0], 0x007F)

    def test_panel_family_removes_numeric_suffix(self) -> None:
        self.assertEqual(panel_family_name("RMP[0]"), "RMP")
        self.assertEqual(panel_family_name("PFD/ND[5]"), "PFD/ND")
        self.assertEqual(panel_family_name("ADIRS"), "ADIRS")

    def test_address_assignment_targets_show_known_captain_and_fo_variants(self) -> None:
        a320 = self.definitions["A320 (3014029.dat)"]

        self.assertEqual(panel_side_label(a320, a320.panels["RMP[0]"]), "CAP")
        self.assertEqual(panel_side_label(a320, a320.panels["RMP[1]"]), "F/O")
        self.assertIn(a320.panels["RMP[0]"], address_assignment_panels(a320))

    def test_a320_rmp_family_is_not_repeated(self) -> None:
        a320 = self.definitions["A320 (3014029.dat)"]
        families = list_panel_families_with_lights(a320)
        rmp_families = [family for family in families if family.family_name == "RMP"]
        self.assertEqual(len(rmp_families), 1)
        self.assertEqual(rmp_families[0].variant_count, 3)

    def test_exact_test_target_matches_only_detected_panel(self) -> None:
        a320 = self.definitions["A320 (3014029.dat)"]
        test = build_panel_light_test(a320, "RMP[0]")
        self.assertIsNotNone(test)

        self.assertTrue(test_target_includes_panel(test, a320.panels["RMP[0]"]))
        self.assertFalse(test_target_includes_panel(test, a320.panels["RMP[1]"]))
        self.assertTrue(test_target_includes_panel(test, None))

    def test_family_test_target_matches_only_family_variants(self) -> None:
        a320 = self.definitions["A320 (3014029.dat)"]
        family = next(
            item
            for item in list_panel_families_with_lights(a320)
            if item.family_name == "RMP"
        )

        self.assertTrue(test_target_includes_panel(family, a320.panels["RMP[2]"]))
        self.assertFalse(test_target_includes_panel(family, a320.panels["ADIRS"]))


class BoardInfoTests(unittest.TestCase):
    def test_parse_address_and_channel_from_at_notation(self) -> None:
        info = parse_board_info("Card detected @2.145 ready")
        self.assertEqual(info.channel, 2)
        self.assertEqual(info.address, 145)

    def test_parse_address_label(self) -> None:
        info = parse_board_info("Address: 147\r\nFirmware: 1.2")
        self.assertIsNone(info.channel)
        self.assertEqual(info.address, 147)

    def test_parse_extra_board_info_fields(self) -> None:
        raw = "Address: 145\r\nFirmware Version: 2.4.1\r\nHardware: UMB-3\r\nBaud Rate: 500000\r\nBus Status: OK"
        info = parse_board_info(raw)
        self.assertEqual(info.address, 145)
        self.assertEqual(info.firmware, "2.4.1")
        self.assertEqual(info.hardware, "UMB-3")
        self.assertEqual(info.baud_rate, 500000)
        self.assertEqual(info.bus_status, "Ok")

    def test_connector_board_description_is_not_mistaken_for_firmware(self) -> None:
        raw = "EA7873501 DVI V.1.03\r\nFirmware for Connector Board EA 00091799-01\r\nCAN addr 140"

        info = parse_board_info(raw)

        self.assertEqual(info.address, 140)
        self.assertIsNone(info.firmware)

    def test_parse_software_version_as_firmware(self) -> None:
        info = parse_board_info("Software Version # 1.84\r\nCAN Address <154>")

        self.assertEqual(info.firmware, "1.84")


class UtilityTests(unittest.TestCase):
    def test_safe_filename_fragment_removes_command_plan_punctuation(self) -> None:
        fragment = safe_filename_fragment("RMP[0]  @2.145 / Captain")

        self.assertEqual(fragment, "RMP_0_2_145_Captain")


class SerialDiagnosticTests(unittest.TestCase):
    def test_line_payload_uses_selected_newline(self) -> None:
        self.assertEqual(line_payload("w 38 ffff", "CR"), b"w 38 ffff\r")
        self.assertEqual(line_payload("w 38 ffff", "LF"), b"w 38 ffff\n")
        self.assertEqual(line_payload("w 38 ffff", "CRLF"), b"w 38 ffff\r\n")

    def test_trace_event_keeps_text_and_hex(self) -> None:
        event = make_serial_trace_event(
            "2026-06-14 16:00:00.123",
            "RX",
            "diagnostic",
            b"OK\r\n",
        )

        self.assertEqual(event.text, "OK\\r\\n")
        self.assertEqual(event.hex_data, "4F 4B 0D 0A")

    def test_trace_text_includes_metadata_and_events(self) -> None:
        event = make_serial_trace_event(
            "2026-06-14 16:00:00.123",
            "TX",
            "command",
            b"i\r",
        )

        text = build_serial_trace_text(
            [event],
            {
                "generated_at": "2026-06-14 16:00:01",
                "port": "COM7",
                "baud_rate": "115200",
                "newline": "CR",
                "dat_path": "C:/defs/3014029.dat",
                "panel": "ADIRS",
                "detected_panel": "ADIRS  @2.145",
                "response_wait_seconds": "1.20",
                "response_quiet_seconds": "0.25",
                "command_delay_seconds": "0.05",
                "diagnostic_seconds": "2.00",
            },
        )

        self.assertIn("Port: COM7", text)
        self.assertIn("Detected panel: ADIRS  @2.145", text)
        self.assertIn("Response wait: 1.20 s", text)
        self.assertIn("Trace event limit:", text)
        self.assertIn("[2026-06-14 16:00:00.123] TX command", text)
        self.assertIn("TEXT: i\\r", text)
        self.assertIn("HEX : 69 0D", text)

    def test_trim_serial_trace_events_keeps_latest_events(self) -> None:
        events = [
            make_serial_trace_event(f"2026-06-14 16:00:0{index}.000", "TX", "command", f"cmd{index}")
            for index in range(5)
        ]

        removed_count = trim_serial_trace_events(events, max_events=3)

        self.assertEqual(removed_count, 2)
        self.assertEqual([event.text for event in events], ["cmd2", "cmd3", "cmd4"])

    def test_default_serial_trace_limit_is_large_enough_for_sessions(self) -> None:
        self.assertGreaterEqual(SERIAL_TRACE_MAX_EVENTS, 1000)


class PreHardwareChecklistTests(unittest.TestCase):
    def test_pre_hardware_checklist_includes_context_and_safety_steps(self) -> None:
        text = build_pre_hardware_checklist_text(
            {
                "generated_at": "2026-06-15 12:30:00",
                "app_version": "0.2.35",
                "aircraft": "A320",
                "dat_path": "C:/defs/3014029.dat",
                "selected_panel": "ADIRS",
                "detected_panel": "ADIRS  @2.145",
                "port": "COM7",
                "baud_rate": "115200",
                "newline": "CR",
                "connection_status": "Conectado a COM7",
                "light_filter": "Backlight",
                "output_filter": "Todas",
                "intensity_mode": "Raw FF",
                "auto_off": "Si",
            }
        )

        self.assertIn("# Interface Tester Pre-Hardware Checklist", text)
        self.assertIn("- Selected panel: ADIRS", text)
        self.assertIn("- Port: COM7", text)
        self.assertIn("Confirm that Sim Host is already downloaded", text)
        self.assertIn("this app does not control, start, stop, or verify Sim Host", text)
        self.assertIn("Save the report", text)


class InputLogicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.definitions = {
            definition.name: definition
            for definition in load_interface_definitions(ROOT / "InterfaceDefinition")
        }

    def test_parse_ver3_word_values_accepts_common_formats(self) -> None:
        updates = parse_ver3_word_values(
            """
w30 0100
word 31 value=0x00ff
32: 0001
VER 3 33 8000
word 34 changed to 0200
""".strip()
        )

        self.assertEqual(
            [(update.word, update.value) for update in updates],
            [(30, 0x0100), (31, 0x00FF), (32, 0x0001), (33, 0x8000), (34, 0x0200)],
        )

    def test_decode_input_update_uses_dat_bit_order_and_flip(self) -> None:
        a320 = self.definitions["A320 (3014029.dat)"]
        signal = next(item for item in a320.signals if item.name == "bVU125_CF_1_CB_In")

        self.assertEqual(signal.bit_range, "7")
        self.assertEqual(signal.mask, 0x0100)
        self.assertEqual(signal_raw_value(signal, 0x0100), 1)
        self.assertEqual(signal_logical_value(signal, 1), 0)
        self.assertEqual(signal_logical_value(signal, 0), 1)

    def test_format_ver3_decoded_lines_reports_changed_signal(self) -> None:
        a320 = self.definitions["A320 (3014029.dat)"]
        signals = input_signals_for_panels(a320, ["VU123"])
        update = parse_ver3_word_values("w36 0100")[0]

        baseline_lines = format_ver3_decoded_lines(update, signals)
        changed_lines = format_ver3_decoded_lines(
            parse_ver3_word_values("w36 0000")[0],
            signals,
            previous_value=0x0100,
        )

        self.assertIn("baseline", baseline_lines[0])
        self.assertTrue(any("bVU125_CF_1_CB_In" in line for line in baseline_lines))
        self.assertIn("0100 -> 0000", changed_lines[0])
        self.assertTrue(any("raw 1->0" in line for line in changed_lines))
        self.assertTrue(any("logical 0->1" in line for line in changed_lines))

    def test_mirrored_ver3_change_decodes_atr_vu110_hardware_order(self) -> None:
        atr = self.definitions["ATR (0010110600001.dat)"]
        signals = input_signals_for_panels(atr, ["VU110"])

        lines = format_ver3_decoded_lines(
            parse_ver3_word_values("00 0200")[0],
            signals,
            previous_value=0x0000,
        )

        self.assertIn("inferred reversed bit order", lines[0])
        self.assertTrue(any("bVU110_Stby_Sw_Nose_Up_Pos" in line for line in lines))

    def test_mirrored_ver3_change_decodes_a320_vu110_word_five(self) -> None:
        a320 = self.definitions["A320 (3014029.dat)"]
        signals = input_signals_for_panels(a320, ["VU110"])
        update = parse_ver3_word_values("05 0009")[0]

        decoded, mirrored = decode_input_update_with_fallback(update, signals, previous_value=0x0001)
        changed = [item.signal.name for item in decoded if item.changed]

        self.assertTrue(mirrored)
        self.assertEqual(changed, ["bVU110_Rud_Trim_Rst_Sw"])

    def test_decode_input_update_keeps_raw_fields(self) -> None:
        atr = self.definitions["ATR (0010110600001.dat)"]
        signal = next(item for item in atr.signals if item.name == "nICP_Spd_Tgt_Sel_Enc[0]")

        decoded = decode_input_update(parse_ver3_word_values("w8 00f0")[0], [signal])

        self.assertEqual(decoded[0].raw_value, 0x00F0)
        self.assertEqual(decoded[0].logical_value, 0x00F0)

    def test_input_test_plan_text_lists_words_flags_and_inputs(self) -> None:
        a320 = self.definitions["A320 (3014029.dat)"]
        signals = [
            signal
            for signal in input_signals_for_panels(a320, ["VU123"])
            if signal.word == 36
        ]

        text = build_input_test_plan_text(
            signals,
            "VU123",
            {
                "Avion": "A320",
                "Puerto": "COM7",
            },
        )

        self.assertIn("# Interface Tester Input Test Plan", text)
        self.assertIn("Target: VU123", text)
        self.assertIn("Avion: A320", text)
        self.assertIn("| w36 |", text)
        self.assertIn("bVU125_CF_1_CB_In", text)
        self.assertIn("| VU123 | bVU125_CF_1_CB_In | BIT | w36 | 7 | FLIP |", text)

    def test_input_test_plan_text_handles_empty_target(self) -> None:
        text = build_input_test_plan_text([], "EMPTY")

        self.assertIn("Target: EMPTY", text)
        self.assertIn("No CI inputs are mapped", text)


class SpecialOutputLogicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.definitions = {
            definition.name: definition
            for definition in load_interface_definitions(ROOT / "InterfaceDefinition")
        }

    def test_ape4200_outputs_include_display_digits_and_enable(self) -> None:
        atr = self.definitions["ATR (0010110600001.dat)"]
        signals = special_output_signals_for_panels(atr, ["APE4200[0]"])
        names = {signal.name for signal in signals}

        display_signal = next(signal for signal in signals if signal.name == "cAPE4200_Clock_Upr_Dspl_Hr_Digit_10[0]")
        enable_signal = next(signal for signal in signals if signal.name == "bAlways_On")

        self.assertIn("cAPE4200_Clock_Upr_Dspl_Hr_Digit_10[0]", names)
        self.assertIn("fAPE4200_Clock_Dspl_Int[0]", names)
        self.assertNotIn("bAPE4200_Clock_Mode_Dspl_DT_Ann[0]", names)
        self.assertEqual(special_output_category(display_signal), OUTPUT_CATEGORY_DISPLAY)
        self.assertEqual(special_output_category(enable_signal), OUTPUT_CATEGORY_ENABLE)

    def test_rmp_outputs_group_display_words_without_lights(self) -> None:
        a320 = self.definitions["A320 (3014029.dat)"]
        signals = special_output_signals_for_panels(a320, ["RMP[0]", "RMP[1]", "RMP[2]"])
        names = {signal.name for signal in signals}
        by_word = special_outputs_by_word(signals)

        self.assertIn("cRMP_Active_Dspl_Digit_10[0]", names)
        self.assertIn(60, by_word)
        self.assertTrue(all("Bklt" not in signal.name for signal in signals))
        self.assertTrue(all("Ann" not in signal.name for signal in signals))
        self.assertTrue(all("_Lt" not in signal.name for signal in signals))

    def test_atctcas_display_sweep_uses_two_characters_per_word(self) -> None:
        a320 = self.definitions["A320 (3014029.dat)"]
        signals = special_output_signals_for_panels(
            a320,
            ["ATCTCAS"],
            OUTPUT_CATEGORY_DISPLAY,
        )
        groups = display_word_groups(signals)
        frames = build_display_sweep_frames(signals, "09")

        self.assertEqual([group.word for group in groups], [30, 31, 32])
        self.assertEqual([len(group.signals) for group in groups], [1, 2, 1])
        self.assertEqual(frames[0].commands, ("S 30 12", "S 31 34", "S 32 56"))
        self.assertEqual(frames[1].commands, ("S 30 00", "S 31 00", "S 32 00"))
        self.assertEqual(frames[2].commands, ("S 30 99", "S 31 99", "S 32 99"))

    def test_special_output_plan_text_lists_categories_words_and_outputs(self) -> None:
        atr = self.definitions["ATR (0010110600001.dat)"]
        signals = special_output_signals_for_panels(atr, ["APE4200[0]"])

        text = build_special_output_plan_text(
            signals,
            "APE4200[0]",
            {
                "Avion": "ATR",
                "Puerto": "COM8",
            },
        )

        self.assertIn("# Interface Tester Non-Light Output Plan", text)
        self.assertIn("Target: APE4200[0]", text)
        self.assertIn("Avion: ATR", text)
        self.assertIn("`S <word> <text>`", text)
        self.assertIn("does not generate raw commands for other outputs", text)
        self.assertIn("| DISPLAY |", text)
        self.assertIn("| ENABLE |", text)
        self.assertIn("cAPE4200_Clock_Upr_Dspl_Hr_Digit_10[0]", text)

    def test_special_output_plan_text_handles_empty_target(self) -> None:
        text = build_special_output_plan_text([], "EMPTY")

        self.assertIn("Target: EMPTY", text)
        self.assertIn("No non-light CO outputs are mapped", text)

    def test_non_light_outputs_include_cb_out_discretes(self) -> None:
        a320 = self.definitions["A320 (3014029.dat)"]
        signals = special_output_signals_for_panels(a320, ["VU123"])
        signal = next(item for item in signals if item.name == "bVU125_CF_1_CB_Out")

        self.assertEqual(special_output_category(signal), OUTPUT_CATEGORY_DISCRETE_CB)
        self.assertEqual(signal.word, 36)
        self.assertEqual(signal.bit_range, "7")

    def test_non_light_output_filter_keeps_only_selected_category(self) -> None:
        a320 = self.definitions["A320 (3014029.dat)"]
        discrete_signals = special_output_signals_for_panels(
            a320,
            ["VU123"],
            OUTPUT_CATEGORY_DISCRETE_CB,
        )
        display_signals = special_output_signals_for_panels(
            a320,
            ["VU123"],
            OUTPUT_CATEGORY_DISPLAY,
        )

        self.assertEqual(len(discrete_signals), 48)
        self.assertTrue(all(special_output_category(signal) == OUTPUT_CATEGORY_DISCRETE_CB for signal in discrete_signals))
        self.assertEqual(display_signals, [])


class PanelInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.definitions = {
            definition.name: definition
            for definition in load_interface_definitions(ROOT / "InterfaceDefinition")
        }

    def test_inventory_includes_input_and_cb_output_families(self) -> None:
        a320 = self.definitions["A320 (3014029.dat)"]
        light_families = {
            family.family_name
            for family in list_panel_families_with_lights(a320)
        }
        families, stats = build_panel_inventory(a320)
        inventory_families = {family.family_name for family in families}

        self.assertNotIn("VU123", light_families)
        self.assertIn("VU123", inventory_families)
        self.assertEqual(stats["VU123"].light_count, 0)
        self.assertGreater(stats["VU123"].input_count, 0)
        self.assertGreater(stats["VU123"].output_count, 0)

    def test_inventory_includes_special_output_only_families(self) -> None:
        atr = self.definitions["ATR (0010110600001.dat)"]
        families, stats = build_panel_inventory(atr)
        svrice = next(family for family in families if family.family_name == "SVRICE")

        self.assertEqual(svrice.light_count, 0)
        self.assertEqual(len(svrice.groups), 0)
        self.assertEqual(stats["SVRICE"].input_count, 0)
        self.assertGreater(stats["SVRICE"].output_count, 0)


class PanelCapabilityDetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.definitions = {
            definition.name: definition
            for definition in load_interface_definitions(ROOT / "InterfaceDefinition")
        }

    def test_detail_includes_input_only_panel_capabilities(self) -> None:
        a320 = self.definitions["A320 (3014029.dat)"]
        families, stats = build_panel_inventory(a320)
        vu123 = next(family for family in families if family.family_name == "VU123")
        inputs = input_signals_for_panels(a320, vu123.variant_names)
        outputs = special_output_signals_for_panels(a320, vu123.variant_names)

        text = build_panel_capability_detail_text(
            vu123,
            inputs,
            outputs,
            stats["VU123"],
            {
                "Avion": "A320",
                "Intensidad": "Raw FF",
            },
        )

        self.assertIn("# Interface Tester Panel Capability Detail", text)
        self.assertIn("Panel: VU123", text)
        self.assertIn("| VU123 | 3 | 128 | 0 |", text)
        self.assertIn("| Lights CO | 0 | 0 |", text)
        self.assertIn("| Inputs CI | 48 | 7 |", text)
        self.assertIn("| Non-light CO outputs | 48 | 7 |", text)
        self.assertIn("No CO lights are mapped", text)
        self.assertIn("bVU125_CF_1_CB_In", text)
        self.assertIn("bVU125_CF_1_CB_Out", text)
        self.assertIn("DISCRETE/CB", text)

    def test_detail_includes_special_output_only_panel_capabilities(self) -> None:
        atr = self.definitions["ATR (0010110600001.dat)"]
        families, stats = build_panel_inventory(atr)
        svrice = next(family for family in families if family.family_name == "SVRICE")
        inputs = input_signals_for_panels(atr, svrice.variant_names)
        outputs = special_output_signals_for_panels(atr, svrice.variant_names)

        text = build_panel_capability_detail_text(
            svrice,
            inputs,
            outputs,
            stats["SVRICE"],
            {
                "Avion": "ATR",
            },
        )

        self.assertIn("Panel: SVRICE (SVRICE[0], SVRICE[1])", text)
        self.assertIn("| Non-light CO outputs | 2 | 1 |", text)
        self.assertIn("No CO lights are mapped", text)
        self.assertIn("No CI inputs are mapped", text)
        self.assertIn("fSevereIceSign_Matrix[0]", text)
        self.assertIn("MATRIX/SIGN", text)


class ValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.definitions = {
            definition.name: definition
            for definition in load_interface_definitions(ROOT / "InterfaceDefinition")
        }

    def test_a320_validation_detects_undefined_acp3(self) -> None:
        report = validate_aircraft_definition(self.definitions["A320 (3014029.dat)"])
        titles = [issue.title for issue in report.issues]
        self.assertTrue(any("active definition" in title for title in titles))
        undefined_issue = next(issue for issue in report.issues if "active definition" in issue.title)
        self.assertIn("ACP[3]", undefined_issue.details)

    def test_validation_detects_duplicate_addresses(self) -> None:
        report = validate_aircraft_definition(self.definitions["ATR (0010110600001.dat)"])
        duplicate_issue = next(issue for issue in report.issues if "addresses appear" in issue.title)
        self.assertTrue(any("107" in detail for detail in duplicate_issue.details))

    def test_validation_reports_testable_panel_count(self) -> None:
        report = validate_aircraft_definition(self.definitions["A320 (3014029.dat)"])
        self.assertGreater(report.testable_panel_count, 0)
        self.assertLessEqual(report.testable_panel_count, report.panel_count)


class AppSettingsTests(unittest.TestCase):
    def test_settings_round_trip(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "settings.json"
            settings = AppSettings(
                last_dat_path="C:/defs/a320.dat",
                last_definition_dir="C:/defs",
                serial_port="COM7",
                baud_rate="500000",
                newline="CRLF",
                intensity_mode="percent_100",
                light_filter="backlight",
                output_filter="DISCRETE/CB",
                duration_seconds=2.5,
                response_wait_seconds=2.0,
                response_quiet_seconds=0.4,
                command_delay_seconds=0.1,
                diagnostic_seconds=3.0,
                auto_off=False,
                display_word="41",
                display_text="123456",
            )

            save_app_settings(settings, config_path)
            loaded = load_app_settings(config_path)

        self.assertEqual(loaded, settings)

    def test_corrupt_settings_return_defaults(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "settings.json"
            config_path.write_text("{not valid json", encoding="utf-8")

            loaded = load_app_settings(config_path)

        self.assertEqual(loaded, AppSettings())


class SessionResultTests(unittest.TestCase):
    def test_family_result_has_priority_over_variants(self) -> None:
        results = {
            "RMP": make_panel_result("RMP", "OK", "", "2026-06-14 10:00:00"),
            "RMP[0]": make_panel_result("RMP[0]", "FAIL", "", "2026-06-14 10:01:00"),
        }

        summary = summarize_family_result("RMP", ["RMP[0]", "RMP[1]", "RMP[2]"], results)

        self.assertEqual(summary, "OK")

    def test_partial_variant_results_show_count(self) -> None:
        results = {
            "RMP[0]": make_panel_result("RMP[0]", "OK", "", "2026-06-14 10:00:00"),
            "RMP[1]": make_panel_result("RMP[1]", "OK", "", "2026-06-14 10:01:00"),
        }

        summary = summarize_family_result("RMP", ["RMP[0]", "RMP[1]", "RMP[2]"], results)

        self.assertEqual(summary, "OK (2/3)")

    def test_mixed_variant_results_show_mixed(self) -> None:
        results = {
            "RMP[0]": make_panel_result("RMP[0]", "OK", "", "2026-06-14 10:00:00"),
            "RMP[1]": make_panel_result("RMP[1]", "FAIL", "", "2026-06-14 10:01:00"),
        }

        summary = summarize_family_result("RMP", ["RMP[0]", "RMP[1]", "RMP[2]"], results)

        self.assertEqual(summary, "Mixed (2/3)")

    def test_empty_results_are_not_tested(self) -> None:
        summary = summarize_family_result("RMP", ["RMP[0]", "RMP[1]", "RMP[2]"], {})

        self.assertEqual(summary, RESULT_NOT_TESTED)

    def test_result_filter_matches_pending_and_status(self) -> None:
        self.assertTrue(result_matches_filter(RESULT_NOT_TESTED, RESULT_FILTER_PENDING))
        self.assertFalse(result_matches_filter("OK", RESULT_FILTER_PENDING))
        self.assertTrue(result_matches_filter("OK", RESULT_FILTER_WITH_STATUS))

    def test_result_filter_matches_partial_and_mixed_summaries(self) -> None:
        self.assertTrue(result_matches_filter("OK (2/3)", RESULT_FILTER_OK))
        self.assertTrue(result_matches_filter("FAIL (1/3)", RESULT_FILTER_FAIL))
        self.assertTrue(result_matches_filter("Mixed (2/3)", RESULT_FILTER_MIXED))
        self.assertFalse(result_matches_filter("Mixed (2/3)", RESULT_FILTER_OK))


class SessionStoreTests(unittest.TestCase):
    def test_session_round_trip(self) -> None:
        with TemporaryDirectory() as temp_dir:
            session_path = Path(temp_dir) / "session.json"
            session = TestSession(
                saved_at="2026-06-14 15:30:00",
                dat_path="C:/defs/3014029.dat",
                aircraft_name="A320",
                panel_results={
                    "ADIRS": make_panel_result("ADIRS", "OK", "Backlight OK", "2026-06-14 15:31:00"),
                },
                command_history=[
                    {"time": "2026-06-14 15:31:10", "status": "OK", "command": "w38 ffff", "response": "OK"},
                ],
                serial_trace_events=[
                    make_serial_trace_event("2026-06-14 15:31:10.100", "TX", "command", b"w38 ffff\r"),
                    make_serial_trace_event("2026-06-14 15:31:10.220", "RX", "command", "OK\r\n"),
                ],
                serial_trace_discarded_count=12,
                input_word_values={36: 0x0100, 38: 0xFFFF},
                input_history=[
                    {
                        "time": "2026-06-14 15:31:12",
                        "event": "changed",
                        "word": "w36",
                        "previous_word_value": "0100",
                        "word_value": "0000",
                        "changed_mask": "0100",
                        "panel": "VU123",
                        "signal": "bVU125_CF_1_CB_In",
                        "signal_type": "BIT",
                        "bits": "7",
                        "flags": "FLIP",
                        "previous_raw": "1",
                        "raw": "0",
                        "previous_logical": "0",
                        "logical": "1",
                        "comment": "Panel 125VU TRI Cntor Supply CB In",
                        "raw_line": "w36 0000",
                    }
                ],
                report_result="OK",
                report_comment="Sesion parcial",
                current_result_key="ADIRS",
                detected_panel_name="ADIRS",
                board_info_text="Tarjeta: canal 2, direccion 145",
                light_filter="backlight",
                output_filter="DISCRETE/CB",
                intensity_mode="percent_100",
                duration_seconds=2.0,
                response_wait_seconds=2.5,
                response_quiet_seconds=0.5,
                command_delay_seconds=0.2,
                diagnostic_seconds=4.0,
                auto_off=False,
                display_word="38",
                display_text="105435",
            )

            save_test_session(session, session_path)
            loaded = load_test_session(session_path)

        self.assertEqual(loaded, session)
        self.assertEqual(loaded.input_history[0]["signal"], "bVU125_CF_1_CB_In")

    def test_old_session_command_history_gets_status_from_response(self) -> None:
        with TemporaryDirectory() as temp_dir:
            session_path = Path(temp_dir) / "session.json"
            session_path.write_text(
                """
{
  "schema_version": 1,
  "saved_at": "2026-06-14 15:30:00",
  "command_history": [
    {"time": "2026-06-14 15:31:10", "command": "w38 ffff", "response": "OK"},
    {"time": "2026-06-14 15:31:11", "command": "w38 0000", "response": ""}
  ]
}
""".strip(),
                encoding="utf-8",
            )

            loaded = load_test_session(session_path)

        self.assertEqual(loaded.command_history[0]["status"], "OK")
        self.assertEqual(loaded.command_history[1]["status"], "No response")
        self.assertEqual(loaded.output_filter, "all")
        self.assertEqual(loaded.input_word_values, {})
        self.assertEqual(loaded.serial_trace_events, [])
        self.assertEqual(loaded.serial_trace_discarded_count, 0)

    def test_session_loads_input_word_values_from_json_strings(self) -> None:
        with TemporaryDirectory() as temp_dir:
            session_path = Path(temp_dir) / "session.json"
            session_path.write_text(
                """
{
  "schema_version": 1,
  "saved_at": "2026-06-14 15:30:00",
  "input_word_values": {
    "36": "0100",
    "38": 65535,
    "bad": "ignored"
  }
}
""".strip(),
                encoding="utf-8",
            )

            loaded = load_test_session(session_path)

        self.assertEqual(loaded.input_word_values, {36: 0x0100, 38: 0xFFFF})

    def test_corrupt_session_raises_value_error(self) -> None:
        with TemporaryDirectory() as temp_dir:
            session_path = Path(temp_dir) / "session.json"
            session_path.write_text("{not valid json", encoding="utf-8")

            with self.assertRaises(ValueError):
                load_test_session(session_path)

    def test_unsupported_session_schema_raises_value_error(self) -> None:
        with TemporaryDirectory() as temp_dir:
            session_path = Path(temp_dir) / "session.json"
            session_path.write_text('{"schema_version": 999}', encoding="utf-8")

            with self.assertRaises(ValueError):
                load_test_session(session_path)


class SerialConnectionTests(unittest.TestCase):
    def test_line_buffer_reassembles_fragmented_ver3_lines(self) -> None:
        buffer = SerialLineBuffer()

        self.assertEqual(buffer.feed("10: 00"), [])
        self.assertEqual(buffer.feed("10\r11: 0040\r"), ["10: 0010", "11: 0040"])
        self.assertEqual(buffer.flush(), [])

    def test_line_buffer_flushes_unterminated_text(self) -> None:
        buffer = SerialLineBuffer()

        self.assertEqual(buffer.feed("VER 3"), [])
        self.assertEqual(buffer.flush(), ["VER 3"])

    def test_read_until_quiet_collects_available_chunks(self) -> None:
        class FakeSerial:
            is_open = True

            def __init__(self) -> None:
                self.chunks = [b"OK", b"\r\n"]

            @property
            def in_waiting(self) -> int:
                if not self.chunks:
                    return 0
                return len(self.chunks[0])

            def read(self, _size: int) -> bytes:
                if not self.chunks:
                    return b""
                return self.chunks.pop(0)

        connection = SerialConnection()
        connection._serial = FakeSerial()

        self.assertEqual(connection.read_until_quiet(wait_seconds=0.1, quiet_seconds=0.0), "OK\r\n")


class ReportExportTests(unittest.TestCase):
    def test_report_csvs_round_trip_with_metadata(self) -> None:
        with TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "interface_test_20260614_153000.md"
            result_rows = [
                {
                    "panel": "ADIRS",
                    "variants": "1",
                    "lights": "2",
                    "light_words": "1",
                    "inputs": "0",
                    "input_words": "0",
                    "outputs": "0",
                    "output_words": "0",
                    "result": "OK",
                    "comment": "Backlight OK",
                    "updated_at": "2026-06-14 15:31:00",
                }
            ]
            command_history = [
                {
                    "time": "2026-06-14 15:31:10",
                    "status": "OK",
                    "command": "w38 ffff",
                    "response": "OK, received\nready",
                }
            ]
            input_history = [
                {
                    "time": "2026-06-14 15:31:12",
                    "event": "changed",
                    "word": "w36",
                    "previous_word_value": "0100",
                    "word_value": "0000",
                    "changed_mask": "0100",
                    "panel": "VU123",
                    "signal": "bVU125_CF_1_CB_In",
                    "signal_type": "BIT",
                    "bits": "7",
                    "flags": "FLIP",
                    "previous_raw": "1",
                    "raw": "0",
                    "previous_logical": "0",
                    "logical": "1",
                    "comment": "Panel 125VU TRI Cntor Supply CB In",
                    "raw_line": "w36 0000",
                }
            ]
            metadata = {
                "generated_at": "2026-06-14 15:32:00",
                "aircraft": "A320",
                "dat_path": "C:/defs/3014029.dat",
                "port": "COM7",
                "baud_rate": "115200",
                "newline": "CR",
                "board_info": "Tarjeta: canal 2, direccion 145",
                "detected_panel": "ADIRS  @2.145",
                "selected_panel": "ADIRS  @2.145",
                "light_filter": "Backlight",
                "output_filter": "Todas",
                "intensity_mode": "Raw FF",
                "auto_off": "Si",
                "response_wait_seconds": "1.20",
                "response_quiet_seconds": "0.25",
                "command_delay_seconds": "0.05",
                "diagnostic_seconds": "2.00",
            }

            results_path, commands_path, inputs_path = write_report_csvs(
                report_path,
                result_rows,
                command_history,
                input_history,
                metadata,
            )

            with results_path.open(newline="", encoding="utf-8-sig") as csv_file:
                result_csv_rows = list(csv.DictReader(csv_file))
            with commands_path.open(newline="", encoding="utf-8-sig") as csv_file:
                command_csv_rows = list(csv.DictReader(csv_file))
            with inputs_path.open(newline="", encoding="utf-8-sig") as csv_file:
                input_csv_rows = list(csv.DictReader(csv_file))

        self.assertEqual(result_csv_rows[0]["panel"], "ADIRS")
        self.assertEqual(result_csv_rows[0]["aircraft"], "A320")
        self.assertEqual(result_csv_rows[0]["dat_path"], "C:/defs/3014029.dat")
        self.assertEqual(result_csv_rows[0]["port"], "COM7")
        self.assertEqual(result_csv_rows[0]["detected_panel"], "ADIRS  @2.145")
        self.assertEqual(result_csv_rows[0]["response_wait_seconds"], "1.20")
        self.assertEqual(result_csv_rows[0]["output_filter"], "Todas")
        self.assertEqual(result_csv_rows[0]["lights"], "2")
        self.assertEqual(result_csv_rows[0]["light_words"], "1")
        self.assertEqual(result_csv_rows[0]["inputs"], "0")
        self.assertEqual(result_csv_rows[0]["outputs"], "0")
        self.assertEqual(command_csv_rows[0]["status"], "OK")
        self.assertEqual(command_csv_rows[0]["command"], "w38 ffff")
        self.assertEqual(command_csv_rows[0]["response"], "OK, received\nready")
        self.assertEqual(command_csv_rows[0]["selected_panel"], "ADIRS  @2.145")
        self.assertEqual(input_csv_rows[0]["event"], "changed")
        self.assertEqual(input_csv_rows[0]["signal"], "bVU125_CF_1_CB_In")
        self.assertEqual(input_csv_rows[0]["flags"], "FLIP")
        self.assertEqual(input_csv_rows[0]["selected_panel"], "ADIRS  @2.145")

    def test_empty_csvs_keep_headers(self) -> None:
        with TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "empty.md"
            results_path, commands_path, inputs_path = write_report_csvs(report_path, [], [], [], {})

            with results_path.open(newline="", encoding="utf-8-sig") as csv_file:
                result_reader = csv.DictReader(csv_file)
                result_rows = list(result_reader)
                result_fields = result_reader.fieldnames
            with commands_path.open(newline="", encoding="utf-8-sig") as csv_file:
                command_reader = csv.DictReader(csv_file)
                command_rows = list(command_reader)
                command_fields = command_reader.fieldnames
            with inputs_path.open(newline="", encoding="utf-8-sig") as csv_file:
                input_reader = csv.DictReader(csv_file)
                input_rows = list(input_reader)
                input_fields = input_reader.fieldnames

        self.assertEqual(result_rows, [])
        self.assertIn("panel", result_fields or [])
        self.assertIn("selected_panel", result_fields or [])
        self.assertIn("inputs", result_fields or [])
        self.assertIn("outputs", result_fields or [])
        self.assertEqual(command_rows, [])
        self.assertIn("command", command_fields or [])
        self.assertIn("status", command_fields or [])
        self.assertIn("detected_panel", command_fields or [])
        self.assertEqual(input_rows, [])
        self.assertIn("signal", input_fields or [])
        self.assertIn("logical", input_fields or [])
        self.assertIn("raw_line", input_fields or [])


class ReadinessTests(unittest.TestCase):
    def test_operational_status_text_counts_and_escapes_markdown(self) -> None:
        checks = [
            ReadinessCheck("Conexion", READINESS_OK, "Conectado a COM7"),
            ReadinessCheck("Panel", READINESS_WARNING, "Detectado A | seleccionado B"),
            ReadinessCheck("Direct Mode", READINESS_INFO, "Sim Host descargado"),
        ]

        text = build_operational_status_text(
            {"generated_at": "2026-06-15 07:00:00", "port": "COM7"},
            checks,
            {"Notas": ["Linea con | separador"]},
        )

        self.assertIn("Readiness: Ready with warnings", text)
        self.assertIn("OK: 1", text)
        self.assertIn("Warnings: 1", text)
        self.assertIn("Info: 1", text)
        self.assertIn("| Panel | Warning | Detectado A \\| seleccionado B |", text)
        self.assertIn("- Linea con | separador", text)

    def test_readiness_status_counts_accept_unknown_status(self) -> None:
        counts = readiness_status_counts(
            [
                ReadinessCheck("A", READINESS_OK, ""),
                ReadinessCheck("B", "Custom", ""),
            ]
        )

        self.assertEqual(counts[READINESS_OK], 1)
        self.assertEqual(counts["Custom"], 1)


if __name__ == "__main__":
    unittest.main()
