from __future__ import annotations

import json
from logging import getLogger
from typing import Dict, Iterable, List, NamedTuple, Optional, Tuple, Union

from .mappings import (
    ACTION_MAPPINGS,
    NAVIGATION_TARGET_MAPPINGS,
    get_element,
    get_key_position,
)
from .types import (
    Action,
    ClipSlotAction,
    KeyNumber,
    KeySafetyStrategy,
    MainMode,
    NavigationTarget,
    Quantization,
    TrackControl,
)

logger = getLogger(__name__)

Numeric = Union[int, float]

# Song-specific config via clip names. Prefixes are followed by JSON strings. To replace
# your entire config, add a clip with a name like:
#
#   ms={"initial_mode": "device_parameters_pressure"}
#
# To keep your overall config but replace some fields, add a clip with a name like:
#
#   ms<{"wide_clip_launch": true}
#
SONG_CONFIGURATION_REPLACE_PREFIX = "ms="
SONG_CONFIGURATION_MERGE_PREFIX = "ms<"


# Global control surface configuration. To customize, create a file called `user.py` in
# the repository root directory, and export a `configuration` object, for example:
#
#   # user.py
#   from .control_surface.configuration import Configuration
#
#   configuration = Configuration(
#       # ...
#   )
#
# See `types.py` for lists of possible values for `MainMode`, `KeySafetyStrategy`, etc.
class Configuration(NamedTuple):
    # Startup mode.
    initial_mode: MainMode = "transport"

    # Initial "previous mode", i.e. the mode when the mode button is long-pressed.
    initial_last_mode: MainMode = "mode_select"

    # Whether to auto-arm/"pink arm" selected tracks. Can be toggled from utility
    # mode. If you have other control surfaces (e.g. Push) which enable auto-arm, they
    # may override this behavior.
    auto_arm: bool = False

    # Backlight on/off state (or `None` to leave it unmanaged) to be set at
    # startup.
    #
    # Note as of SoftStep firmware v2.0.3, you might see some weird LED behavior
    # when using the backlight with modeStep. This appears to be a bug in the
    # firmware (since it also happens when using the SoftStep editor).
    backlight: Optional[bool] = None

    # Backlight on/off state (or `None` to leave it unmanaged) to be set at
    # exit.
    disconnect_backlight: Optional[bool] = None

    # Add a behavior when long pressing a clip (currently just "stop_track_clips" is available).
    clip_long_press_action: Optional[ClipSlotAction] = None

    # If true, use a 1x8 box for the clip launch grid, instead of 2x4.
    wide_clip_launch: bool = False

    # Quantization settings.
    quantize_to: Quantization = "sixtenth"
    quantize_amount: float = 1.0  # 1.0 is full quantization.

    # Whether to scroll the session ring along with scenes/tracks.
    link_session_ring_to_scene_selection: bool = False
    link_session_ring_to_track_selection: bool = False

    # The behavior when multiple keys are pressed at the same time.
    key_safety_strategy: KeySafetyStrategy = "all_keys"

    # The CC value at which keys should be considered fully pressed. Lower values ==
    # more sensitive.
    full_pressure: int = 37

    # The range of CC value change per second for incremental controls. The first number
    # is the change per second when the control is lightly pressed, the second
    # is the change per second when the control is fully pressed.
    incremental_steps_per_second: Tuple[Numeric, Numeric] = (10, 127)

    # A tuple with the (completely_off, completely_on) CC values for your expression
    # pedal.
    expression_pedal_range: Tuple[int, int] = (0, 127)

    # The delta in CC value that constitutes intentional movement of the expression
    # pedal. Any smaller movements will be ignored. Use this if your expression pedal
    # sends CC noise when it's not being touched.
    expression_pedal_movement_threshold: int = 2

    # Initial device parameter index (from 0-7) to be controlled by the expression
    # pedal.
    initial_expression_parameter: Optional[int] = None

    # Program change message (0-indexed) to be sent before switching the SoftStep out of
    # standalone mode and into hosted mode. Program changes 0 to 15 will load presets
    # 1-16 in your setlist.
    #
    # Use this to prevent LED states for toggle buttons from getting overwritten in your
    # other standalone presets while using modeStep.
    #
    # To avoid interference with the display when using the nav pad, make sure the nav's
    # display mode is set to None in this preset.
    background_program: Optional[int] = None

    # Program change message (0-indexed) to be sent when exiting Live, after the
    # SoftStep has been placed back into standalone mode.
    disconnect_program: Optional[int] = None

    # Customize the track controls on mode select keys 1-5. For example:
    #
    #   override_track_controls = {1: (
    #       # Top control.
    #       "solo",
    #       # Bottom control.
    #       "arm",
    #       # Key 5 action.
    #       "stop_all_clips"
    #   )}
    #
    override_track_controls: Dict[
        KeyNumber, Optional[Tuple[TrackControl, TrackControl, Action]]
    ] = {}

    # Override the key safety strategy for specific modes, for example:
    #
    #     key_safety_strategy = "all_keys"
    #     override_key_safety_strategies = {"device_parameters_xy": "adjacent_lockout"}
    #
    override_key_safety_strategies: Dict[MainMode, KeySafetyStrategy] = {}

    # Customize keys on the mode select screen. For example, to load your own standalone
    # programs on key 5 short/long press:
    #
    #   override_modes = {5: ("standalone_1", "standalone_2")}
    #
    override_modes: Dict[KeyNumber, Optional[Tuple[MainMode, Optional[MainMode]]]] = {}

    # Override specific control elements in any mode. You can use the helpers in this
    # file to override keys with known actions and nav controls:
    #
    #   override_elements = {"transport": [
    #       # Replace the Tap Tempo button with Capture MIDI.
    #       override_key_with_action(9, "capture_midi"),
    #
    #       # Replace the Metronome button with device nav controls.
    #       override_key_with_nav(4, horizontal="selected_device", vertical="device_bank"),
    #
    #       # Override the main nav controls.
    #       override_nav(horizontal="session_ring_tracks", vertical="session_ring_scenes")
    #   ]}
    #
    # If you're adventurous and/or know your way around Live v3 control surfaces, you
    # can add more complex overrides for any (element, component, attribute):
    #
    #   override_elements = {"transport": [
    #       ("grid_left_pressure_sliders", "Device", "parameter_controls")
    #   ]}
    #
    override_elements: Dict[
        MainMode,
        Iterable[
            Union[ElementOverride, List[ElementOverride], Tuple[ElementOverride, ...]]
        ],
    ] = {}


