# Interface Tester

Python desktop application for testing aircraft panels through a serial connection using interface definition `.dat` files selected by the operator.

Current version: `0.2.39`.

## Recent Changes

### Version 0.2.39

- The `Report` tab is hidden at startup and can be shown or hidden from `View > Show Report`.
- An optional `Help` tab is available from `View > Show Help`.
- Hiding `Report` or `Help` does not destroy their controls, results, or current state.
- `Help` documents common transmitted commands, usage examples, received formats, and warnings for commands that change persistent configuration or move hardware.
- The public release does not contain panel `.dat` definitions. They must be loaded externally from the GUI.

### Version 0.2.38

- Added automatic display testing based on 7- or 8-bit `BIT-FLD` fields detected in the `.dat` file.
- Each display word receives two characters so the `S` command does not continue writing into following words.
- For ATCTCAS, the app detects `w30`, `w31`, and `w32`. The initial `12 34 56` map identifies the physical position of all six digits.
- The configurable sequence cycles through alphanumeric values, supports a custom step time, can be stopped, and can restore `00` when finished.

## Run in Development

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

## Hardware-Free Smoke Test

Before packaging or testing real panels, run the GUI smoke test without opening a serial connection:

```powershell
python tools\gui_smoke.py
```

The smoke test requires the A320 `.dat` file to be available locally. It validates light commands, input/output plans, reports, operational status, optional tabs, and session round trips.

## Current Workflow

1. Press `Load .dat` and select an interface definition.
2. Review the available panel table. It lists families with detected lights, inputs, or non-light `CO` outputs.
3. Refresh and select the serial port.
4. Enter the baud rate.
5. Connect.
6. Press `Info` to send `i` and detect the motherboard address.
7. Optionally press `?` to request the command list supported by the board.
8. Select or confirm the panel.
9. Open `Lights` and review `Generated commands` before transmitting anything.
10. Select the light type and intensity profile.
11. Use `Turn lights on`, `Turn lights off`, or `Automatic test`.
12. Keep `Turn off when finished` enabled when the automatic test must send OFF at the end.
13. Use `Stop and turn off` to interrupt a sequence and send OFF.
14. Use the checklist controls to record results and move through pending panels.
15. Review `Operational status` and `Pre-HW checklist` before connecting real hardware.

When `Info` returns an address used by multiple panels and the channel is not enough to distinguish them, the app opens a candidate selector. The detected board and panel remain visible in the header on every tab.

`Change address` lets the operator search the loaded `.dat`, review side/variant, channel, and address, and then confirm the sequence:

```text
A <address>
SAVE
i
```

If the panel detected by `Info` differs from the selected panel, the app asks for confirmation before sending light commands. Use `Set detected` to choose an exact variant manually when needed.

`Panel details` shows variants, addresses, lights, inputs, and interpreted non-light `CO` outputs from the loaded definition.

## Light Tests

The generated command table shows every word, calculated mask, and grouped signals. Available actions include:

- `Copy ON`, `Copy OFF`, `Copy details`, and `Export commands`.
- `Turn word on` and `Turn word off` for the selected word.
- `Turn signal on` and `Turn signal off` for an individual signal.

If the selected filter produces no light commands, the app reports it and prevents copying or exporting an empty command set.

Light filters:

- `All`: backlights, lights, and annunciators.
- `Backlight`: backlighting signals only.
- `Lights / Ann`: lights and annunciators without backlighting.

Intensity profiles:

- `Raw FF`: sets every field bit to `1`.
- `Percent 100`: writes decimal `100` (`64` hexadecimal) to `FLOAT-FLD` fields.

For RAW light writes, bits `0..7` generate the low byte (`00ff`) and bits `8..15` generate the high byte (`ff00`). Examples:

```text
w 1 00ff
w 1 ff00
w 1 ffff
w 1 0000
```

Tokens are always separated by spaces. Individual signal OFF commands use `w <word> 0000`, so they clear the complete word.

## Remembered Settings

The app automatically stores operational settings from the latest session:

- Last loaded `.dat` and definition directory.
- Selected serial port, baud rate, and line ending.
- Light type, intensity profile, test duration, and automatic OFF setting.
- Non-light output category used by output details and exports.
- Serial response wait time, quiet time, command delay, and raw-read window.
- Display text and word values.

On Windows, settings are stored in:

```text
%LOCALAPPDATA%\InterfaceTester\settings.json
```

If the last `.dat` still exists, the app loads it automatically at startup.

## Serial Diagnostics

