from logging import getLogger
from typing import Optional

from ableton.v3.base import depends
from ableton.v3.control_surface.components import (
    ClipSlotComponent as ClipSlotComponentBase,
)

from .configuration import Configuration
from .live import listens
from .types import ClipSlotAction

logger = getLogger(__name__)


class ClipSlotComponent(ClipSlotComponentBase):
    @depends(configuration=None)
    def __init__(self, *a, configuration: Optional[Configuration] = None, **k):
        super().__init__(*a, **k)

        assert configuration

        self._launch_pressed_delayed_action: Optional[ClipSlotAction] = (
            configuration.clip_long_press_action
        )

        assert self.__on_launch_button_pressed_delayed
        self.__on_launch_button_pressed_delayed.subject = self.launch_button

        self._is_launch_held = False

    # Wait for a delayed press if appropriate.
    def _on_launch_button_pressed(self):
        self._is_launch_held = False
        if self._launch_pressed_delayed_action is None:
            super()._on_launch_button_pressed()

    def _on_launch_button_pressed_delayed(self):
        if self.is_enabled():
            self._is_launch_held = True
            if self._launch_pressed_delayed_action is not None:
                self._do_action(self._launch_pressed_delayed_action)

    def _on_launch_button_released(self):
        if self._launch_pressed_delayed_action is None:
            super()._on_launch_button_released()
        elif not self._is_launch_held:
            # If we were waiting for a delayed action but didn't receive it.
            super()._on_launch_button_pressed()
            super()._on_launch_button_released()

    @listens("is_held")
    def __on_launch_button_pressed_delayed(self, is_held):
        if is_held:
            self._on_launch_button_pressed_delayed()

    def _do_action(self, action: ClipSlotAction):
        if action == "stop_track_clips":
            if self._clip_slot:
                track = self._clip_slot.canonical_parent
                if track:
                    track.stop_all_clips()
        else:
            raise ValueError(f"unknown action: {action}")
