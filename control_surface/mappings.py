from __future__ import annotations

import logging
from functools import partial
from typing import (
    TYPE_CHECKING,
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Tuple,
    TypeVar,
    Union,
)

from ableton.v2.control_surface.mode import SetAttributeMode
from ableton.v3.base import depends
from ableton.v3.control_surface import Component, ControlSurface
from ableton.v3.control_surface.component_map import ComponentMap
from ableton.v3.control_surface.layer import Layer
from ableton.v3.control_surface.mode import (
    CallFunctionMode,
    CompoundMode,
    EnablingAddLayerMode,
    EnablingMode,
    LayerMode,
    Mode,
    ModeButtonBehaviour,
)

from .elements import NUM_COLS, NUM_GRID_COLS, NUM_ROWS
from .live import find_if, lazy_attribute, memoize
from .mode import (
    DISABLED_MODE_NAME,
    MODE_SELECT_MODE_NAME,
    STANDALONE_INIT_MODE_NAME,
    AlternateOnLongPressBehaviour,
    InvertedMode,
    MainModeCategory,
    MainModesComponent,
    ModeSelectBehaviour,
    PersistentSetAttributeMode,
    ReleaseBehaviour,
    ToggleModesComponent,
    get_index_str,
    get_main_mode_category,
)
from .session_ring import SessionRingComponent
from .track_controls import (
    TrackControl,
    TrackControlsButtonBehaviour,
    TrackControlsComponent,
    TrackControlsState,
)
from .track_controls import (
    TrackControlsComponentStrategy as TrackControlsComponentStrategyBase,
)
from .types import Action, MainMode, NavigationTarget, TypedDict
from .ui import (
    DEVICE_NAVIGATION_TARGETS,
    EDIT_TRACK_CONTROL_KEY_MAP,
    MODE_SELECT_KEY_MAP,
    SELECTION_NAVIGATION_TARGETS,
    SESSION_RING_NAVIGATION_TARGETS,
    TRANSPORT_KEY_MAP,
    UTILITY_KEY_MAP,
    KeyMap,
    ModeSelectKeySpecification,
)

if TYPE_CHECKING:
    from .configuration import Configuration

logger = logging.getLogger(__name__)
T = TypeVar("T")


@depends(configuration=None)
def create_mappings(
    control_surface: ControlSurface, configuration: Optional["Configuration"]
) -> Mappings:
    assert configuration
    return MappingsFactory(control_surface, configuration).create()


# Get an element's name by its position.
def get_element(type: str, row: int, col: int):
    return f"{type}_raw[{row * NUM_COLS + col}]"


# Get the (row, col) of a key by its physical number on the device.
def get_key_position(key_number: int) -> Tuple[int, int]:
    row: int
    col: int
    if key_number <= NUM_COLS:
        row = 1
        col = key_number - 1
    else:
        row = 0
        col = key_number - NUM_COLS - 1
    return (row, col)


# Convert a KeyMap to a { element_name: target } map.
def _key_map_elements(
    key_map: KeyMap[T],
) -> Dict[str, T]:
    elements = {}
    for row, key_behaviors in enumerate(key_map):
        for col, key_behavior in enumerate(key_behaviors):
            if key_behavior is not None:
                elements[get_element("buttons", row, col)] = key_behavior
    return elements


# Helper for parsing the config. Replace an element in a key map based on the physical
# key number.
def _replace_in_key_map(key_map: KeyMap[T], key_number: int, value: T) -> KeyMap[T]:
    row, col = get_key_position(key_number)
    # Convert to a list.
    result = [[c for c in r] for r in key_map]
    result[row][col] = value

    # Convert to a tuple.
    assert len(result) == 2
    return (result[0], result[1])


# Spec (as expected by the v3 libs) for mapping a single component, outside of a mode
# context. Can include control -> element mappings, as well as the special "enabled" ->
# bool field.
ComponentSpecification = Dict[str, Union[str, bool]]

