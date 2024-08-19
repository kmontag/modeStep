from __future__ import annotations

import logging
import typing
from contextlib import contextmanager
from enum import Enum
from functools import partial
from time import time

from ableton.v2.control_surface.mode import SetAttributeMode
from ableton.v3.base import depends, listenable_property, task
from ableton.v3.control_surface.controls import ButtonControl
from ableton.v3.control_surface.mode import (
    CallFunctionMode,
    Mode,
    ModeButtonBehaviour,
)
from ableton.v3.control_surface.mode import ModesComponent as ModesComponentBase

from .hardware import HardwareComponent
from .live import lazy_attribute, memoize
from .types import MainMode

if typing.TYPE_CHECKING:
    from .configuration import Configuration

logger = logging.getLogger(__name__)

# Mode activated while the controller is disconnected. Disables the hardware component
# and anything that could otherwise send MIDI messages.
DISABLED_MODE_NAME = "_disabled"

# Mode activated before transitioning out of disabled mode. Puts the controller into
# standalone mode and activates the background program.
STANDALONE_INIT_MODE_NAME = "_standalone_init"

# Mode activated before transitioning from a user standalone mode to hosted mode. Pauses
# briefly before performing the switch, to make sure that all MIDI messages (in
# particular the standalone background PC) get sent before the hosted mode sysexes.
#
# This works around what appears to be low-level MIDI batching (which occurs regardless
# of things like `_flush_midi_messages`) which puts sysexes ahead of all other messages
# when they're sent on the same timer tick.
#
# Note that this mode is bound to the standalone exit button, which is in practice the
# only way to get from a user standalone mode (i.e. other than `_standalone_init`) back
# to a hosted mode. If we ever need to support e.g. other programmatic transitions to
# hosted modes, we'll need to find a more general solution to delay mode-switching in
# these cases.
STANDALONE_TRANSITION_MODE_NAME = "_standalone_transition"

MODE_SELECT_MODE_NAME: MainMode = "mode_select"


# Mode categorization definition and helpers. Values are the mode name prefixes used to
# determine each mode.
class MainModeCategory(Enum):
    device = "device_"
    edit_track_controls = "edit_track_controls_"
    track_controls = "track_controls_"
    standalone = "standalone_"
    mode_select = "mode_select"
    # Non-user-facing modes have this prefix.
    hidden = "_"
    # Anything else is uncategorized.
    uncategorized = None


@memoize
def get_main_mode_category(name: typing.Optional[str]) -> MainModeCategory:
    if name is None:
        return MainModeCategory.hidden
    for category in MainModeCategory:
        prefix = category.value
        if prefix is not None and name.startswith(prefix):
            return category
    return MainModeCategory.uncategorized


# Get the main track controls mode for an edit mode.
@memoize
def get_track_controls_mode(
    name: typing.Optional[str],
) -> typing.Optional[str]:
    category = get_main_mode_category(name)
    if category is MainModeCategory.track_controls:
        return name
    elif category is MainModeCategory.edit_track_controls:
        assert name
        return name[len("edit_") :]
    else:
        return None


# Get e.g. "3" from names like "track_controls_3".
@memoize
def get_index_str(name: str):
    return name.split("_")[-1]


class InvertedMode(Mode):
    def __init__(self, mode: Mode):
        self._mode = mode

    def enter_mode(self):
        self._mode.leave_mode()

    def leave_mode(self):
        self._mode.enter_mode()


class PersistentSetAttributeMode(SetAttributeMode):
    """Set an attribute when entering the mode, but not when leaving it."""

    def leave_mode(self):
        pass