def get_configuration(song) -> Configuration:
    # Load a local configuration if possible, or fall back to the default.
    local_configuration: Optional[Configuration] = None
    try:
        from ..user import (  # type: ignore
            configuration as local_configuration,  # type: ignore
        )

        logger.info("loaded local configuration")

    except (ImportError, ModuleNotFoundError):
        logger.info("loaded default configuration")

    configuration = local_configuration or Configuration()

    # Try to load song-specific config.
    try:
        assert song
        for track in song.tracks:
            for clip_slot in track.clip_slots:
                clip = clip_slot.clip
                if clip is not None:
                    name: Optional[str] = clip.name
                    if name is not None:
                        json_str: Optional[str] = None
                        replace: bool = False
                        for prefix, replaces in (
                            (
                                SONG_CONFIGURATION_REPLACE_PREFIX,
                                True,
                            ),
                            (SONG_CONFIGURATION_MERGE_PREFIX, False),
                        ):
                            if name.startswith(prefix):
                                json_str = name[len(prefix) :]
                                replace = replaces

                        if json_str is not None:
                            new_configuration_attrs = (
                                {} if replace else configuration._asdict()
                            )
                            new_configuration_attrs.update(json.loads(json_str))
                            # This technically isn't correctly typed, since the parsed
                            # object contains arrays instead of tuples. Hopefully tests
                            # would catch any related breakage.
                            configuration = Configuration(**new_configuration_attrs)

                            logger.info("loaded song configuration")

    except Exception as e:
        logger.warning(f"error reading song config: {e}")

    logger.info(f"using configuration: {configuration._asdict()}")
    return configuration


# Element name, component name, attribute name, e.g. ("grid_pressure_sliders", "Device",
# "parameter_controls").
ElementOverride = Tuple[str, str, str]

##
# Helpers for overriding elements, see above for usage examples. Keys are the
# physical key numbers on the SoftStep.


# Override a key with an action.
def override_key_with_action(key: int, action: Action) -> ElementOverride:
    row, col = get_key_position(key)
    action_mapping = ACTION_MAPPINGS[action]
    return (
        get_element("buttons", row=row, col=col),
        action_mapping[0],
        action_mapping[1],
    )


# Set a key's directional sensors to nav controls.
def override_key_with_nav(
    key: int,
    horizontal: Optional[NavigationTarget] = None,
    vertical: Optional[NavigationTarget] = None,
) -> List[ElementOverride]:
    row, col = get_key_position(key)
    left, right, down, up = [
        get_element(f"{dir}_buttons", row, col)
        for dir in ("left", "right", "down", "up")
    ]
    return _override_elements_with_nav(
        left=left,
        right=right,
        down=down,
        up=up,
        horizontal=horizontal,
        vertical=vertical,
    )


# Override the main nav pad assignments.
def override_nav(
    horizontal: Optional[NavigationTarget] = None,
    vertical: Optional[NavigationTarget] = None,
) -> List[ElementOverride]:
    return _override_elements_with_nav(
        left="nav_left_button",
        right="nav_right_button",
        down="nav_down_button",
        up="nav_up_button",
        horizontal=horizontal,
        vertical=vertical,
    )


def _override_elements_with_nav(
    left: str,
    right: str,
    up: str,
    down: str,
    horizontal: Optional[NavigationTarget],
    vertical: Optional[NavigationTarget],
) -> List[ElementOverride]:
    results: List[ElementOverride] = []
    for down_element, up_element, target in (
        (left, right, horizontal),
        # The down button increases values - think selected scene.
        (up, down, vertical),
    ):
        # Get a unique control name based on an element name.
        def background_control_name(element: str):
            return element.replace("[", "_").replace("]", "_")

        component, down_button, up_button = (
            # If no target specified, disable the elements.
            (
                "Background",
                background_control_name(left),
                background_control_name(right),
            )
            if target is None
            else NAVIGATION_TARGET_MAPPINGS[target]
        )

        results.append((down_element, component, down_button))
        results.append((up_element, component, up_button))
    return results