# Spec (as expected by the v3 libs) for a mode that gets applied as part of a
# named/primary mode. If this is a dict, it's a "component" -> component_name mapping,
# plus control -> element mappings for the component layer.
SimpleModeSpecification = Union[Mode, Dict[str, str]]

# Internal spec for one of the main user-facing modes. The actual mode definition will
# also include some common setup and overrides from the config.
_MainModeSpecification = Iterable[SimpleModeSpecification]

# Spec (as expected by the v3 libs) for a named mode that gets added to a top-level
# modes component.
RootModeSpecification = Union[
    Mode,
    TypedDict(
        "ModeDefinitionDict",
        {
            "modes": List[SimpleModeSpecification],
            "behaviour": Optional[ModeButtonBehaviour],
            # ...more options that we don't currently care about.
        },
        total=False,
    ),
]

# Spec (as expected by the v3 libs, incomplete but fine for our purposes) for a
# top-level modes component.
ModesComponentSpecification = Dict[
    # Mode name, physical control name, or one of the keys from the control surface's
    # _create_modes_component("modes_component_type", "support_momentary_mode_cycling",
    # ...).
    str,
    Union[
        # Actual mode specification, key is the mode name.
        RootModeSpecification,
        # Control mapping for a button on the component, key is the control name.
        str,
        # Flag recognized by the component map, key is
        # e.g. "support_momentary_mode_cycling".
        bool,
        # Modes component factory, key is "modes_component_type".
        Callable[[], Component],
    ],
]

# Root mappings dictionary, expected to be returned by the main `create_mappings`
# function.
Mappings = Dict[str, Union[ComponentSpecification, ModesComponentSpecification]]

# Mapping descriptors for all possible actions. Each action maps to a single component
# and attribute. The values of the map are (component_name, attribute_name) pairs.
ACTION_MAPPINGS: Dict[Action, Tuple[str, str]] = {
    "arrangement_record": ("Recording", "arrangement_record_button"),
    "auto_arm": ("Auto_Arm_Modes", "cycle_mode_button"),
    "automation_arm": ("Transport", "automation_arm_button"),
    "backlight": ("Backlight_Modes", "cycle_mode_button"),
    "capture_and_insert_scene": ("Recording", "capture_and_insert_scene_button"),
    "capture_midi": ("Transport", "capture_midi_button"),
    "device_lock": ("Device", "device_lock_button"),
    "launch_selected_scene": ("Session", "launch_selected_scene_button"),
    "metronome": ("Transport", "metronome_button"),
    "new": ("Recording", "new_button"),
    "play_toggle": ("Transport", "play_toggle_button"),
    "quantize": ("Clip_Actions", "quantize_button"),
    "redo": ("Undo_Redo", "redo_button"),
    "selected_track_arm": ("Mixer", "selected_track_arm_button"),
    "session_record": ("Recording", "session_record_button"),
    "stop_all_clips": ("Session", "stop_all_clips_button"),
    "tap_tempo": ("Transport", "tap_tempo_button"),
    "undo": ("Undo_Redo", "undo_button"),
}

# (component_name, attribute_name, element_type) tuples for track controls.
TRACK_CONTROL_MAPPINGS: Dict[TrackControl, Tuple[str, str, str]] = {
    "arm": ("Mixer", "arm_buttons", "buttons"),
    "clip_launch": ("Session", "clip_launch_buttons", "buttons"),
    "mute": ("Mixer", "mute_buttons", "buttons"),
    "solo": ("Mixer", "solo_buttons", "buttons"),
    "stop_track_clip": ("Session", "stop_track_clip_buttons", "buttons"),
    "track_select": ("Mixer", "track_select_buttons", "buttons"),
    "volume": ("Mixer", "volume_controls", "vertical_incremental_sliders"),
}