The `Terminal` tab contains serial diagnostics, the general log, and a custom command field.

- `Read raw`: reads available bytes for the configured duration.
- `Save serial log`: saves the TX/RX trace in `Diagnostics`.
- `Clear serial log`: clears the current session trace.
- `Resp. s`: maximum wait for a response after sending a command.
- `Quiet time (s)`: byte-free interval used to consider a response complete.
- `Command delay (s)`: delay between sending a command and reading its response.

The serial log includes timestamps, source, direction (`TX`/`RX`), escaped control characters, and hexadecimal bytes. The app keeps the latest 5,000 TX/RX events in memory and records how many older events were discarded.

Custom commands are transmitted exactly as entered. Commands related to addresses, EEPROM, registers, NVRAM, reset, or motors require confirmation because they may change persistent state or move hardware.

## Operational Status

`Operational status` opens a Markdown view containing:

- App version, `.dat`, aircraft/project, and serial metadata.
- Definition validation, port, connection, baud rate, and selected panel status.
- Panel detected through `Info` or manual selection.
- A warning when the detected and selected panels differ.
- Mapped capability counts, ON/OFF commands, words, checklist progress, command history, and serial trace.
- A Direct Mode reminder: Sim Host is assumed to be downloaded and is not controlled by this app.

The view can be copied or exported to `StatusSnapshots`.

`Pre-HW checklist` opens a Markdown checklist covering definition context, connection, Direct Mode, lights, inputs, outputs, and minimum evidence. It can be copied or exported.

## Direct Mode Inputs

The `Inputs` tab tests switches, knobs, levers, encoders, potentiometers, circuit breakers, and other inputs:

1. Connect the serial port.
2. Confirm that Sim Host is downloaded.
3. Press `Monitor VER 3`.
4. Move one physical control at a time.
5. Review the decoded table and the raw `VER 3` console.
6. Press `Stop monitor` when finished.
7. Use `Reset panel` only when a board reset is required.
8. Use `Input details` or `Export inputs` to inspect the `CI` map.

When a `VER 3` response contains word/value pairs, the app decodes them against `CI` signals from the loaded `.dat`.

Input event meanings:

- `baseline`: first value observed for a word; establishes the reference.
- `baseline_signal`: active signal found in the first reading.
- `changed`: a later value changed and matched a `CI` signal.
- `unmapped_change`: bits changed, but no `CI` signal from the selected panel uses that mask.
- `changed_mirrored`: the change matched only after reflecting the 16-bit order. This is reported as an inference and does not modify the `.dat`.

Signals with `FLIP` show both raw and logical values. The receiver reconstructs lines even when serial bytes arrive in fragments.

Analog `FLOAT-FLD` inputs depend on firmware verbose output. If they do not appear, use the custom `ANALOG` command to inspect sensitivity. The app does not modify sensitivity automatically.

Stopping monitoring ends the app read loop, but does not currently send `VER 0`; that behavior remains pending hardware validation.

## Displays and Indicators

The `Outputs` tab provides additional direct tests:

- `Send display`: sends `S <word> <text>`, for example `S 38 105435`.
- `Automatic display test`: detects words containing compatible 7- or 8-bit display `BIT-FLD` fields.
- `Step (s)`: controls how long each pattern remains visible.
- `Stop`: interrupts the display sweep.
- `Restore 00`: writes `00` to all tested display words when finished.
- `demo`, `ST`, and `ST_Brushless`: start firmware-dependent tests when supported.
- `Output details`: opens a Markdown map of non-light `CO` outputs.
- `Export outputs`: saves that map in `OutputPlans`.
- `Category`: filters by `Display`, `Indicator`, `Enable`, `Matrix/Sign`, `Actuator`, or `Discrete/CB`.

The automatic display test sends exactly two characters per word:

```text
S 30 12
S 31 34
S 32 56
```

For ATCTCAS, `w30`, `w31`, and `w32` are used to locate the six display positions. After the position map, the configured sequence is sent with each character repeated for the corresponding word.

An automatic display test requires an exact detected panel or a family with only one variant. It cannot start while `VER 3` monitoring or an automatic light test is active.

The output plan does not automatically generate raw commands for actuators, indicators, or discrete outputs. It provides a map for deciding whether `demo`, `ST`, `ST_Brushless`, or a manually validated `w` command is appropriate.

## Optional Tabs

The `View` menu controls two tabs that are hidden at startup:

- `Show Report`: shows or hides `Report` without losing controls, comments, or results.
- `Show Help`: shows or hides the integrated command reference.

