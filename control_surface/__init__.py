from __future__ import annotations

import logging
import typing
from functools import partial

from ableton.v3.base import const, depends, inject, listens, task
from ableton.v3.control_surface import (
    ControlSurface,
    ControlSurfaceSpecification,
    create_skin,
)
from ableton.v3.control_surface.capabilities import (
    CONTROLLER_ID_KEY,
    NOTES_CC,
    PORTS_KEY,
    REMOTE,
    SCRIPT,
    controller_id,
    inport,
    outport,
)

from .clip_actions import ClipActionsComponent
from .clip_slot import ClipSlotComponent
from .colors import Skin
from .configuration import Configuration, get_configuration
from .device import DeviceComponent
from .display import display_specification
from .elements import NUM_GRID_COLS, NUM_ROWS, Elements
from .hardware import HardwareComponent
from .live import lazy_attribute
from .mappings import (
    DISABLED_MODE_NAME,
    STANDALONE_INIT_MODE_NAME,
    TRACK_CONTROLS_EDIT_ACTION_ALT_MAPPINGS,
    TRACK_CONTROLS_EDIT_ACTION_MAPPINGS,
    TRACK_CONTROLS_EDIT_TRACK_CONTROL_MAPPINGS,
    create_mappings,
)
from .mixer import MixerComponent
from .recording import RecordingComponent
from .scene import SceneComponent
from .session import SessionComponent
from .session_navigation import SessionNavigationComponent
from .session_ring import SessionRingComponent
from .sysex import (
    DEVICE_FAMILY_BYTES,
    MANUFACTURER_ID_BYTES,
    SYSEX_STANDALONE_MODE_ON_REQUESTS,
)
from .track_controls import TrackControlsComponent, TrackControlsState
from .transport import TransportComponent
from .types import Action, TrackControl
from .ui import TRACK_CONTROLS
from .undo_redo import UndoRedoComponent
from .view_control import ViewControlComponent

logger = logging.getLogger(__name__)


def get_capabilities():
    return {
        CONTROLLER_ID_KEY: controller_id(
            vendor_id=0x1F38,
            # Firmware v2.x.
            product_ids=(0x000C),
            # Earlier firmware versions used "SSCOM".
            model_name=("SoftStep"),
        ),
        PORTS_KEY: [
            inport(props=[NOTES_CC]),
            inport(props=[NOTES_CC, SCRIPT, REMOTE]),
            outport(props=[NOTES_CC]),
            outport(props=[NOTES_CC, SCRIPT, REMOTE]),
        ],
    }


def create_instance(c_instance):
    return modeStep(c_instance=c_instance)


# Initializers for custom components with spec-dependent setup in the default component map.
@depends(specification=None)
def create_device_component(
    *a,
    specification: typing.Optional[typing.Type[Specification]] = None,
    **k,
):
    assert specification
    return DeviceComponent(
        *a,
        bank_definitions=(specification.parameter_bank_definitions),
        bank_size=(specification.parameter_bank_size),
        continuous_parameter_sensitivity=(
            specification.continuous_parameter_sensitivity
        ),
        quantized_parameter_sensitivity=(specification.quantized_parameter_sensitivity),
        **k,
    )


@depends(specification=None)
def create_session_navigation_component(
    *a,
    specification: typing.Optional[typing.Type[Specification]] = None,
    **k,
):
    assert specification
    return SessionNavigationComponent(
        *a, snap_track_offset=(specification.snap_track_offset), **k
    )


# Convert an override from the config to a state object.
def _track_controls_override_to_state(
    override: typing.Optional[typing.Tuple[TrackControl, TrackControl, Action]],
) -> typing.Optional[TrackControlsState]:
    if override:
        return TrackControlsState(
            top_control=override[0], bottom_control=override[1], action=override[2]
        )
    else:
        return None


# Track controls factory, accounting for overrides in configuration.
@depends(configuration=None)
def create_track_controls_component(
    index: int, *a, configuration: typing.Optional[Configuration] = None, **k
):
    assert configuration
    key_number = index + 1
    # Config keys can be ints or strings, normalize to ints.
    normalized_overrides = {
        int(k): v for k, v in configuration.override_track_controls.items()
    }
    state = (
        _track_controls_override_to_state(normalized_overrides[key_number])
        if key_number in normalized_overrides
        else TrackControlsState(
            top_control=TRACK_CONTROLS[index],
            bottom_control=TRACK_CONTROLS[index],
            action="session_record",
        )
    )
    return TrackControlsComponent(*a, state=state, **k)


