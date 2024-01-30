from typing import TYPE_CHECKING, Union

if not TYPE_CHECKING:
    # At runtime, just assign the non-literal variants.
    Action: "TypeAlias" = "str"
    ClipSlotAction: "TypeAlias" = "str"
    KeyNumber: "TypeAlias" = Union[str, int]
    KeySafetyStrategy: "TypeAlias" = "str"
    MainMode: "TypeAlias" = "str"
    NavigationTarget: "TypeAlias" = "str"
    Quantization: "TypeAlias" = "str"
    TrackControl: "TypeAlias" = "str"

    # This is actually called to define typed dicts, we need a real implementation.
    def TypedDict(*_a, **_k):
        return dict
else:
    # At type-check time, define more detailed types.
    from typing_extensions import Literal as _Literal
    from typing_extensions import TypeAlias, TypedDict  # noqa: F401

    ##
    # Literals for enumerable types. We use these instead of enums for
    # simplicity in the configuration, and greater flexibility to
    # hack/extend the built-in mappings.

    # Standalone actions that can be assigned to a single button.
    Action = _Literal[
        "automation_arm",
        "auto_arm",
        "backlight",
        "capture_and_insert_scene",
        "capture_midi",
        "device_lock",
        "launch_selected_scene",
        "metronome",
        "play_toggle",
        "arrangement_record",
        "redo",
        "quantize",
        "selected_track_arm",
        "session_record",
        "stop_all_clips",
        "tap_tempo",
        "undo",
        "new",
    ]

    # Possible clip actions on long-press.
    ClipSlotAction = _Literal["stop_track_clips"]

    KeyNumber = _Literal[
        # We need to allow strings in key number dicts so that configs can be
        # represented as valid JSON for song-specific overrides.
        "0",
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
        "7",
        "8",
        "9",
        0,
        1,
        2,
        3,
        4,
        5,
        6,
        7,
        8,
        9,
    ]

    KeySafetyStrategy = _Literal[
        # Only one key can be triggered at a time.
        "single_key",
        # Keys immediately adjacent to an active key cannot be triggered.
        "adjacent_lockout",
        # Any key can be triggered at any time.
        "all_keys",
    ]

    # Modes that can be assigned to mode select buttons.
    MainMode = _Literal[
        # Uncategorized modes.
        "mode_select",
        "transport",
        "utility",
        # Device modes.
        "device_bank_select",
        "device_expression_map",
        "device_parameters_increment",
        "device_parameters_pressure",
        "device_parameters_pressure_latch",
        "device_parameters_xy",
        # Configurable track controls and associated edit modes.
        "track_controls_1",
        "track_controls_2",
        "track_controls_3",
        "track_controls_4",
        "track_controls_5",
        "edit_track_controls_1",
        "edit_track_controls_2",
        "edit_track_controls_3",
        "edit_track_controls_4",
        "edit_track_controls_5",
        # Modes to load each possible standalone preset in your device's
        # setlist (configured from the SoftStep editor).
        "standalone_1",
        "standalone_2",
        "standalone_3",
        "standalone_4",
        "standalone_5",
        "standalone_6",
        "standalone_7",
        "standalone_8",
        "standalone_9",
        "standalone_10",
        "standalone_11",
        "standalone_12",
        "standalone_13",
        "standalone_14",
        "standalone_15",
        "standalone_16",
    ]

    # Available nav pad controls.
    NavigationTarget = _Literal[
        "device_bank",
        "selected_device",
        "selected_scene",
        "selected_track",
        "session_ring_scenes",
        "session_ring_tracks",
    ]

    # Possible quantization grid sizes. Matches up with Live.Song.RecordingQuantization.
    Quantization = _Literal[
        "quarter",
        # [sic]
        "eight",
        "eight_triplet",
        "eight_eight_triplet",
        "sixtenth",
        "sixtenth_triplet",
        "sixtenth_sixtenth_triplet",
        "thirtysecond",
    ]

    TrackControl = _Literal[
        "arm",
        "clip_launch",
        "mute",
        "solo",
        "stop_track_clip",
        "track_select",
        "volume",
    ]
