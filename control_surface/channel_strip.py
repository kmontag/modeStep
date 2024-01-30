import logging
from enum import Enum

from ableton.v3.base import listens
from ableton.v3.control_surface.components.channel_strip import (
    ChannelStripComponent as ChannelStripComponentBase,
)
from ableton.v3.control_surface.controls import MappedControl
from ableton.v3.live import liveobj_valid

logger = logging.getLogger(__name__)


class ArmStatus(Enum):
    on = "on"
    off = "off"
    implicit = "implicit"


class ChannelStripComponent(ChannelStripComponentBase):
    empty_color = "DefaultButton.Off"

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.volume_control: MappedControl.State
        # We don't seem to have access to the control element at any point during the
        # connection callbacks in this class, and it then becomes Null by the time we
        # reach an update. We need to monkey-patch the control to get reasonable volume
        # light updates.
        orig_update_direct_connection = self.volume_control._update_direct_connection

        def update_direct_connection():
            self._update_volume_light()
            orig_update_direct_connection()

        self.volume_control._update_direct_connection = update_direct_connection

        # Use an "is_pressed" handler so we can preserve the parent "pressed" behavior.
        assert self.__on_arm_button_is_pressed
        self.__on_arm_button_is_pressed.subject = self.arm_button
        self.__arm_needs_notification = False

    # Probably shouldn't be called during the normal update method, since the control element
    # will be None at that point.
    def _update_volume_light(self):
        color = "Mixer.TrackVolume" if liveobj_valid(self._track) else self.empty_color
        if self.volume_control._control_element and hasattr(
            self.volume_control._control_element, "set_light"
        ):
            self.volume_control._control_element.set_light(color)

    @listens("is_pressed")
    def __on_arm_button_is_pressed(self):
        if self.arm_button.is_pressed:
            # This listener gets called before the button is updated. Wait for the
            # button update so we can piggyback off the logic there.
            self.__arm_needs_notification = True

    def _update_arm_button(self):
        super()._update_arm_button()
        if self.track and self.__arm_needs_notification:
            # Use the computed button state to determine the arm status.
            status: ArmStatus
            if self.arm_button.is_on:
                status = (
                    ArmStatus.on
                    if self.arm_button.on_color == "Mixer.ArmOn"
                    else ArmStatus.implicit
                )
            else:
                status = ArmStatus.off
            self.notify(self.notifications.Track.arm, self.track.name, status)
        self.__arm_needs_notification = False
