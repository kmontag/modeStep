from logging import getLogger

from ableton.v3.control_surface.components import (
    TransportComponent as TransportComponentBase,
)
from ableton.v3.control_surface.controls import ToggleButtonControl

logger = getLogger(__name__)


class TransportComponent(TransportComponentBase):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.automation_arm_button: ToggleButtonControl.State

    @TransportComponentBase.automation_arm_button.toggled
    def automation_arm_button(self, is_on, _):  # type: ignore
        self.notify(self.notifications.Transport.automation_arm, is_on)
