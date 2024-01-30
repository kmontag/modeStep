from logging import getLogger
from typing import Callable, Optional

from ableton.v3.base import task
from ableton.v3.control_surface import InputControlElement

logger = getLogger(__name__)


class InputLock:
    def __init__(self, can_acquire: Callable[[], bool]):
        self._can_acquire = can_acquire
        self._is_acquired = False

    @property
    def is_acquired(self) -> bool:
        return self._is_acquired

    # Returns whether the lock could be acquired. This can be called repeatedly; once
    # acquired, this will always return true until the lock has been explicitly
    # released.
    def acquire(self) -> bool:
        if self._is_acquired:
            return True
        else:
            self._is_acquired = self._can_acquire()
            return self._is_acquired

    def release(self):
        self._is_acquired = False


class PressureInputElement(InputControlElement):
    """A raw input element which tries to obtain a lock when receiving inputs, and
    suppresses them if it can't be acquired.
    """

    def __init__(
        self,
        msg_type,
        channel,
        identifier,
        *a,
        input_lock: Optional[InputLock] = None,
        **k,
    ):
        super().__init__(
            msg_type,
            channel,
            identifier,
            *a,
            **k,
        )
        self._value: Optional[int] = None
        self._input_lock = input_lock

        # Help the type checker.
        self._tasks: task.TaskGroup

    def _do_send_value(self, value, channel=None):
        # LED updates happen via higher-level compound
        # elements. Values sent directly to inputs aren't relevant or
        # recognized by the SoftStep, we should ignore them.
        pass

    def receive_value(self, value: int):
        # logger.info(f"{self} received {value}")
        self._value = value

        # Note this doesn't currently gracefully handle disconnects or
        # breaks in the value stream (which happen e.g. if this
        # element isn't bound to anything). If standalone mode is
        # entered while a button is pressed, the SoftStep actually
        # sends a 0 on that channel when returning to hosted mode,
        # meaning we don't run into any issues in practice. A 0 is
        # also sent after processing if a button is pressed when the
        # greeting message gets sent (which freezes the controller for
        # a moment), and released during processing. However, if the
        # controller is disconnected during a button press and then
        # reconnected, the button will be "stuck" until that input is
        # pressed and released again.
        is_value_safe = self._input_lock is None or self._input_lock.acquire()
        if is_value_safe:
            super().receive_value(value)

            if value == 0 and self._input_lock is not None:
                self._input_lock.release()

    @property
    def value(self) -> Optional[int]:
        return self._value

    def __str__(self) -> str:
        return self.name
