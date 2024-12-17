import logging
from typing import Any

from ableton.v3.control_surface.component import Component
from ableton.v3.control_surface.controls import ButtonControl

logger = logging.getLogger(__name__)


# Component to respond to pings from the test runner.
class PingComponent(Component):
    ping_button: Any = ButtonControl()

    @ping_button.pressed
    def ping_input(self, _):
        if self.is_enabled():
            logger.info("ponging ping")
            self.ping_button.control_element.send_value(True)