# (component_name, down_button, up_button)
NAVIGATION_TARGET_MAPPINGS: Dict[NavigationTarget, Tuple[str, str, str]] = {
    "device_bank": (
        "Device",
        "prev_bank_button",
        "next_bank_button",
    ),
    "selected_device": (
        "Device_Navigation",
        "prev_button",
        "next_button",
    ),
    "selected_scene": (
        "View_Control",
        "prev_scene_button",
        "next_scene_button",
    ),
    "selected_track": (
        "View_Control",
        "prev_track_button",
        "next_track_button",
    ),
    "session_ring_scenes": (
        "Session_Navigation",
        # Inverted makes more sense for these.
        "up_button",
        "down_button",
    ),
    "session_ring_tracks": (
        "Session_Navigation",
        "left_button",
        "right_button",
    ),
}


# Mappings for the edit modes of the track controls component.
TRACK_CONTROLS_EDIT_TRACK_CONTROL_MAPPINGS: Dict[TrackControl, str] = {
    v: k for k, v in _key_map_elements(EDIT_TRACK_CONTROL_KEY_MAP).items()
}
TRACK_CONTROLS_EDIT_ACTION_MAPPINGS: Dict[Action, str] = {
    v: k for k, v in _key_map_elements(TRANSPORT_KEY_MAP).items()
}
TRACK_CONTROLS_EDIT_ACTION_ALT_MAPPINGS: Dict[Action, str] = {
    v: k for k, v in _key_map_elements(UTILITY_KEY_MAP).items()
}