The `Help` tab covers:

- `i` for board information.
- `?` for firmware help.
- `VER 3` for input monitoring.
- `w <word> <hex value>` with `00ff`, `ff00`, `ffff`, and `0000` examples.
- `S <word> <text>` for compatible displays.
- `A <address>` and `SAVE` for persistent address assignment.
- Common `Info` and `VER 3` response formats.
- `baseline`, `baseline_signal`, `changed`, and `unmapped_change` meanings.

## Reports

The `Report` tab stores panel results during the session and exports files to `Reports`. It starts hidden and is enabled through `View > Show Report`.

Recommended workflow:

1. Select or detect the panel.
2. Run the required test.
3. Choose `OK`, `FAIL`, `N/A`, or `Not tested`.
4. Enter a comment when needed.
5. Press `Save panel`.
6. Repeat for the remaining panels.
7. Press `Save report`.

Saving a report creates four files with the same timestamp:

- `interface_test_YYYYMMDD_HHMMSS.md`: complete Markdown report.
- `interface_test_YYYYMMDD_HHMMSS_results.csv`: panel result matrix.
- `interface_test_YYYYMMDD_HHMMSS_commands.csv`: command and response history.
- `interface_test_YYYYMMDD_HHMMSS_inputs.csv`: decoded `VER 3` input history.

CSV rows include the `.dat`, port, baud rate, line ending, detected board and panel, selected panel, light filter, intensity, and serial timings. Result rows also include light, input, output, and word counts.

Use status filters, `Next pending`, `Save and next`, and the checklist buttons to move efficiently through pending panels.

When `Info` detects a different address, the app starts a new board context and clears commands, inputs, results, and trace data from the previous panel. The new board's `i` event and trace are preserved.

## Test Sessions

Use `Save session` to pause work and continue later. Sessions are stored as JSON files in `Sessions` and include:

- Loaded `.dat` path.
- Panel results and current comment.
- Command and TX/RX history.
- Decoded input history and latest `VER 3` baseline.
- Detected panel.
- Light/output filters, test configuration, and serial timings.

`Load session` restores the saved state. If the original `.dat` path does not exist, the app reports the problem without modifying the current session.

Indexed panels are grouped by family. For example, `RMP[0]`, `RMP[1]`, and `RMP[2]` appear as one `RMP` family.

## Definition Validation

When a `.dat` file is loaded, the app reports validation results in the GUI and console. It checks for:

- Signals referencing panels without an active `define`.
- Repeated addresses that may be ambiguous.
- Duplicate `channel.address` combinations.
- `FLOAT-FLD` lights with widths other than 8 or 16 bits.
- Defined panels without testable capabilities.

Validation is informational. It does not modify the `.dat` or block use of the app.

## Windows Packaging

Build the executable folder with:

```powershell
.\build_windows.ps1
```

The script creates the virtual environment when needed, installs dependencies, runs tests, cleans build output, and creates `dist\InterfaceTester\InterfaceTester.exe` with cx_Freeze.

Useful options:

```powershell
.\build_windows.ps1 -SkipInstall
.\build_windows.ps1 -SkipTests
```

Distribute the complete `dist\InterfaceTester` folder, not only the executable.

Validate a build before packaging:

```powershell
python tools\pre_release_check.py
```

Individual checks:

```powershell
python tools\gui_smoke.py
python tools\release_check.py
python tools\exe_smoke.py
```

## Delivery Package

Create a versioned folder, ZIP, and SHA256 checksum from the current build:

```powershell
.\package_release.ps1 -SkipBuild
```

Build and package in one step:

```powershell
.\package_release.ps1 -SkipInstall
```

Artifacts are written to `Releases\InterfaceTester-vX.Y.Z-win` and `Releases\InterfaceTester-vX.Y.Z-win.zip`. The folder includes `RELEASE_NOTES.txt`, `release_manifest.json`, and `SHA256SUMS.txt`.

To reduce Windows Defender and SmartScreen warnings:

- Sign the executable with a code-signing certificate.
- Do not use UPX or similar executable compressors.
- Distribute a complete folder or signed installer.
- Keep application name, version, and publisher consistent.

Unsigned builds may still display an "unknown publisher" warning.

Executable configuration lives in `setup.py`, including version, name, description, and optional inclusion of a local `InterfaceDefinition` directory.

The public `0.2.39` release does not include the A320 or ATR `.dat` files. The operator must select the appropriate definition through `Load .dat`. This keeps definitions outside the public `main` branch.
