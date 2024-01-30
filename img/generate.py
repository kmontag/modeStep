# Generates diagrams for the README.
import importlib.machinery
import importlib.util
import os
import typing
from collections import namedtuple

import svgwrite
from typing_extensions import TypedDict

if typing.TYPE_CHECKING:
    # The type checker sees packages in the project root.
    import control_surface.elements.hardware as hardware
    import control_surface.types as types
    import control_surface.ui as ui
else:
    # Outside the type checker, we don't have direct import access to the main control
    # surface, but the sysex constants would be too annoying to duplicate. Load it manually
    # from the path, see
    # https://csatlas.com/python-import-file-module/#import_a_file_in_a_different_directory.
    def _load_module_from_path(name: str, path: str):
        path = os.path.join(path, f"{name}.py")
        loader = importlib.machinery.SourceFileLoader(name, path)
        spec = importlib.util.spec_from_loader(name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        return module

    hardware = _load_module_from_path(
        "hardware",
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "..",
            "control_surface",
            "elements",
        ),
    )
    types = _load_module_from_path(
        "types",
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)), "..", "control_surface"
        ),
    )
    ui = _load_module_from_path(
        "ui",
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "..",
            "control_surface",
        ),
    )


T = typing.TypeVar("T")

Pedal = namedtuple("Pedal", "desc long_press_desc color", defaults=(None, None, None))

PedalOpt = typing.Union[Pedal, None]

# Secondary color for text in the pedals.
alt_pedal_text_color = "#6a6b6c"

# Color for text on the dark device background.
bg_text_color = "#cecfd0"

red = "red"
yellow = "yellow"
green = "green"

# Dimensions for copmonents.
height = 350
spacing = height / 8
pedal_size = (height - 2 * spacing) / 2

screen_height = pedal_size / 2
screen_width = height - screen_height - spacing * 3 / 2

width = (spacing + pedal_size) * 5 + (screen_width + spacing)


class DiagramNavArgs(TypedDict):
    vertical_nav: str
    horizontal_nav: str


