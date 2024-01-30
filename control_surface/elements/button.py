from .light import LightedTransitionalProcessedValueElement


class LightedButtonElement(LightedTransitionalProcessedValueElement):
    def _on_value(self, value, control):  # noqa: ARG002
        self._commit_value(127 if self.is_pressed() else 0)

    def is_momentary(self):
        return True

    def is_pressed(self):
        return True if any([value > 0 for value in self._owned_values()]) else False