class MappingsFactory:
    def __init__(self, control_surface: ControlSurface, configuration: "Configuration"):
        self._control_surface = control_surface
        self._configuration = configuration

    def create(self) -> Mappings:
        mappings: Mappings = {}

        mappings["Hardware"] = dict(
            # Turned off by default, since we'll be in `_disabled` mode at startup. This
            # shouldn't be toggled except when entering/exiting `_disabled` mode.
            enable=False,
            # Permanent hardware mappings.
            backlight_sysex="backlight_sysex",
            standalone_sysex="standalone_sysex",
            # Ping input used by tests.
            ping_button="ping_sysex",
        )

        def set_backlight(backlight: bool):
            self._get_component("Hardware").backlight = backlight

        # Toggle modes. Actions get mapped to the cycle buttons.
        for name, initial_state, set_state in (
            (
                "Auto_Arm_Modes",
                self._configuration.auto_arm,
                self._control_surface.set_can_auto_arm,
            ),
            ("Backlight_Modes", self._configuration.backlight, set_backlight),
        ):
            mappings[name] = {
                "modes_component_type": partial(
                    ToggleModesComponent,
                    set_state=set_state,
                    initial_state=initial_state,
                ),
                # Don't want long-press button behavior.
                "support_momentary_mode_cycling": False,
            }

        mappings["Main_Modes"] = {
            "modes_component_type": MainModesComponent,
            # Base mode where no values should ever be sent. Active while the controller
            # is disconnected, which gives us better control over the order of
            # operations when it connects.
            DISABLED_MODE_NAME: {
                "modes": [
                    LayerMode(self._get_component("Background"), Layer()),
                    InvertedMode(EnablingMode(self._get_component("Hardware"))),
                ]
            },
            # Add a mode that just switches to standalone mode and selects the
            # background program. We enter this on connection events to prepare the
            # controller to be placed into hosted mode.
            STANDALONE_INIT_MODE_NAME: {
                "modes": [
                    # Unlike other standalone modes, the init mode doesn't get exited
                    # via the `standalone_exit_button`, which would normally invoke the
                    # transition to hosted mode. Instead, we need to enter hosted mode
                    # explicitly when leaving the mode.
                    InvertedMode(
                        PersistentSetAttributeMode(
                            self._get_component("Hardware"), "standalone", False
                        )
                    ),
                    self._enter_standalone_mode(self._configuration.background_program),
                    # TODO: Make sure LEDs are cleared.
                ]
            },
        }

        # Add specs for any configured modes (plus the mode select mode). We don't need
        # to create mode entries for anything that isn't being rendered, e.g. most or
        # all standalone modes.
        mode_select_specifications: List[ModeSelectKeySpecification] = [
            ("mode_select", None),
            *self._mode_select_key_mappings.values(),
        ]
        for specification in list(mode_select_specifications):
            for mode in specification:
                if mode is not None:
                    mappings["Main_Modes"][mode] = self._create_main_mode(mode)

        return mappings

    def _get_component(self, name: str) -> Component:
        component = self._control_surface.component_map[name]
        assert component
        return component

    # Return a mode which enters standalone mode and activates the given program (if
    # any), and returns to the background program (if any) on exit.
    def _enter_standalone_mode(self, standalone_program: Optional[int]) -> Mode:
        hardware = self._get_component("Hardware")

        def clear_light_caches():
            elements = self._control_surface.elements
            assert elements
            for light in elements.lights_raw:
                light.clear_send_cache()

        def set_standalone_program(standalone_program: Optional[int]):
            if (
                standalone_program is not None
                # Program changes cause blinks and other weirdness on the SoftStep. In
                # case `standalone_program` is the same as the current program (e.g. if
                # it's the same as the already-set background program), we don't need to
                # send a new PC message.
                and standalone_program != hardware.standalone_program
            ):
                hardware.standalone_program = standalone_program

        return CompoundMode(
            # We don't have control of the LEDs, so make sure everything gets rendered
            # as we re-enter hosted mode. This also ensures that LED states will all be
            # rendered on disconnect/reconnect events, since we pass through
            # _standalone_init mode in that case.
            CallFunctionMode(on_exit_fn=clear_light_caches),
            # Set the program attribute before actually switching into standalone mode,
            # so that we don't send an extra message for whatever program is currently
            # active.
            CallFunctionMode(
                on_enter_fn=partial(set_standalone_program, standalone_program)
            ),
            # Send the standalone message on enter, but not the hosted mode message on
            # exit.
            #
            # Regardless of whether `_flush_midi_messages()` is called,
            # `_c_instance.send_midi` seems to batch messages such that sysex messages
            # come first on a given frame, meaning that if we sent the hosted-mode sysex
            # on exit, we'd end up sending the background program change _after_ the
            # controller was already in hosted mode (which defeats the purpose).
            #
            # Re-entering hosted mode happens (if necessary) when the next mode is
            # within the standalone exit button handler. Note this relies on the fact
            # that the `standalone_exit_button` is the only way to re-enter hosted mode
            # from a standalone mode, except for transitions out of
            # _standalone_init_mode (where the background PC gets sent at mode entry,
            # and the transition to hosted mode is handled explicitly in the mode
            # definition).
            PersistentSetAttributeMode(hardware, "standalone", True),
            # The SoftStep seems to keep track of the current LED states for each
            # standalone preset in the setlist. Whenever a preset is loaded, the Init
            # source will fire (potentially setting some LED states explicitly), and any
            # LEDs not affected by the Init source will revert to their state from the
            # last time the preset was active. Even when the controller is in hosted
            # mode, LED updates will affect the state of the most recently-active
            # standalone preset - which can mess with that preset's LED state if it has,
            # for example, toggle buttons that don't use the Init source for LED
            # setup.
            #
            # We avoid this by switching to a background program (whose LED state we
            # don't care about) before returning to host mode.
            CallFunctionMode(
                on_exit_fn=partial(
                    set_standalone_program,
                    self._configuration.background_program,
                )
            ),
        )

    # Mappings of (mode name, alt mode name) -> element for the mode select screen.
    @lazy_attribute
    def _mode_select_key_mappings(self) -> Dict[str, ModeSelectKeySpecification]:
        key_map = MODE_SELECT_KEY_MAP
        for key_number, override in self._configuration.override_modes.items():
            key_map = _replace_in_key_map(key_map, int(key_number), override)

        return _key_map_elements(key_map)

    # Returns the horizontal and vertical (respectively) targets for the nav pad in this
    # mode.
    def _mode_navigation_targets(
        self, mode: MainMode
    ) -> Tuple[Optional[NavigationTarget], Optional[NavigationTarget]]:
        category = get_main_mode_category(mode)
        if category is MainModeCategory.device:
            return DEVICE_NAVIGATION_TARGETS
        elif category in [
            MainModeCategory.track_controls,
            MainModeCategory.edit_track_controls,
        ]:
            return SESSION_RING_NAVIGATION_TARGETS
        elif category is MainModeCategory.standalone:
            return (None, None)
        else:
            return SELECTION_NAVIGATION_TARGETS

    def _action_mode(
        self,
        # Value is the element name, key is the action to map.
        mappings: Dict[str, Action],
    ) -> List[SimpleModeSpecification]:
        component_mappings: Dict[str, Dict[str, str]] = {}
        for element, action in mappings.items():
            if action not in ACTION_MAPPINGS:
                logger.warning(f"unrecognized action: {action}")
                continue

            component, attribute = ACTION_MAPPINGS[action]
            if component not in component_mappings:
                component_mappings[component] = {}
            component_mappings[component][attribute] = element

        return [
            dict(component=component, **attributes)
            for component, attributes in component_mappings.items()
        ]

    def _navigation_mode(
        self,
        horizontal_target: Optional[NavigationTarget],
        vertical_target: Optional[NavigationTarget],
    ) -> List[SimpleModeSpecification]:
        component_mappings: Dict[str, Dict[str, str]] = {}
        targets_and_elements: Iterable[Tuple[Optional[NavigationTarget], str, str]] = (
            (horizontal_target, "nav_left_button", "nav_right_button"),
            # The down button generally increases values, e.g. the selected scene index,
            # session ring position...
            (vertical_target, "nav_up_button", "nav_down_button"),
        )
        for navigation_target, down_button, up_button in targets_and_elements:
            if navigation_target:
                component, down_attribute, up_attribute = NAVIGATION_TARGET_MAPPINGS[
                    navigation_target
                ]
                if component not in component_mappings:
                    component_mappings[component] = {}
                component_mappings[component][down_attribute] = down_button
                component_mappings[component][up_attribute] = up_button

        return [
            dict(component=component, **attributes)
            for component, attributes in component_mappings.items()
        ]

    @lazy_attribute
    def _mode_select_button(self):
        return get_element("buttons", 0, 4)

    @lazy_attribute
    def _action_button(self):
        return get_element("buttons", 1, 4)

    def _create_main_mode(self, mode: MainMode) -> RootModeSpecification:
        main_mode_specification = self._main_mode_factory(mode)()

        # Create the mode button and set its long-press behavior depending on the
        # configuration.
        behaviour = None
        mode_category = get_main_mode_category(mode)

        def is_leading_mode(
            key_mapping: Optional[ModeSelectKeySpecification],
        ):
            return key_mapping and (key_mapping[0] == mode)

        mode_select_key_mapping = find_if(
            is_leading_mode, self._mode_select_key_mappings.values()
        )
        alternate_mode = mode_select_key_mapping[1] if mode_select_key_mapping else None
        alternate_mode_category = (
            get_main_mode_category(alternate_mode) if alternate_mode else None
        )

        if alternate_mode_category is MainModeCategory.standalone or (
            alternate_mode is None and mode_category is MainModeCategory.standalone
        ):
            # When switching into a standalone mode on long press, we need need to wait
            # until the button is released before performing the switch, otherwise the
            # SoftStep will immediately register an input in standalone mode.
            behaviour = ReleaseBehaviour(alternate_mode=alternate_mode)
        elif mode_category is MainModeCategory.mode_select:
            # Long-pressing mode select selects the previous mode.
            behaviour = ModeSelectBehaviour()
        elif mode_category is MainModeCategory.track_controls:
            # Track controls mode buttons need special handling when the mode has been
            # "deleted".
            behaviour = TrackControlsButtonBehaviour(
                track_controls=self._get_component(mode.title()),
                alternate_mode=alternate_mode,
            )
        else:
            # In most cases, just assign this mode to short-press and the alternate mode
            # to long-press.
            behaviour = AlternateOnLongPressBehaviour(alternate_mode)

        # The key safety manager gets set up during element creation, this is a no-op...
        key_safety_mode: Mode = CallFunctionMode()
        # ...unless the strategy has been overridden in the configuration.
        if mode in self._configuration.override_key_safety_strategies:
            assert self._control_surface.elements
            key_safety_mode = SetAttributeMode(
                self._control_surface.elements.key_safety_manager,
                "strategy",
                self._configuration.override_key_safety_strategies[mode],
            )

        # Control layers which are present in all non-standalone modes.
        main_modes_mode: SimpleModeSpecification
        expression_mode: SimpleModeSpecification
        if mode_category is MainModeCategory.standalone:
            # Standalone modes shouldn't bind anything (except the exit button, which
            # gets set up elsewhere).
            main_modes_mode = CallFunctionMode()
            expression_mode = CallFunctionMode()
        else:
            # Bind the mode select button.
            main_modes_mode = {
                "component": "Main_Modes",
                "mode_select_button": self._mode_select_button,
            }

            # Bind the expression pedal.
            expression_mode = dict(
                component="Device", expression_pedal="expression_slider"
            )

        # Navigation controls.
        navigation_mode = self._navigation_mode(*(self._mode_navigation_targets(mode)))

        # The configuration accepts overrides as tuples or collections of tuples (for
        # convenience with the helper functions). Build the flattened list of overrides;
        # regular flatten doesn't work, since we don't want to flatten the actual
        # override tuples.
        configuration_overrides: List[Tuple[str, str, str]] = []
        for override in self._configuration.override_elements.get(mode, []):
            if len(override) > 0 and isinstance(override[0], str):
                configuration_overrides.append(override)  # type: ignore
            else:
                for sub_override in override:
                    assert not isinstance(sub_override, str)
                    configuration_overrides.append(sub_override)

        configuration_override_modes = [
            {"component": component, attr: element}
            for element, component, attr in configuration_overrides
        ]

        return {
            "modes": [
                # Special key safety strategy if any.
                key_safety_mode,
                # Make sure any unbound LEDs are turned off.
                dict(component="Background", lights="lights"),
                # Mode select button.
                main_modes_mode,
                # Expression pedal.
                expression_mode,
                # Nav pad bindings.
                *navigation_mode,
                # Actual mode.
                *main_mode_specification,
                # Overrides from the configuration.
                *configuration_override_modes,
            ],
            "behaviour": behaviour,
        }

    ## Specs for individual main modes.
    def _main_mode_factory(
        self, name: MainMode
    ) -> Callable[[], _MainModeSpecification]:
        category = get_main_mode_category(name)
        if category is MainModeCategory.track_controls:
            return partial(self._track_controls_mode, name)
        elif category is MainModeCategory.edit_track_controls:
            return partial(self._edit_track_controls_mode, name)
        elif category is MainModeCategory.standalone:
            return partial(self._standalone_mode, name)
        else:
            return {
                "device_bank_select": self._device_bank_select_mode,
                "device_expression_map": self._device_expression_map_mode,
                "device_parameters_increment": self._device_parameters_increment_mode,
                "device_parameters_pressure": self._device_parameters_pressure_mode,
                "device_parameters_pressure_latch": self._device_parameters_pressure_latch_mode,
                "device_parameters_xy": self._device_parameters_xy_mode,
                "mode_select": self._mode_select_mode,
                "transport": self._transport_mode,
                "utility": self._utility_mode,
            }[name]

    def _mode_select_mode(self) -> _MainModeSpecification:
        component_mode = dict(component="Main_Modes")
        for (
            element,
            mode_select_specification,
        ) in self._mode_select_key_mappings.items():
            component_mode[f"{mode_select_specification[0]}_button"] = element
        return [component_mode]

    # Convenience.
    def __device_action_button_mode(self) -> List[SimpleModeSpecification]:
        return self._action_mode({self._action_button: "device_lock"})

    def _device_bank_select_mode(self) -> _MainModeSpecification:
        return [
            dict(component="Device", bank_select_buttons="grid_buttons"),
            *self.__device_action_button_mode(),
        ]

    def _device_expression_map_mode(self) -> _MainModeSpecification:
        # Hack to enable popups with the current expression parameter value in this
        # mode. These are distracting elsewhere, so we just enable them here.
        # SetAttributeMode( self._elements.expression_slider, "enable_popups", True, ),

        return [
            dict(component="Device", expression_mapping_buttons="grid_buttons"),
            *self.__device_action_button_mode(),
        ]

    def _device_parameters_increment_mode(self) -> _MainModeSpecification:
        return [
            # SetAttributeMode(
            #     self._get_component("Device")._parameters_component,
            #     "parameter_on_color",
            #     "Device.IncrementParameterOn",
            # ),
            dict(
                component="Device",
                parameter_controls="grid_vertical_incremental_sliders",
            ),
            *self.__device_action_button_mode(),
        ]

    def _device_parameters_pressure_mode(self) -> _MainModeSpecification:
        return [
            dict(
                component="Device",
                parameter_controls="grid_pressure_sliders",
            ),
            *self.__device_action_button_mode(),
        ]

    def _device_parameters_pressure_latch_mode(self) -> _MainModeSpecification:
        return [
            dict(
                component="Device",
                alt_parameter_controls="grid_pressure_latching_sliders",
            ),
            *self.__device_action_button_mode(),
        ]

    def _device_parameters_xy_mode(self) -> _MainModeSpecification:
        return [
            dict(
                component="Device",
                parameter_controls="grid_right_xy_sliders",
                alt_parameter_controls="grid_left_xy_latching_sliders",
            ),
            *self.__device_action_button_mode(),
        ]

    def _transport_mode(self) -> _MainModeSpecification:
        return self._action_mode(_key_map_elements(TRANSPORT_KEY_MAP))

    def _utility_mode(self) -> _MainModeSpecification:
        return self._action_mode(_key_map_elements(UTILITY_KEY_MAP))

    ## Track controls modes setup.

    # Return the component after setting the strategy for edit events and mode creation.
    @memoize
    def __track_controls_component(self, index_str: str) -> TrackControlsComponent:
        component_name = f"Track_Controls_{index_str}"
        component: TrackControlsComponent = self._get_component(component_name)

        component.strategy = TrackControlsComponentStrategy(
            self._control_surface.component_map, index_str
        )

        return component

    def _track_controls_mode(self, name: MainMode) -> _MainModeSpecification:
        index = get_index_str(name)
        component = self.__track_controls_component(index)

        return [
            # In some cases (e.g. when transitioning directly from the edit mode), gets
            # immediately disabled by `_possibly_disable_component` unless there's a
            # layer attached, so we need the empty layer here.
            EnablingAddLayerMode(component=component, layer=Layer()),
            component.track_controls_mode,
        ]

    def _edit_track_controls_mode(self, name: MainMode) -> _MainModeSpecification:
        index = get_index_str(name)
        component = self.__track_controls_component(index)
        return [
            EnablingAddLayerMode(
                component=component,
                layer=Layer(
                    cancel_button=self._mode_select_button,
                    edit_action_button=self._action_button,
                ),
            ),
            component.edit_mode,
        ]

    def _standalone_mode(self, name: MainMode) -> _MainModeSpecification:
        index = int(get_index_str(name))

        # Force all current MIDI/control state to be written to the device. This
        # works-ish - sometimes CCs still get sent after the switch to standalone mode
        # for some reason. But they seem to always get flushed before the main program
        # change is sent.
        def flush():
            self._control_surface._ownership_handler.commit_ownership_changes()
            self._control_surface._flush_midi_messages()

            # Make sure the display gets re-rendered in hosted mode even if the text
            # hasn't changed.
            elements = self._control_surface.elements
            assert elements
            elements.display.clear_send_cache()

        return [
            # We use the same CC as nav left (80) for the exit button, so a) we don't
            # reduce the number of useful CCs for MIDI mapping in standalone mode, and
            # b) the mode select button could be triggered by button mashing if the
            # controller ever got stuck in hosted mode when it was supposed to be in
            # standalone mode.
            dict(component="Main_Modes", standalone_exit_button="nav_left_button"),
            # Make sure all LEDs are cleared. This affects the standalone background
            # program state.
            CallFunctionMode(on_enter_fn=flush),
            # Make sure the background has no bindings, so no more LED updates get sent.
            LayerMode(self._get_component("Background"), Layer()),
            # Enter standalone mode and select the program.
            self._enter_standalone_mode(index - 1),
        ]