_track_controls_component_map = {
    f"Track_Controls_{i + 1}": partial(
        partial(create_track_controls_component, i),
        descriptor=str(i + 1),
        name=f"Track_Controls_{i+ 1}",
        edit_track_control_mappings=TRACK_CONTROLS_EDIT_TRACK_CONTROL_MAPPINGS,
        edit_action_mappings=TRACK_CONTROLS_EDIT_ACTION_MAPPINGS,
        edit_action_alt_mappings=TRACK_CONTROLS_EDIT_ACTION_ALT_MAPPINGS,
    )
    for i in range(len(TRACK_CONTROLS))
}


class Specification(ControlSurfaceSpecification):
    elements_type = Elements
    control_surface_skin = create_skin(Skin)
    display_specification = display_specification

    # Scenes is config-dependent and gets set below.
    num_tracks = NUM_GRID_COLS * NUM_ROWS

    include_master = False
    include_returns = False

    # Gets conditionally enabled later.
    include_auto_arming = True

    identity_response_id_bytes = (
        *MANUFACTURER_ID_BYTES,
        *DEVICE_FAMILY_BYTES,
    )

    # Force the controller into standalone mode when exiting (this will be redundant if
    # a standalone mode is already active.) The disconnect program change message will
    # be appended below, if configured.
    goodbye_messages: typing.Collection[typing.Tuple[int, ...]] = (
        SYSEX_STANDALONE_MODE_ON_REQUESTS
    )
    send_goodbye_messages_last = True

    component_map = {
        "Clip_Actions": ClipActionsComponent,
        "Device": create_device_component,
        "Hardware": HardwareComponent,
        "Mixer": MixerComponent,
        # The recording component has some special init in the default component map,
        # but we're overriding it.
        "Recording": RecordingComponent,
        "Session": partial(
            SessionComponent,
            clip_slot_component_type=ClipSlotComponent,
            scene_component_type=SceneComponent,
        ),
        "Session_Navigation": create_session_navigation_component,
        "Transport": TransportComponent,
        "Undo_Redo": UndoRedoComponent,
        "View_Control": ViewControlComponent,
        **_track_controls_component_map,
    }
    session_ring_component_type = SessionRingComponent

    create_mappings_function = create_mappings


