import Live
from typing import TYPE_CHECKING, Optional

from ableton.v3.base import depends
from ableton.v3.control_surface.components import (
    ClipActionsComponent as ClipActionsComponentBase,
)

if TYPE_CHECKING:
    from .configuration import Configuration
from logging import getLogger

logger = getLogger(__name__)


class ClipActionsComponent(ClipActionsComponentBase):
    @depends(configuration=None)
    def __init__(self, *a, configuration: Optional["Configuration"] = None, **k):
        super().__init__(*a, **k)

        assert configuration
        try:
            self._quantization_value = getattr(
                Live.Song.RecordingQuantization, f"rec_q_{configuration.quantize_to}"
            )
        except Exception:
            logger.warning(f"could not set quantization to {configuration.quantize_to}")

        self._quantize_amount = configuration.quantize_amount

    def _quantize_clip(self, clip):
        old_quantize = clip.quantize

        # The parent doesn't support a variable quantization amount, so we temporarily
        # monkey-patch the clip's qantize method.
        def quantize_with_amount(quantization, _ignored_amount):
            old_quantize(quantization, self._quantize_amount)

        clip.quantize = quantize_with_amount
        try:
            super()._quantize_clip(clip)
        finally:
            clip.quantize = old_quantize
