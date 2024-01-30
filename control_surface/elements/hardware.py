# This file contains basic hardware constants and convenience functions for getting CC
# assignments in hosted mode. It's also used in tests.
from enum import Enum

NUM_ROWS = 2
NUM_COLS = 5
NAV_BASE_CC = 80


# Values are the offsets of that direction's CC from the pedal's base
# CC number. Note that these offsets are different for the navigation
# pedal.
class KeyDirection(Enum):
    up = 0
    right = 1
    left = 2
    down = 3


# Rows and columns are indexed from 0 starting at the top left, i.e. button 6.
def get_cc_for_key(row: int, col: int, direction: KeyDirection):
    assert 0 <= row < NUM_ROWS
    assert 0 <= col < NUM_COLS

    # CCs start at 40, and each pedal gets 4 of them (one for each
    # side). They increment starting at top left and moving down then
    # to the right, i.e. 6 -> 1 -> 7 -> 2 -> ...
    cc_base = 40 + (NUM_ROWS * col * len(KeyDirection)) + row * len(KeyDirection)
    return cc_base + direction.value


def get_cc_for_nav(direction: KeyDirection):
    return (
        NAV_BASE_CC
        + {
            KeyDirection.left: 0,
            KeyDirection.right: 1,
            KeyDirection.up: 2,
            KeyDirection.down: 3,
        }[direction]
    )
