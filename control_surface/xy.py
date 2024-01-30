import base64
import logging
import zlib

from ableton.v2.base.util import clamp

logger = logging.getLogger(__name__)

DEFAULT_VALUE = 63

# The decoded/decompressed value is a list of precomputed output
# values (in the range 0-127) for XY positional sources, approximating
# the controller's native output. Indexed by `high_pressure + 128 *
# low_pressure` for pressure values ranging from 0 to 127.
try:
    output_values: "tuple[int, ...]" = tuple(
        zlib.decompress(
            base64.b64decode(
                b"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",
            )
        )
    )
except Exception as ex:
    logger.warning("Error loading XY outputs")
    logger.exception(ex)
    output_values = tuple([DEFAULT_VALUE] * 128 * 128)


def get_xy_value(left_value: int, right_value: int) -> int:
    try:
        value = output_values[right_value + 128 * left_value]
    except IndexError:
        logger.warning(
            f"Pressure values not found in XY table: {left_value}, {right_value}"
        )
        value = DEFAULT_VALUE

    # Prevent the big jumps to 0 and 127 that otherwise happen on initial press Reduces
    # the value's delta from center by a multiplier that increases to 1 over the first
    # portion of the range.
    smoothing_end_value = 10
    smoothing = (
        1
        if left_value == right_value
        else clamp(max(left_value, right_value) / smoothing_end_value, 0, 1)
    )

    return int(DEFAULT_VALUE - smoothing * (DEFAULT_VALUE - value))