# The mode select button:
# - brings up the mode select screen on short press in non-transient modes
# - jumps to the most recent mode on long press
# - serves as a back button while already in transient modes
class ModeSelectBehaviour(ModeButtonBehaviour):
    def __init__(self):
        super().__init__()
        self._needs_handling_on_release: bool = False

    def release_immediate(self, component, mode):
        if component.selected_mode and component.is_transient_mode(
            component.selected_mode
        ):
            # component.pop_mode(component.selected_mode)
            component.push_mode(
                component.current_non_transient_mode or MODE_SELECT_MODE_NAME
            )
        else:
            component.push_mode(mode)

    def press_delayed(self, component, mode):
        # Special handling for the standalone mode. We don't want to
        # switch there while a button is still being held.
        if component.last_non_transient_mode and component.is_standalone_mode(
            component.last_non_transient_mode
        ):
            self._needs_handling_on_release = True
            component.update_mode_button(mode)
        else:
            component.select_last_non_transient_mode()

    def release_delayed(self, component, mode):  # noqa: ARG002
        # If we skipped the `pressed_delayed` event, perform the
        # switch after release instead.
        if self._needs_handling_on_release:
            component.select_last_non_transient_mode()

        self._needs_handling_on_release = False

    def update_button(
        self, component: ModesComponentBase, mode: str, selected_mode: str
    ):
        button = getattr(component, f"{mode}_button", None)
        mode_color_base_name = component._get_mode_color_base_name(mode)
        if button:
            if self._needs_handling_on_release:
                color = f"{mode_color_base_name}.PressDelayed"
            else:
                color = (
                    f"{mode_color_base_name}.PopMode"
                    if component.is_transient_mode(selected_mode)
                    else f"{mode_color_base_name}.Off"
                )
            button.mode_selected_color = color
            button.mode_unselected_color = color


class AlternateOnLongPressBehaviour(ModeButtonBehaviour):
    def __init__(self, alternate_mode: typing.Optional[str] = None):
        self._alternate_mode = alternate_mode

    def press_immediate(self, component: ModesComponentBase, mode):
        if not self._alternate_mode:
            component.push_mode(mode)
            component.pop_unselected_modes()

    def release_immediate(self, component: ModesComponentBase, mode):
        if self._alternate_mode:
            component.push_mode(mode)
            component.pop_unselected_modes()

    def press_delayed(self, component: ModesComponentBase, mode):  # noqa: ARG002
        if self._alternate_mode:
            component.push_mode(self._alternate_mode)
            component.pop_unselected_modes()


# A button which doesn't trigger anything until it's released. This is
# useful if we need to make sure the player's foot is off the button
# before e.g. switching into standalone mode.
class ReleaseBehaviour(ModeButtonBehaviour):
    def __init__(self, alternate_mode: typing.Union[str, None] = None):
        super().__init__()
        self._alternate_mode = alternate_mode
        self._is_delayed = False

    def release_immediate(self, component, mode):
        self._handle_release(component, mode)

    def press_delayed(self, component, mode):
        self._is_delayed = True
        component.update_mode_button(mode)

    def release_delayed(self, component, mode):
        self._handle_release(
            component, self._alternate_mode if self._alternate_mode else mode
        )
        self._is_delayed = False

    def _handle_release(self, component, mode):
        component.push_mode(mode)
        component.pop_unselected_modes()

    def update_button(self, component: MainModesComponent, mode, selected_mode):  # noqa: ARG002
        button = getattr(component, f"{mode}_button", None)
        mode_color_base_name = component._get_mode_color_base_name(mode)
        if button:
            if self._is_delayed and self._alternate_mode:
                button.mode_unselected_color = f"{mode_color_base_name}.PressDelayed"
            else:
                button.mode_unselected_color = f"{mode_color_base_name}.Off"


