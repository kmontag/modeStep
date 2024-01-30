# UI constants, separated so they're also available to build tools like the image
# generator.
from typing import TYPE_CHECKING, Collection, Dict, Optional, Tuple, TypeVar

if TYPE_CHECKING:
    # Don't use relative imports at runtime, so this can be included without a package
    # context.
    from .types import Action, MainMode, NavigationTarget, TrackControl

T = TypeVar("T")

## Key maps.

# Type definition for a structure that specifies a `T` for each key position. This is a
# 2x5 matrix corresponding to the `Elements` matrices, i.e. the first row represents the
# top row of keys.
KeyMap = Tuple[Collection[Optional[T]], Collection[Optional[T]]]

# Primary and alternate (i.e. long-press) mappings for each key in the mode select
# screen. This list is in order of key numbers 1-9.
ModeSelectKeySpecification = Tuple["MainMode", Optional["MainMode"]]

MODE_SELECT_KEY_MAP: KeyMap[ModeSelectKeySpecification] = (
    (
        # Device modes on buttons 6-8.
        ("device_parameters_xy", "device_bank_select"),
        ("device_parameters_pressure", "device_parameters_pressure_latch"),
        ("device_parameters_increment", "device_expression_map"),
        # Transport/utility on button 9.
        ("transport", "utility"),
    ),
    (
        # Bottom row, control presets for multiple tracks.
        ("track_controls_1", "edit_track_controls_1"),
        ("track_controls_2", "edit_track_controls_2"),
        ("track_controls_3", "edit_track_controls_3"),
        ("track_controls_4", "edit_track_controls_4"),
        ("track_controls_5", "edit_track_controls_5"),
    ),
)

# Transport mode actions.
TRANSPORT_KEY_MAP: KeyMap["Action"] = (
    ("stop_all_clips", "selected_track_arm", "automation_arm", "tap_tempo"),
    (
        "launch_selected_scene",
        "arrangement_record",
        "play_toggle",
        "metronome",
        "session_record",
    ),
)

# Utility mode actions.
UTILITY_KEY_MAP: KeyMap[Optional["Action"]] = (
    ("backlight", "redo", "quantize", "new"),
    ("auto_arm", "undo", "capture_midi", "capture_and_insert_scene", "session_record"),
)

## Navigation targets.

# (horizontal, vertical)
NavigationTargets = Tuple["NavigationTarget", "NavigationTarget"]

# 2-dimensional nav target pairs.
DEVICE_NAVIGATION_TARGETS: NavigationTargets = ("selected_device", "device_bank")
SELECTION_NAVIGATION_TARGETS: NavigationTargets = ("selected_track", "selected_scene")
SESSION_RING_NAVIGATION_TARGETS: NavigationTargets = (
    "session_ring_tracks",
    "session_ring_scenes",
)


## Track controls.

# Default control types on keys 1-5, respectively.
TRACK_CONTROLS: Tuple["TrackControl", ...] = (
    "volume",
    "arm",
    "solo",
    "mute",
    "clip_launch",
)

# Key map for the top/bottom track control edit screens.
EDIT_TRACK_CONTROL_KEY_MAP: KeyMap["TrackControl"] = (
    ("track_select", None, "stop_track_clip", "clip_launch"),
    (
        "volume",
        "arm",
        "solo",
        "mute",
    ),
)


# Display names.
TRACK_CONTROL_DISPLAY_NAMES: Dict["TrackControl", str] = {
    "track_select": "SeL",
    "arm": "Arm",
    "mute": "Mute",
    "solo": "Solo",
    "volume": "Vol",
    "clip_launch": "Clip",
    "stop_track_clip": "Stop",
}

## Mode names.
MAIN_MODE_DISPLAY_NAMES: Dict["MainMode", str] = {
    "device_bank_select": "BanK",
    "device_expression_map": "Expr",
    "device_parameters_increment": "Incr",
    "device_parameters_pressure": "Prss",
    "device_parameters_pressure_latch": "PrLt",
    "device_parameters_xy": " XY ",
    "mode_select": " __  __ ",
    "transport": "Trns",
    "utility": "Util",
}