class modeStep(ControlSurface):
    def __init__(self, specification=Specification, *a, c_instance=None, **k):
        # A new control surface gets constructed when the song is changed, so we can
        # load song-dependent configuration.
        assert c_instance
        self._configuration = get_configuration(c_instance.song())

        # Set spec fields that depend on the configuration.
        specification.num_scenes = (
            1 if self._configuration.wide_clip_launch else NUM_ROWS
        )
        specification.link_session_ring_to_scene_selection = (
            self._configuration.link_session_ring_to_scene_selection
        )
        specification.link_session_ring_to_track_selection = (
            self._configuration.link_session_ring_to_track_selection
        )
        if self._configuration.disconnect_program is not None:
            specification.goodbye_messages = [
                *specification.goodbye_messages,
                (0xC0, self._configuration.disconnect_program),
            ]

        super().__init__(*a, specification=specification, c_instance=c_instance, **k)

        # Internal tracker during connect/reconnect events.
        self._mode_after_identified = self._configuration.initial_mode

    # Dependencies to be injected throughout the application.
    #
    # We need the `Any` return type because otherwise the type checker
    # infers `None` as the only valid return type.
    def _get_additional_dependencies(self) -> typing.Any:
        deps: typing.Dict[str, typing.Any] = (
            super()._get_additional_dependencies() or {}
        )
        assert self.elements

        deps["component_map"] = const(self.component_map)
        deps["configuration"] = const(self._configuration)
        deps["hardware"] = const(self.component_map["Hardware"])
        deps["specification"] = const(self.specification)

        return deps

    def _create_elements(self, specification: ControlSurfaceSpecification):  # type: ignore
        # Element creation happens before the main dependency injector
        # is built, so we need to explicitly inject any necessary
        # dependencies for this stage.
        with inject(
            configuration=const(self._configuration),
        ).everywhere():
            return super(modeStep, modeStep)._create_elements(specification)

    def setup(self):
        # Activate the background program before doing anything. No-op if no background
        # program has been set.
        self.component_map[
            "Hardware"
        ].standalone_program = self._configuration.background_program
        self._flush_midi_messages()

        # Put the controller explicitly into hosted mode. Setting this directly (rather
        # than in a layer) avoids the need to modify this attribute in every
        # non-standalone control surface mode, which would send unnecessary sysex
        # messages on every mode change.
        self.component_map["Hardware"].standalone = False

        super().setup()

        logger.info(f"{self.__class__.__name__} setup complete")

    @property
    def main_modes(self):
        return self.component_map["Main_Modes"]

    def _create_identification(self, specification):
        identification = super()._create_identification(specification)
        assert self.__on_is_identified_changed_local
        self.__on_is_identified_changed_local.subject = identification
        return identification

    def on_identified(self, response_bytes):
        super().on_identified(response_bytes)
        logger.info("identified SoftStep 2 device")

        # Cancel any pending timeout checks.
        if not self._identity_response_timeout_task.is_killed:
            self._identity_response_timeout_task.kill()

        # We'll reach this point on startup, as well as when MIDI ports change (due to
        # hardware disconnects/reconnects or changes in the Live settings). Don't do
        # anything unless we're currently in disabled mode, i.e. unless we're
        # transitioning from a disconnected controller - there's no need to switch in
        # and out of standalone mode otherwise.
        if (
            self.main_modes.selected_mode is None
            or self.main_modes.selected_mode == DISABLED_MODE_NAME
        ):
            # Force the controller into standalone mode (so we're starting
            # from a consistent state), send the standalone background
            # program if any, and clear the LEDs and display.
            self.main_modes.selected_mode = STANDALONE_INIT_MODE_NAME

            # After a short delay, load the main desired mode. This
            # ensures that all MIDI messages for initialization in
            # standalone mode get sent before the main mode begins to
            # load, which avoids weird issues with MIDI batching etc.
            if not self._on_identified_task.is_killed:
                self._on_identified_task.kill()
            self._on_identified_task.restart()

    # Invoked after a delay if an identity request is sent but no
    # response is received.
    def _on_identity_response_timeout(self):
        # Store the mode that we should enable when/if the controller
        # is (re-)connected. The checks ensure that the first time
        # this is called (or if it's somehow called multiple times
        # before callbacks have finished running), this case won't be
        # reached and the mode variable will keep its current value.
        if (
            self.main_modes.selected_mode
            and self.main_modes.selected_mode != DISABLED_MODE_NAME
            and self.main_modes.selected_mode != STANDALONE_INIT_MODE_NAME
        ):
            self._mode_after_identified = self.main_modes.selected_mode

        # Enter disabled mode, which relinquishes control of everything. This ensures
        # that sysex state values will be invalidated (by disconnecting their control
        # elements), and nothing will be bound when the controller is next identified,
        # so we won't send a bunch of LED messages before placing it into hosted
        # mode. (This could still happen if the controller were connected and
        # disconnected quickly, but in any case it would just potentially mess with
        # standalone-mode LEDs.)
        self.main_modes.selected_mode = DISABLED_MODE_NAME

    @listens("is_identified")
    def __on_is_identified_changed_local(self, is_identified: bool):
        # This will trigger on startup, and whenever a new identity
        # request is sent to an already-identified controller
        # (e.g. when devices are connected/disconnected). If we don't
        # get a timely response, we can assume the controller was
        # physically disconnected.
        if not is_identified:
            self._identity_response_timeout_task.restart()

    @lazy_attribute
    def _identity_response_timeout_task(self):
        assert self.specification
        # The `identity_request_delay` is the delay before a second identity request is
        # sent. Let this elapse twice before considering the SoftStep disconnected.
        timeout = self.specification.identity_request_delay * 2
        identity_response_timeout_task = self._tasks.add(
            task.sequence(
                task.wait(timeout),
                task.run(self._on_identity_response_timeout),
            )
        )
        identity_response_timeout_task.kill()
        return identity_response_timeout_task

    @lazy_attribute
    def _on_identified_task(self):
        # Just delay by one frame. At startup, this delay will be
        # a bit longer.
        on_identified_task = self._tasks.add(task.run(self._after_identified))
        on_identified_task.kill()
        return on_identified_task

    def _after_identified(self):
        mode = (
            self._mode_after_identified
            if self._mode_after_identified is not None
            else self._configuration.initial_mode
        )
        self.main_modes.selected_mode = mode