def diagram(
    filename: str,
    pedal1: PedalOpt = None,
    pedal2: PedalOpt = None,
    pedal3: PedalOpt = None,
    pedal4: PedalOpt = None,
    pedal5: PedalOpt = None,
    pedal6: PedalOpt = None,
    pedal7: PedalOpt = None,
    pedal8: PedalOpt = None,
    pedal9: PedalOpt = None,
    pedal0: PedalOpt = None,
    display: str = "",
    vertical_nav: str = "",
    horizontal_nav: str = "",
) -> svgwrite.Drawing:
    dwg = svgwrite.Drawing(filename, size=(width, height))

    # Background box.
    dwg.add(dwg.rect(size=(width, height), fill="#414243", rx=10, ry=10))

    # Hacky helper to render potentially multi-line text. Lots of
    # one-off logic and adjustments.
    def add_desc(
        desc: str,
        x_center: float,
        y_center: float,
        max_height: float,
        base_font_size: float,
    ):
        lines = desc.split("\n")
        assert len(lines) <= 3

        max_line_length = max([len(line) for line in lines])

        is_middle_size = False
        if max_line_length <= 5 and len(lines) == 1:
            font_multiplier = 1.8
        elif max_line_length <= 8:
            font_multiplier = 1.15
            is_middle_size = True
        else:
            font_multiplier = 1

        font_size = f"{font_multiplier * base_font_size}em"

        if len(lines) == 3:
            segments = [
                (lines[0], y_center - max_height / 2),
                (lines[1], y_center),
                (lines[2], y_center + max_height / 2),
            ]
        elif len(lines) == 2:
            if is_middle_size:
                offset = max_height * 0.28
            else:
                offset = max_height / 4

            segments = [(lines[0], y_center - offset), (lines[1], y_center + offset)]
        else:
            segments = [(desc, y_center)]

        for text, y in segments:
            dwg.add(
                dwg.text(
                    text,
                    fill="black",
                    style=f"font-family: monospace; font-size: {font_size};",
                    text_anchor="middle",
                    dominant_baseline="middle",
                    x=[x_center],
                    y=[y],
                )
            )

    for idx, pedal in enumerate(
        [
            pedal1,
            pedal2,
            pedal3,
            pedal4,
            pedal5,
            pedal6,
            pedal7,
            pedal8,
            pedal9,
            pedal0,
        ]
    ):
        x_offset = spacing / 2 + (pedal_size + spacing) * (idx % 5)
        y_offset = spacing / 2 + (pedal_size + spacing) * (1 - int(idx / 5.0))
        pedal_stroke_width = 4

        # Boxes for individual pedals.
        dwg.add(
            dwg.rect(
                insert=(x_offset, y_offset),
                size=(pedal_size, pedal_size),
                stroke=(
                    pedal.color
                    if (pedal is not None and pedal.color is not None)
                    else "white"
                ),
                fill="white",
                fill_opacity=1.0,
                stroke_width=pedal_stroke_width,
                rx=5,
                ry=5,
            )
        )

        # Number labels.
        dwg.add(
            dwg.text(
                str((idx + 1) % 10),
                fill=bg_text_color,
                text_anchor="middle",
                dominant_baseline="middle",
                style="font-family: monospace;",
                x=[x_offset + pedal_size / 2],
                y=[y_offset + pedal_size + spacing / 4],
            )
        )

        if pedal:
            base_font_size = 1.2 if pedal.long_press_desc else 1.5
            padding_pct = 0.4
            # Function description at the top (if there's a long-press
            # action) or middle of the pedal box.
            add_desc(
                desc=pedal.desc,
                x_center=x_offset + pedal_size / 2,
                y_center=y_offset
                + (pedal_size / 4 if pedal.long_press_desc else pedal_size / 2),
                max_height=pedal_size
                * (1 - padding_pct)
                * (0.5 if pedal.long_press_desc else 0.9),
                base_font_size=base_font_size,
            )
            if pedal.long_press_desc:
                # Line through the middle of the pedal box.
                dwg.add(
                    dwg.line(
                        start=(x_offset, y_offset + pedal_size / 2 - 2),
                        end=(x_offset + pedal_size, y_offset + pedal_size / 2 - 2),
                        stroke="black",
                        stroke_width=1,
                        fill="black",
                    )
                )

                # Long press function description at the bottom of the
                # pedal box.
                add_desc(
                    desc=pedal.long_press_desc,
                    x_center=(x_offset + pedal_size / 2),
                    y_center=(y_offset + pedal_size * 3 / 4 + 3),
                    max_height=(pedal_size * (1 - padding_pct) / 2),
                    base_font_size=base_font_size,
                )
                dwg.add(
                    dwg.text(
                        "(long press)",
                        fill=alt_pedal_text_color,
                        style="font-family: monospace; font-size: 0.8em;",
                        dominant_baseline="hanging",
                        x=[x_offset + pedal_stroke_width],
                        y=[y_offset + pedal_size / 2 + 1],
                    )
                )

    # Screen.
    dwg.add(
        dwg.rect(
            insert=((spacing + pedal_size) * 5 + spacing / 2, spacing / 2),
            size=(screen_width, screen_height),
            fill="black",
            rx=3,
            ry=3,
        )
    )

    screen_x_offset = ((spacing + pedal_size) * 5) + spacing / 2
    dwg.add(
        dwg.text(
            display,
            textLength=screen_width - spacing / 2,
            text_anchor="middle",
            dominant_baseline="middle",
            fill="red",
            style="font-size: 2em; font-family: monospace;",
            y=[spacing / 2 + screen_height / 2],
            x=[screen_x_offset + screen_width / 2],
            **{"xml:space": "preserve"},
        )
    )

    # Nav pad and label.
    nav_y_offset = screen_height + spacing
    dwg.add(
        dwg.rect(
            insert=(screen_x_offset, nav_y_offset),
            size=(screen_width, screen_width),
            fill="white",
            rx=8,
            ry=8,
        )
    )

    dwg.add(
        dwg.text(
            "Nav",
            text_anchor="middle",
            dominant_baseline="middle",
            fill=bg_text_color,
            style="font-size: 0.8em; font-family: monospace;",
            x=[screen_x_offset + screen_width / 2],
            y=[nav_y_offset + screen_width + spacing / 4],
        )
    )

    # Up/down nav text.
    if vertical_nav:
        dwg.add(
            dwg.text(
                "↑",
                text_anchor="middle",
                dominant_baseline="middle",
                fill=alt_pedal_text_color,
                style="font-size: 4em; font-family: monospace;",
                y=[nav_y_offset + screen_width / 4],
                x=[screen_x_offset + screen_width / 8],
            )
        )
        add_desc(
            desc=vertical_nav,
            x_center=screen_x_offset + screen_width / 2,
            y_center=nav_y_offset + screen_width / 4,
            max_height=screen_width / 4,
            base_font_size=1.5,
        )
        dwg.add(
            dwg.text(
                "↓",
                text_anchor="middle",
                dominant_baseline="middle",
                fill=alt_pedal_text_color,
                style="font-size: 4em; font-family: monospace;",
                y=[nav_y_offset + screen_width / 4],
                x=[screen_x_offset + screen_width * 7 / 8],
            )
        )

    # Line in nav pad.
    dwg.add(
        dwg.line(
            start=(screen_x_offset, nav_y_offset + screen_width / 2),
            end=(screen_x_offset + screen_width, nav_y_offset + screen_width / 2),
            stroke="black",
            stroke_width=1,
            fill="black",
        )
    )

    # Left/right nav text.
    if horizontal_nav:
        dwg.add(
            dwg.text(
                "←",
                text_anchor="middle",
                dominant_baseline="middle",
                fill=alt_pedal_text_color,
                style="font-size: 4em; font-family: monospace;",
                y=[nav_y_offset + screen_width * 3 / 4],
                x=[screen_x_offset + screen_width / 8],
            )
        )
        add_desc(
            desc=horizontal_nav,
            x_center=screen_x_offset + screen_width / 2,
            y_center=nav_y_offset + screen_width * 3 / 4,
            max_height=screen_width / 4,
            base_font_size=1.5,
        )
        dwg.add(
            dwg.text(
                "→",
                text_anchor="middle",
                dominant_baseline="middle",
                fill=alt_pedal_text_color,
                style="font-size: 4em; font-family: monospace;",
                y=[nav_y_offset + screen_width * 3 / 4],
                x=[screen_x_offset + screen_width * 7 / 8],
            )
        )
    return dwg


