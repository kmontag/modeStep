import logging

from ableton.v3.control_surface.components.mixer import (
    MixerComponent as MixerComponentBase,
)

from .channel_strip import ChannelStripComponent

logger = logging.getLogger(__name__)


class MixerComponent(MixerComponentBase):
    def __init__(self, *a, channel_strip_component_type=ChannelStripComponent, **k):
        super().__init__(
            *a, channel_strip_component_type=channel_strip_component_type, **k
        )

    def set_selected_track_arm_button(self, button):
        self._target_strip.arm_button.set_control_element(button)
        self._target_strip.update()