class TrackControlsComponentStrategy(TrackControlsComponentStrategyBase):
    @depends(session_ring=None)
    def __init__(
        self,
        component_map: ComponentMap,
        index_str: str,
        session_ring: Optional[SessionRingComponent] = None,
    ):
        super().__init__()
        self._component_map = component_map
        self._track_controls_mode_name = f"track_controls_{index_str}"

        assert session_ring
        self._session_ring = session_ring

    def cancel_edit(self):
        self._main_modes_component.selected_mode = MODE_SELECT_MODE_NAME

    def finish_edit(self):
        for _ in range(2):
            self._main_modes_component.selected_mode = None
            self._main_modes_component.push_mode(self._track_controls_mode_name)

    @lazy_attribute
    def _main_modes_component(self) -> MainModesComponent:
        return self._component_map["Main_Modes"]

    def create_mode(self, state: Optional[TrackControlsState]) -> Mode:
        def get_component_mode(element, component_name: str, attribute: str):
            return EnablingAddLayerMode(
                component=self._component_map[component_name],
                layer=Layer(**{attribute: element}),
            )

        if state is None:
            return CallFunctionMode()

        # Get the action mode.
        action_mode = get_component_mode(
            get_element("buttons", NUM_ROWS - 1, NUM_COLS - 1),
            *(ACTION_MAPPINGS[state.action]),
        )

        top_component_name, top_attribute, top_type = TRACK_CONTROL_MAPPINGS[
            state.top_control
        ]
        bottom_component_name, bottom_attribute, bottom_type = TRACK_CONTROL_MAPPINGS[
            state.bottom_control
        ]

        track_controls_mode: Mode
        num_tracks: int
        if state.top_control == state.bottom_control:
            is_wide = False
            if state.top_control == "clip_launch":
                # 1x8 or 2x4 depending on the session ring size (which depends on the
                # configuration).
                num_tracks = int(
                    NUM_GRID_COLS * NUM_ROWS / self._session_ring.num_scenes
                )
                # For the 1x8 case, select the wide grid.
                is_wide = num_tracks > NUM_GRID_COLS
            else:
                num_tracks = NUM_GRID_COLS * NUM_ROWS
            element = f"grid_{'wide_' if is_wide else ''}{top_type}"
            track_controls_mode = get_component_mode(
                element, top_component_name, top_attribute
            )
        else:
            top_element, bottom_element = [
                f"grid_{side}_{side_type}"
                for side, side_type in (("top", top_type), ("bottom", bottom_type))
            ]
            track_controls_mode = CompoundMode(
                get_component_mode(top_element, top_component_name, top_attribute),
                get_component_mode(
                    bottom_element, bottom_component_name, bottom_attribute
                ),
            )
            num_tracks = NUM_GRID_COLS

        # Only need to set the number of tracks, we always highlight the full number of
        # scenes.
        session_ring_mode = SetAttributeMode(
            self._session_ring, "highlight_tracks", num_tracks
        )

        return CompoundMode(
            action_mode,
            track_controls_mode,
            session_ring_mode,
        )