# Shorthand method for pedal definitions.
def pedal(
    desc: str,
    long_press_desc: typing.Union[str, None] = None,
    color: typing.Union[str, None] = None,
):
    return Pedal(desc=desc, long_press_desc=long_press_desc, color=color)


if __name__ == "__main__":
    # Hacky import of stuff from consts in the parent, so we can run this
    # outside of a python module context. See
    # https://stackoverflow.com/a/11158224.
    import inspect
    import os
    import sys

    current_frame = inspect.currentframe()
    assert current_frame

    currentdir = os.path.dirname(os.path.abspath(inspect.getfile(current_frame)))
    parentdir = os.path.dirname(currentdir)
    sys.path.insert(0, parentdir)

    def display_name(mode: types.MainMode):
        # Replace uppercase characters that are just there because
        # they look better in the SoftStep's rendering.
        return ui.MAIN_MODE_DISPLAY_NAMES[mode].replace("K", "k")

    session_record_pedal = pedal("Session\nRecord")
    session_record = {"pedal5": session_record_pedal}
    mode_select: typing.Dict[str, PedalOpt] = {
        "pedal0": pedal("Mode\nSelect", "Jump to\nRecent Mode")
    }

    def navigation(mode: types.MainMode) -> DiagramNavArgs:
        navigation_mode_labels: typing.Dict[types.NavigationTarget, str] = {
            "selected_scene": "Selected\nScene",
            "selected_track": "Selected\nTrack",
            "device_bank": "Device\nBank",
            "selected_device": "Selected\nDevice",
            "session_ring_scenes": "Session\nRing\nScenes",
            "session_ring_tracks": "Session\nRing\nTracks",
        }

        # Just hard-code the categorization logic, will need to be updated if it changes
        # on the application side.
        horizontal_nav: types.NavigationTarget
        vertical_nav: types.NavigationTarget
        if mode.startswith("device_"):
            horizontal_nav, vertical_nav = ui.DEVICE_NAVIGATION_TARGETS
        elif mode.startswith("track_controls_") or mode.startswith(
            "edit_track_controls_"
        ):
            horizontal_nav, vertical_nav = ui.SESSION_RING_NAVIGATION_TARGETS
        elif mode in ("mode_select", "transport", "utility"):
            horizontal_nav, vertical_nav = ui.SELECTION_NAVIGATION_TARGETS
        else:
            raise RuntimeError(f"unexpected nav mode: {mode}")

        return {
            "horizontal_nav": navigation_mode_labels[horizontal_nav],
            "vertical_nav": navigation_mode_labels[vertical_nav],
        }

    device_lock = {
        "pedal5": pedal("Device\nLock"),
    }
    interstitial_mode = {"pedal0": pedal("Cancel", "Jump to\nRecent Mode")}

    def params_from_key_map(
        key_map: ui.KeyMap[T], to_pedal: typing.Callable[[T], Pedal]
    ):
        args = {}
        for row, specs in enumerate(key_map):
            for col, spec in enumerate(specs):
                if spec is not None:
                    key_number = (
                        ((hardware.NUM_ROWS - 1 - row) * hardware.NUM_COLS) + col + 1
                    ) % (hardware.NUM_ROWS * hardware.NUM_COLS)
                    pedal = to_pedal(spec)
                    if pedal is not None:
                        args[f"pedal{key_number}"] = pedal

        return args

    track_control_descriptions: typing.Dict[types.TrackControl, str] = {
        "volume": "Volume\nControls",
        "arm": "Arm\nButtons",
        "solo": "Solo\nButtons",
        "mute": "Mute\nButtons",
        "clip_launch": "Launch\nClips",
    }

    mode_descriptions: typing.Dict[types.MainMode, str] = {
        "device_parameters_xy": "XY Pos.\nParams Mode",
        "device_bank_select": "Device\nBank Mode",
        "device_parameters_pressure": "Pressure\nParams Mode",
        "device_parameters_pressure_latch": "Prss. Params\nLatch Mode",
        "device_parameters_increment": "Y Incr.\nParams Mode",
        "device_expression_map": "Expr. Pedal\nMap Mode",
        "transport": "Transport\nMode",
        "utility": "Utility\nMode",
    }

    for index, track_control in enumerate(ui.TRACK_CONTROLS):
        track_controls_mode: types.MainMode = f"track_controls_{index + 1}"  # type: ignore
        edit_track_controls_mode: types.MainMode = f"edit_track_controls_{index + 1}"  # type: ignore
        mode_descriptions[track_controls_mode] = track_control_descriptions[
            track_control
        ]
        mode_descriptions[edit_track_controls_mode] = "Edit"

    mode_select_params = {
        **params_from_key_map(
            ui.MODE_SELECT_KEY_MAP,
            lambda m: pedal(
                mode_descriptions[m[0]],
                None if m[1] is None else mode_descriptions[m[1]],
                (
                    green
                    if m[0].startswith("device_")
                    else (red if m[0].startswith("track_controls_") else yellow)
                ),
            ),
        ),
        **interstitial_mode,
        **navigation("mode_select"),
    }
    diagram(
        "mode-select.svg",
        display=ui.MAIN_MODE_DISPLAY_NAMES["mode_select"][0:4],
        **mode_select_params,
    ).save(pretty=True)

    # Define pedals for actions here; their positions will be computed
    # dynamically for the transport/utility modes.
    action_pedals: typing.Dict[types.Action, Pedal] = {
        "automation_arm": pedal("Automation\nArm"),
        "auto_arm": pedal("Implicit\nArm\nOn/Off"),
        "backlight": pedal("Backlight\nOn/Off"),
        "capture_and_insert_scene": pedal("Capture\n& Insert\nScene"),
        "capture_midi": pedal("Capture\nMIDI"),
        "launch_selected_scene": pedal("Launch\nSelected\nScene"),
        "metronome": pedal("Metronome\nOn/Off"),
        "new": pedal("New Clip"),
        "play_toggle": pedal("Play/\nStop"),
        "arrangement_record": pedal("Arrangement\nRecord"),
        "quantize": pedal("Quantize\nClip"),
        "redo": pedal("Redo"),
        "selected_track_arm": pedal("Arm\nSelected\nTrack"),
        "session_record": session_record_pedal,
        "stop_all_clips": pedal("Stop\nAll\nClips"),
        "tap_tempo": pedal("Tap\nTempo"),
        "undo": pedal("Undo"),
    }

    transport_mode_pedal_params = params_from_key_map(
        ui.TRANSPORT_KEY_MAP, lambda action: action_pedals[action]
    )
    diagram(
        "transport-mode.svg",
        display=display_name("transport"),
        **transport_mode_pedal_params,
        **mode_select,
        **navigation("transport"),
    ).save(pretty=True)

    utility_mode_pedal_params = params_from_key_map(
        ui.UTILITY_KEY_MAP, lambda action: action_pedals[action]
    )
    diagram(
        "utility-mode.svg",
        display=display_name("utility"),
        **utility_mode_pedal_params,
        **mode_select,
        **navigation("utility"),
    ).save(pretty=True)

    diagram(
        "device-parameters-pressure-mode.svg",
        pedal1=pedal("Pressure\nParam 5"),
        pedal2=pedal("Pressure\nParam 6"),
        pedal3=pedal("Pressure\nParam 7"),
        pedal4=pedal("Pressure\nParam 8"),
        pedal6=pedal("Pressure\nParam 1"),
        pedal7=pedal("Pressure\nParam 2"),
        pedal8=pedal("Pressure\nParam 3"),
        pedal9=pedal("Pressure\nParam 4"),
        display=display_name("device_parameters_pressure"),
        **navigation("device_parameters_pressure"),
        **device_lock,
        **mode_select,
    ).save(pretty=True)

    diagram(
        "device-parameters-increment-mode.svg",
        pedal1=pedal("Y Incr.\nParam 5"),
        pedal2=pedal("Y Incr.\nParam 6"),
        pedal3=pedal("Y Incr.\nParam 7"),
        pedal4=pedal("Y Incr.\nParam 8"),
        pedal6=pedal("Y Incr.\nParam 1"),
        pedal7=pedal("Y Incr.\nParam 2"),
        pedal8=pedal("Y Incr.\nParam 3"),
        pedal9=pedal("Y Incr.\nParam 4"),
        display=display_name("device_parameters_increment"),
        **navigation("device_parameters_increment"),
        **device_lock,
        **mode_select,
    ).save(pretty=True)

    diagram(
        "device-parameters-xy-mode.svg",
        pedal1=pedal("XY Latch\nParams\n5/6"),
        pedal2=pedal("XY Latch\nParams\n7/8"),
        pedal3=pedal("XY\nParams\n5/6"),
        pedal4=pedal("XY\nParams\n7/8"),
        pedal6=pedal("XY Latch\nParams\n1/2"),
        pedal7=pedal("XY Latch\nParams\n3/4"),
        pedal8=pedal("XY\nParams\n1/2"),
        pedal9=pedal("XY\nParams\n3/4"),
        display=display_name("device_parameters_xy"),
        **navigation("device_parameters_xy"),
        **device_lock,
        **mode_select,
    ).save(pretty=True)

    diagram(
        "expression-pedal-map-mode.svg",
        pedal1=pedal("Map to\nParam\n5"),
        pedal2=pedal("Map to\nParam\n6"),
        pedal3=pedal("Map to\nParam\n7"),
        pedal4=pedal("Map to\nParam\n8"),
        pedal6=pedal("Map to\nParam\n1"),
        pedal7=pedal("Map to\nParam\n2"),
        pedal8=pedal("Map to\nParam\n3"),
        pedal9=pedal("Map to\nParam\n4"),
        display=display_name("device_expression_map"),
        **navigation("device_expression_map"),
        **device_lock,
        **mode_select,
    ).save(pretty=True)

    diagram(
        "device-bank-mode.svg",
        pedal1=pedal("Select\nBank 5"),
        pedal2=pedal("Select\nBank 6"),
        pedal3=pedal("Select\nBank 7"),
        pedal4=pedal("Select\nBank 8"),
        pedal6=pedal("Select\nBank 1"),
        pedal7=pedal("Select\nBank 2"),
        pedal8=pedal("Select\nBank 3"),
        pedal9=pedal("Select\nBank 4"),
        display=display_name("device_bank_select"),
        **navigation("device_bank_select"),
        **device_lock,
        **mode_select,
    ).save(pretty=True)

    track_controls_nav = navigation("track_controls_1")
    diagram(
        "solo-arm-mode.svg",
        pedal1=pedal("Arm\nTrack 1"),
        pedal2=pedal("Arm\nTrack 2"),
        pedal3=pedal("Arm\nTrack 3"),
        pedal4=pedal("Arm\nTrack 4"),
        pedal5=pedal("Session\nRecord"),
        pedal6=pedal("Solo\nTrack 1"),
        pedal7=pedal("Solo\nTrack 2"),
        pedal8=pedal("Solo\nTrack 3"),
        pedal9=pedal("Solo\nTrack 4"),
        display=f"{ui.TRACK_CONTROL_DISPLAY_NAMES['solo'][:2]}{ui.TRACK_CONTROL_DISPLAY_NAMES['arm'][:2]}",
        **mode_select,
        **track_controls_nav,
    ).save(pretty=True)

    diagram(
        "mute-mode.svg",
        pedal1=pedal("Mute\nTrack 5"),
        pedal2=pedal("Mute\nTrack 6"),
        pedal3=pedal("Mute\nTrack 7"),
        pedal4=pedal("Mute\nTrack 8"),
        pedal5=pedal("Session\nRecord"),
        pedal6=pedal("Mute\nTrack 1"),
        pedal7=pedal("Mute\nTrack 2"),
        pedal8=pedal("Mute\nTrack 3"),
        pedal9=pedal("Mute\nTrack 4"),
        display=ui.TRACK_CONTROL_DISPLAY_NAMES["mute"],
        **mode_select,
        **track_controls_nav,
    ).save(pretty=True)

    diagram(
        "track-volume-mode.svg",
        pedal1=pedal("Track 5\nVolume"),
        pedal2=pedal("Track 6\nVolume"),
        pedal3=pedal("Track 7\nVolume"),
        pedal4=pedal("Track 8\nVolume"),
        pedal5=pedal("Session\nRecord"),
        pedal6=pedal("Track 1\nVolume"),
        pedal7=pedal("Track 2\nVolume"),
        pedal8=pedal("Track 3\nVolume"),
        pedal9=pedal("Track 4\nVolume"),
        display=ui.TRACK_CONTROL_DISPLAY_NAMES["volume"],
        **mode_select,
        **track_controls_nav,
    ).save(pretty=True)

    edit_track_control_pedals: typing.Dict[types.TrackControl, Pedal] = {
        "track_select": pedal("Select\nTrack"),
        "stop_track_clip": pedal("Stop\nTrack\nClip"),
        "clip_launch": pedal("Clip\nLaunch"),
        "arm": pedal("Arm"),
        "solo": pedal("Solo"),
        "mute": pedal("Mute"),
        "volume": pedal("Volume"),
    }

    edit_track_control_pedal_params: typing.Dict[str, PedalOpt] = {
        **params_from_key_map(
            ui.EDIT_TRACK_CONTROL_KEY_MAP,
            lambda track_control: edit_track_control_pedals[track_control],
        ),
        "pedal0": pedal("Cancel", "Disable\nPreset"),
        "pedal5": pedal("Custom Action\n(Transport)", "Custom Action\n(Util)"),
    }
    diagram(
        "edit-track-control.svg",
        display="1Top",
        **navigation("edit_track_controls_1"),
        **edit_track_control_pedal_params,
    ).save(pretty=True)

# Local Variables:
# compile-command: "python generate.py"
# End:
