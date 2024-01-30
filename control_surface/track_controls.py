from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from functools import partial
from logging import getLogger
from typing import Any, Callable, Dict, Optional, TypeVar

from ableton.v2.control_surface.mode import SetAttributeMode, to_camel_case_name
from ableton.v3.base import listenable_property, task
from ableton.v3.control_surface import Component
from ableton.v3.control_surface.controls import ButtonControl
from ableton.v3.control_surface.display import Renderable
from ableton.v3.control_surface.layer import Layer
from ableton.v3.control_surface.mode import (
    AddLayerMode,
    CallFunctionMode,
    CompoundMode,
    Mode,
    ModesComponent,
)

from .live import lazy_attribute
from .mode import AlternateOnLongPressBehaviour
from .types import Action, TrackControl

logger = getLogger(__name__)

DELETE_DELAY = 1.0


@dataclass
class TrackControlsState:
    action: Action
    top_control: TrackControl
    bottom_control: TrackControl


@dataclass
class PendingTrackControlsState:
    # Always require an action to be present to avoid complicating
    # the mode navigation logic.
    action: Action
    top_control: Optional[TrackControl] = None
    bottom_control: Optional[TrackControl] = None


class TrackControlsComponentStrategy:
    def cancel_edit(self):
        raise NotImplementedError

    def finish_edit(self):
        raise NotImplementedError

    def create_mode(self, state: Optional[TrackControlsState]) -> Mode:
        raise NotImplementedError


# Possible overall UI states for the edit dialgs.
class TrackControlsEditWindow(Enum):
    top_control = "edit_top_control"
    bottom_control = "edit_bottom_control"
    action = "edit_action"
    action_alt = "edit_action_alt"


class TrackControlsButtonBehaviour(AlternateOnLongPressBehaviour):
    def __init__(self, track_controls: TrackControlsComponent, *a, **k):
        super().__init__(*a, **k)
        self._track_controls = track_controls

    def release_immediate(self, component, mode):
        # Don't do anything if the mode is disabled.
        if self._track_controls.state is not None:
            return super().release_immediate(component, mode)

    def update_button(self, component, mode, selected_mode):  # noqa: ARG002
        color = (
            "TrackControls.Disabled"
            if self._track_controls.state is None
            else "TrackControls.Enabled"
        )

        getattr(component, f"{mode}_button").mode_unselected_color = color


# Dynamic multitrack controls with a configuration UI.
class TrackControlsComponent(Component, Renderable):
    # Back/cancel button while editing.
    cancel_button: Any = ButtonControl()

    # Bind this in the edit mode to configure the a quick action.
    edit_action_button: Any = ButtonControl(color="TrackControls.EditAction")

    edit_window: Optional[TrackControlsEditWindow] = listenable_property.managed(None)  # type: ignore
    edit_window_updated_at: float = listenable_property.managed(0.0)  # type: ignore
    descriptor: str = listenable_property.managed("")  # type: ignore
    state: Optional[TrackControlsState] = listenable_property.managed(None)  # type: ignore

    _tasks: task.TaskGroup  # type: ignore

    def __init__(
        self,
        # One-character descriptor to use in mode display names.
        descriptor: str,
        # Maps of track controls to element names. Used to
        # create the edit view layers.
        edit_track_control_mappings: Dict[TrackControl, str],
        # Maps of actions from the transport and utility modes.
        edit_action_mappings: Dict[Action, str],
        edit_action_alt_mappings: Dict[Action, str],
        # Strategy for generating modes and taking actions.
        strategy: Optional[TrackControlsComponentStrategy] = None,
        # Initial state.
        state: Optional[TrackControlsState] = None,
        # Default action in case no state is provided.
        default_action: Action = "session_record",
        *a,
        **k,
    ):
        super().__init__(*a, **k)

        self.descriptor = descriptor
        self.state = state
        self._default_action: Action = default_action

        self._modes = ModesComponent(
            name=f"Track_Controls_{self.descriptor}_Modes",
            is_private=True,
            parent=self,
        )
        self.add_children(self._modes)

        # Add entrypoint modes to perform setup before entering the edit or track
        # controls context.
        self.__edit_mode_name = f"edit_track_controls_{descriptor}"
        self.__track_controls_mode_name = f"track_controls_{descriptor}"
        for mode_name, enter_fn in (
            (self.__edit_mode_name, self._enter_edit_mode),
            (self.__track_controls_mode_name, self._enter_track_controls_mode),
        ):
            self._modes.add_mode(mode_name, CallFunctionMode(on_enter_fn=enter_fn))

        # Dynamically create buttons to select each action and control type during
        # preset configuration.
        #
        # When pressed, the handlers for these buttons will store the appropriate value,
        # and then advance the configuration process using `_next_configuration_step`.
        def make_button_control(on_pressed: Callable[[], Any], **k):
            button_control: Any = ButtonControl(**k)

            @button_control.pressed
            def button_control(_component, _button):
                on_pressed()

            return button_control

        T = TypeVar("T")

        def create_controls_and_layer(
            prefix: str, mappings: Dict[T, str], on_selected: Callable[[T], Any]
        ):
            layer_attrs = {}
            for value, element in mappings.items():
                button_control_name = f"select_{prefix}_{value}_button"
                color = f"TrackControls.{to_camel_case_name(value)}"
                on_pressed = partial(on_selected, value)
                # Skip stuff like "session_record" that gets added twice.
                if not hasattr(self, button_control_name):
                    self.add_control(
                        button_control_name,
                        make_button_control(on_pressed, color=color),
                    )
                layer_attrs[button_control_name] = element
            return Layer(**layer_attrs)

        select_action_layer = create_controls_and_layer(
            "action", edit_action_mappings, self._on_action_selected
        )
        select_action_alt_layer = create_controls_and_layer(
            "action", edit_action_alt_mappings, self._on_action_selected
        )
        select_track_control_layer = create_controls_and_layer(
            "track_control",
            edit_track_control_mappings,
            self._on_track_control_selected,
        )

        # Add modes for the edit screens.
        self.__edit_control_mode_name = f"select_{descriptor}"
        self.__edit_action_mode_name = f"select_action_{self.name}"
        self.__edit_action_alt_mode_name = f"select_action_alt_{self.name}"
        for mode_name, layer in (
            (
                self.__edit_control_mode_name,
                select_track_control_layer,
            ),
            (self.__edit_action_mode_name, select_action_layer),
            (self.__edit_action_alt_mode_name, select_action_alt_layer),
        ):
            self._modes.add_mode(
                mode_name,
                # Add the provided layer for select-button mappings.
                AddLayerMode(component=self, layer=layer),
            )

        self._strategy: TrackControlsComponentStrategy = (
            strategy if strategy else TrackControlsComponentStrategy()
        )

        self._is_deleting: bool = False
        self._pending_state: PendingTrackControlsState = self._new_pending_state()
        self.__track_controls_external_mode = None
        self.__track_controls_external_mode_count = 0

    @property
    def strategy(self):
        return self._strategy

    @strategy.setter
    def strategy(self, strategy: TrackControlsComponentStrategy):
        self._strategy = strategy
        self.__track_controls_external_mode = None

    @cancel_button.released_immediately
    def cancel_button(self, _):  # type: ignore
        self._pop_edit_step()

    @cancel_button.pressed_delayed
    def cancel_button(self, _):  # type: ignore
        self._is_deleting = True
        self._delete_task.restart()
        self._update_cancel_button()

    @cancel_button.released
    def cancel_button(self, _):
        if not self._delete_task.is_killed:
            self._delete_task.kill()
        self._is_deleting = False
        self._update_cancel_button()

    @lazy_attribute
    def _delete_task(self):
        delete_task = self._tasks.add(
            task.sequence(task.wait(DELETE_DELAY), task.run(self._delete))
        )
        delete_task.kill()
        return delete_task

    def _delete(self):
        self.state = None
        self._is_deleting = False
        self.__track_controls_external_mode = None
        self._update_cancel_button()
        self._cancel_edit()
        self.notify(self.notifications.TrackControls.delete, self.descriptor)

    def _update_cancel_button(self):
        color = (
            "TrackControls.WarnDelete" if self._is_deleting else "TrackControls.Cancel"
        )
        self.cancel_button.color = color

    def update(self):
        super().update()
        self._update_cancel_button()

    @edit_action_button.released_immediately
    def edit_action_button(self, _):  # type: ignore
        self._set_edit_window(TrackControlsEditWindow.action)
        self._modes.selected_mode = self.__edit_action_mode_name

    @edit_action_button.pressed_delayed
    def edit_action_button(self, _):
        self._set_edit_window(TrackControlsEditWindow.action_alt)
        self._modes.selected_mode = self.__edit_action_alt_mode_name

    # Modes to enter different UIs for the component.
    @lazy_attribute
    def edit_mode(self):
        return self.__set_selected_mode_mode(self.__edit_mode_name)

    @lazy_attribute
    def track_controls_mode(self):
        return self.__set_selected_mode_mode(self.__track_controls_mode_name)

    def __set_selected_mode_mode(self, mode_name: str):
        return CompoundMode(
            # EnablingMode(self),
            SetAttributeMode(self._modes, "selected_mode", mode_name),
        )

    def _next_edit_track_control_step(self):
        state = self._pending_state
        if state.top_control is not None and state.bottom_control is not None:
            self.state = TrackControlsState(
                top_control=state.top_control,
                bottom_control=state.bottom_control,
                action=state.action,
            )
            self._set_edit_window(None)
            # Reset the external mode so it gets regenerated when needed.
            self.__track_controls_external_mode = None
            self._modes.selected_mode = None
            self.strategy.finish_edit()
        else:
            self._set_edit_window(
                TrackControlsEditWindow.top_control
                if state.top_control is None
                else TrackControlsEditWindow.bottom_control
            )
            if self._modes.selected_mode != self.__edit_control_mode_name:
                self._modes.selected_mode = self.__edit_control_mode_name

    def _pop_edit_step(self):
        selected_mode = self._modes.selected_mode
        if selected_mode in [
            self.__edit_action_mode_name,
            self.__edit_action_alt_mode_name,
        ]:
            # If we're looking at an action mode, just jump back to
            # the appropriate control mode.
            self._next_edit_track_control_step()
        elif self._pending_state.top_control is None:
            # If we're looking at the first edit screen, exit the
            # editor.
            self._cancel_edit()
        else:
            self._pending_state.top_control = None
            self._next_edit_track_control_step()
        self.update()

    def _enter_edit_mode(self):
        self._pending_state = self._new_pending_state()
        self._next_edit_track_control_step()

    def _cancel_edit(self):
        self._modes.selected_mode = None
        self.strategy.cancel_edit()

    def _new_pending_state(self):
        return PendingTrackControlsState(
            action=self.state.action if self.state else self._default_action
        )

    def _enter_track_controls_mode(self):
        # Create the "real" mode if necessary.
        if self.__track_controls_external_mode is None:
            self.__track_controls_external_mode = self._strategy.create_mode(self.state)
            self.__track_controls_external_mode_count += 1
            self._modes.add_mode(
                self.__track_controls_external_mode_name(),
                self.__track_controls_external_mode,
            )

        self._modes.selected_mode = self.__track_controls_external_mode_name()

    def set_enabled(self, enable):
        super().set_enabled(enable)

    def _set_edit_window(self, edit_window: Optional[TrackControlsEditWindow]):
        self.edit_window = edit_window
        self.edit_window_updated_at = time.time()

    def _on_action_selected(self, action: Action):
        self._pending_state.action = action
        notification = action
        try:
            notification = getattr(self.notifications.TrackControls.EditAction, action)
        except AttributeError:
            logger.warning(f"no notification string found for {action}")
        self.notify(notification)
        self._next_edit_track_control_step()

    def _on_track_control_selected(self, track_control: TrackControl):
        state = self._pending_state
        if state.top_control is None:
            state.top_control = track_control
        else:
            state.bottom_control = track_control
        self.notify(
            getattr(self.notifications.TrackControls.EditTrackControl, track_control)
        )
        self._next_edit_track_control_step()

    def __track_controls_external_mode_name(self):
        return f"track_controls_{self.descriptor}_external_v{self.__track_controls_external_mode_count}"