class MainModesComponent(ModesComponentBase):
    # We need slightly different behaviour for mode select from the
    # standalone mode, since we don't want to trigger anything while
    # the button is still pressed.
    standalone_exit_button = ButtonControl(color=None)

    # Timestamp when the current mode was selected. Needed to scroll mode names if
    # necessary.
    entered_at = listenable_property.managed(0.0)

    _tasks: task.TaskGroup  # type: ignore

    @depends(configuration=None, hardware=None)
    def __init__(
        self,
        *a,
        configuration: typing.Optional["Configuration"] = None,
        hardware: typing.Optional[HardwareComponent] = None,
        **k,
    ):
        super().__init__(*a, **k)

        assert configuration
        assert hardware
        self._hardware = hardware

        # The current mode, or if we're in a transient mode, the most recent
        # non-transient mode. Set this immediately so that when a mode is actually
        # loaded, this will get placed in the history.
        self._current_non_transient_mode = configuration.initial_last_mode

        # The non-transient mode (different from the current one) that
        # was last seen before the current one.
        self._last_non_transient_mode = None

        # During setup of mode components, Live activates their first added mode (see
        # `ControlSurfaceMappingMixin::_setup_modes_component`). Add a blank mode
        # immediately to make this activation a no-op. We'll select the "real" first
        # mode (disabled mode) after the component setup is complete.
        self.add_mode("_pre_init", CallFunctionMode())

        # Internal mode for transitioning from standalone to hosted mode, which requires
        # a pause (to get correct MIDI message ordering) before activating the next real
        # mode.
        self.add_mode(
            STANDALONE_TRANSITION_MODE_NAME,
            CallFunctionMode(on_enter_fn=self._prepare_standalone_transition),
        )

        # Tracker for the post-delay behavior of the standalone transition mode,
        # i.e. mode select or previous mode. The initial value doesn't matter; this will
        # get set when the standalone exit button is pressed.
        self.__standalone_transition_is_mode_select: bool = False

    # Transient modes don't get added to the mode history, and switch
    # the mode select button to a "cancel" button.
    @memoize
    def is_transient_mode(self, name: typing.Optional[str]):
        if name is None:
            return True
        else:
            return get_main_mode_category(name) in [
                MainModeCategory.hidden,
                MainModeCategory.mode_select,
                MainModeCategory.edit_track_controls,
            ]

    # Standalone modes (where the controller has been taken out of
    # hosted mode) need special handling in the mode select button.
    @memoize
    def is_standalone_mode(self, name: str):
        if name is STANDALONE_INIT_MODE_NAME:
            return True
        else:
            return get_main_mode_category(name) is MainModeCategory.standalone

    @property
    def last_non_transient_mode(self):
        return self._last_non_transient_mode

    @property
    def current_non_transient_mode(self):
        return self._current_non_transient_mode

    # Used to exit a popup, e.g. the track control editing screen.
    def select_current_non_transient_mode(self):
        self.__select_mode_or_mode_select(self._current_non_transient_mode)

    # Note the history only gets updated when a non-transient mode becomes active. So
    # from the mode select screen, for exmample, this is actually two non-transient
    # modes ago.
    def select_last_non_transient_mode(self):
        self.__select_mode_or_mode_select(self.last_non_transient_mode)

    def __select_mode_or_mode_select(self, name: typing.Optional[str]):
        if name and name != self.selected_mode:
            self.selected_mode = name
        else:
            self.push_mode(MODE_SELECT_MODE_NAME)

    def update_mode_button(self, mode):
        if self.is_enabled():
            self._get_mode_behaviour(mode).update_button(self, mode, self.selected_mode)

    def _update_mode_controls(self, selected_mode):
        super()._update_mode_controls(selected_mode)

        # Sometime in the Live 12 lifecycle, this stopped getting called automatically
        # during mode changes. Some mode buttons (track controls, mode select) have a
        # color which is dependent on state that might change during a mode change, and
        # need to be explicitly refreshed.
        for mode in self._mode_list:
            self.update_mode_button(mode)

    def _prepare_standalone_transition(self):
        # Delay the actual transition out of standalone mode to allow the background
        # program change message to be sent.
        #
        # Note we assume that no other modes will be activated in the meantime;
        # otherwise we'd end up stomping on the activated mode after the delay.
        self._finish_standalone_transition_task.restart()

    @lazy_attribute
    def _finish_standalone_transition_task(self):
        finish_standalone_transition_task = self._tasks.add(
            task.sequence(task.delay(0), task.run(self._finish_standalone_transition))
        )
        finish_standalone_transition_task.kill()
        return finish_standalone_transition_task

    def _finish_standalone_transition(self):
        # After the delay, the background program change message should have been sent,
        # so we can now send the actual sysexes to switch to hosted mode.
        self._hardware.standalone = False
        if self.__standalone_transition_is_mode_select:
            self.push_mode(MODE_SELECT_MODE_NAME)
        else:
            self.select_last_non_transient_mode()

    @standalone_exit_button.released_immediately
    def standalone_exit_button(self, _):  # type: ignore
        self.__standalone_transition_is_mode_select = True
        self.push_mode(STANDALONE_TRANSITION_MODE_NAME)

    @standalone_exit_button.released_delayed
    def standalone_exit_button(self, _):
        # Hack to get nicer switching directly between standalone modes. If we're
        # exiting to another standalone mode, we can skip unloading/reloading from
        # hosted mode by just sending a program change directly.
        if all(
            [
                (None if name is None else get_main_mode_category(name))
                is MainModeCategory.standalone
                for name in (
                    self.last_non_transient_mode,
                    self._current_non_transient_mode,
                )
            ]
        ):
            assert self.last_non_transient_mode
            self._hardware.standalone_program = (
                int(get_index_str(self.last_non_transient_mode)) - 1
            )
            # Fake the update in our internal state as well.
            tmp = self.last_non_transient_mode
            self._last_non_transient_mode = self._current_non_transient_mode
            self._current_non_transient_mode = tmp
        else:
            self.__standalone_transition_is_mode_select = False
            self.push_mode(STANDALONE_TRANSITION_MODE_NAME)

    def _do_enter_mode(self, name):
        logger.info(f"enter mode: {name}")
        self.entered_at = time()
        if not self.is_transient_mode(name):
            if name is not self._current_non_transient_mode:
                self._last_non_transient_mode = self._current_non_transient_mode
                self._current_non_transient_mode = name

        super()._do_enter_mode(name)

    def _get_mode_color_base_name(self, mode_name):
        # Just use the mode category for the color, rather than the full mode name.
        category = get_main_mode_category(mode_name)
        return "{}.{}".format(
            self.name.title().replace("_", ""), category.name.title().replace("_", "")
        )


# Modes component which creates on/off modes for a target. Map the cycle button to get a
# toggle switch.
class ToggleModesComponent(ModesComponentBase):
    _on_mode = "on"
    _off_mode = "off"
    _unset_mode = "unset"

    def __init__(
        self,
        # Turn the target on or off. This will be called when the component switches
        # modes, as well as (if an initial state is given) once immediately during
        # the initial mode select.
        set_state: typing.Callable[[bool], typing.Any],
        *a,
        # Initial state to set.
        #
        # If `None`, the setter won't be called during
        # initializtion, but the cycling position will be set such that the ON state is
        # next. For example, to leave the backlight unmanaged at first but allow
        # toggling it in real time.
        initial_state: typing.Optional[bool] = None,
        # Don't want long-press behavior for the cycle button.
        support_momentary_mode_cycling=False,
        **k,
    ):
        # Force the value of the momentary cycling setting, since it gets passed down as
        # True during creation.
        super().__init__(
            *a, support_momentary_mode_cycling=support_momentary_mode_cycling, **k
        )

        self._state: typing.Optional[bool] = initial_state

        def set_and_record_state(state: bool):
            set_state(state)
            self._state = state

        # ON mode should come first so that it's next in the cycle if no initial state
        # was passed.
        for name, state in ((self._on_mode, True), (self._off_mode, False)):
            self.add_mode(
                name,
                CallFunctionMode(partial(set_and_record_state, state)),
            )

        # No-op mode that will get skipped in the cycle, to represent an initial state
        # of `None`. Note we need to set our `selected_mode` explicitly in the
        # constructor (it can't just be `None`), since otherwise the framework's setup
        # logic will just select one for us.
        self.add_mode(self._unset_mode, Mode())

        self._suppressing_notifications = False
        with self.suppressing_notifications():
            if initial_state is None:
                self.selected_mode = self._unset_mode
            else:
                self.selected_mode = self._on_mode if initial_state else self._off_mode

    def cycle_mode(self, delta=1):
        super().cycle_mode(delta)

        # Skip the null mode in the cycle.
        if self.selected_mode == self._unset_mode:
            super().cycle_mode(1)

    # Maybe there's a more built-in way to do this?
    @contextmanager
    def suppressing_notifications(self, suppressing_notifications=True):
        old_suppressing_notifications = self._suppressing_notifications
        self._suppressing_notifications = suppressing_notifications
        try:
            yield
        finally:
            self._suppressing_notifications = old_suppressing_notifications

    def notify(self, notification, *a):
        if not self._suppressing_notifications:
            super().notify(notification, *a)
