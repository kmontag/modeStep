import logging
from dataclasses import dataclass
from functools import partial
from time import time
from typing import Any, Dict, Optional, Union

from ableton.v3.control_surface.display import (
    DefaultNotifications,
    DisplaySpecification,
    Event,
    State,
    view,
)
from ableton.v3.control_surface.display.event_signal import EventSignalFn

from .mode import MainModeCategory, get_main_mode_category, get_track_controls_mode
from .track_controls import TrackControlsEditWindow, TrackControlsState
from .types import Action
from .ui import MAIN_MODE_DISPLAY_NAMES, TRACK_CONTROL_DISPLAY_NAMES

logger = logging.getLogger(__name__)

# Timing in seconds for scroll parameters.
BLINK = 0.1
SCROLL_STEP = 0.2
SCROLL_PRE_DELAY = 0.2
SCROLL_POST_DELAY = 0.5

DISPLAY_WIDTH = 4


@dataclass
class NotificationData:
    text: str = ""
    # Whether to initially blink this notification if it's the same as the last one.
    flash_on_repeat: bool = True


def _toggle_text(text: str, toggle_state: bool):
    return f"{'+' if toggle_state else '-'}{text}"


# Action descriptors reusable across the main notification class.
_action_texts: Dict[Action, str] = {
    "arrangement_record": "Rec",
    "auto_arm": "AAr",
    "automation_arm": "Aut",
    "backlight": "BaK",
    "capture_and_insert_scene": "CpSc",
    "capture_midi": "CpMD",
    "device_lock": "LocK",
    "launch_selected_scene": "LnSc",
    "metronome": "Met",
    "new": "NwCl",
    "play_toggle": "Play",
    "quantize": "Quan",
    "redo": "Redo",
    "selected_track_arm": "ArmT",
    "session_record": "SRec",
    "stop_all_clips": "StCl",
    "tap_tempo": "TapT",
    "undo": "Undo",
}


_TOGGLE_DESCRIPTIONS = {
    "Auto_Arm_Modes": _action_texts["auto_arm"],
    "Backlight_Modes": _action_texts["backlight"],
}


def _mode_select_notification(component_name: str, mode_name: str):
    toggle_state = True if mode_name == "on" else False
    if component_name in _TOGGLE_DESCRIPTIONS:
        return _toggle_text(_TOGGLE_DESCRIPTIONS[component_name], toggle_state)
    else:
        return None


def _quantize_notification(_name, quantization):
    return f"Q{quantization}"


def _right_align(prefix: str, value: Any):
    width = DISPLAY_WIDTH - len(prefix)
    format_str = prefix + "{:>" + str(width) + "}"
    return format_str.format(str(value))


# Humanize a 0-based index before right-aligning.
def _right_align_index(prefix: str, idx: int):
    return _right_align(prefix, idx + 1)


def _scene_notification(name: str, idx: Optional[int] = None, prefix: str = ""):
    # Note the Scene component never provides empty names (it converts them to "Scene
    # {}"), but in practice these notifications should be coming from nav buttons
    # assigned to our ViewControl component.
    if name or (idx is None):
        return name
    else:
        return _right_align_index(prefix, idx)


def _slider_value_notification(value: str):
    return NotificationData(text=_right_align("", value), flash_on_repeat=False)


class Notifications(DefaultNotifications):
    class Clip(DefaultNotifications.Clip):
        quantize = _quantize_notification

    class Device(DefaultNotifications.Device):
        bank = DefaultNotifications.DefaultText()
        select = DefaultNotifications.DefaultText()

        locked = (_action_texts["device_lock"] + " {}").format
        unlocked = "UnlK"

    class Modes(DefaultNotifications.Modes):
        select = _mode_select_notification

    class Recording(DefaultNotifications.Recording):
        capture_and_insert_scene = _action_texts["capture_and_insert_scene"]
        new = _action_texts["new"]

    class Scene(DefaultNotifications.Scene):
        launch = partial(_scene_notification, prefix="#")
        select = partial(_scene_notification, prefix="#")

    class SessionNavigation:
        vertical = partial(_right_align_index, "_")
        horizontal = partial(_right_align_index, "|")

    class Slider:
        value = _slider_value_notification

    class Track(DefaultNotifications.Track):
        # Disabling these for now, maybe should be removed entirely...
        arm = None
        select = DefaultNotifications.DefaultText()

    class TrackControls:
        delete = "DeL{}".format

        class EditAction:
            # Gets filled in below based on the action text map.
            pass

        class EditTrackControl:
            # Gets filled in below based on the track controls name map.
            pass

    class Transport(DefaultNotifications.Transport):
        automation_arm = None  # partial(_toggle_text, _action_texts["automation_arm"])
        # metronome = partial(_toggle_text, _action_texts["metronome"])
        midi_capture = _action_texts["capture_midi"]
        tap_tempo = lambda t: _right_align("T", int(t))  # noqa: E731

    class UndoRedo(DefaultNotifications.UndoRedo):
        undo = DefaultNotifications.DefaultText()
        redo = DefaultNotifications.DefaultText()


# Inject action descriptions for the track controls edit modes.
for action, text in _action_texts.items():
    setattr(Notifications.TrackControls.EditAction, action, text)
for track_control, text in TRACK_CONTROL_DISPLAY_NAMES.items():
    setattr(Notifications.TrackControls.EditTrackControl, track_control, text)


@dataclass
class Content:
    # The last timestamp when the main view was updated via a mode change or
    # similar. Internal value passed up the rendering chain.
    _main_timestamp: float

    text: Optional[str] = None
    scroll_offset: int = 0


def get_scroll_offset(
    started_at: float, initial_delay: float = 0.0, scroll_step: float = SCROLL_STEP
):
    # Add a little buffer to account for float errors, so that e.g. (0.3 / 0.1) gives 3.
    position = (0.01 + time() - started_at - initial_delay) / scroll_step
    return int(position) if position > 0 else 0


def get_max_non_looping_scroll_offset(text: str):
    return max(0, len(text) - DISPLAY_WIDTH)


@dataclass
class ScrollingNotificationData:
    timestamp: float = 0.0
    duration: float = 0.0
    text: str = ""
    replaced_text: Optional[str] = None
    flash_on_repeat: bool = True


class ScrollingNotificationView(view.NotificationView):
    def __init__(self, *a, scroll_step: float = SCROLL_STEP, **k):
        super().__init__(*a, **k)
        self._prev_data: Optional[ScrollingNotificationData] = None
        self._scroll_step = scroll_step
        orig_notification_signal = self._notification_signal

        # Extend the main notification signal generator to add metadata.
        def notification_signal(
            state: State, event: Event
        ) -> Optional[ScrollingNotificationData]:
            # Original signal is the result of applying the notification's factory
            # method.
            orig_notification_data: Optional[
                Union[str, NotificationData]
            ] = orig_notification_signal(state, event)

            if orig_notification_data is not None:
                # logger.info(f"got notification: {orig_notification_data}")
                # Normalize to our custom data object if a plain string was notified.
                notification_data: NotificationData = (
                    orig_notification_data
                    if isinstance(orig_notification_data, NotificationData)
                    else NotificationData(text=orig_notification_data)
                )

                current_time = time()
                duration = (self._duration or 0.0) + get_max_non_looping_scroll_offset(
                    notification_data.text
                ) * self._scroll_step
                replaced_text = (
                    self._prev_data.text
                    if self._prev_data
                    and current_time
                    < self._prev_data.timestamp + self._prev_data.duration
                    else None
                )
                self._prev_data = ScrollingNotificationData(
                    timestamp=time(),
                    text=notification_data.text,
                    duration=duration,
                    replaced_text=replaced_text,
                    flash_on_repeat=notification_data.flash_on_repeat,
                )
                return self._prev_data
            return None

        self._notification_signal: EventSignalFn = notification_signal

    # Gets called whenever a notification has been recieved, to clear it out after a
    # delay. Add the time needed to scroll through the notification, if any.
    def reset_state(self, state: State, delay: Optional[float] = None):
        notification_data = self._get_notification_data(state)
        # Extend the delay if we need to scroll the text.
        if delay is not None and notification_data is not None:
            delay = notification_data.duration
        return super().reset_state(state, delay)

    def _get_notification_data(
        self, state: State
    ) -> Optional[ScrollingNotificationData]:
        return getattr(state, self._name) if hasattr(state, self._name) else None

    def render(self, state: State):
        return super().render(state)


# Hacky singleton state for the root view. The view methods don't have access to normal
# variables in the global namespace, so we use a class.
class _RootViewState:
    last_flash_timestamp: float = 0.0


def create_root_view() -> view.View[Optional[Content]]:
    @view.View
    def main_view(state) -> Content:
        # logger.info(f"{state}")
        main_mode_name = state.main_modes.selected_mode
        main_mode_category = get_main_mode_category(main_mode_name)

        text: Optional[str] = None
        scroll_offset = 0
        timestamp = state.main_modes.entered_at  # Overridden if necessary below.

        # Show the dynamic description in track control modes.
        if main_mode_category is MainModeCategory.track_controls:
            # Components are named such that the state key matches the mode name.
            track_controls_state: Optional[TrackControlsState] = getattr(
                state, main_mode_name
            ).state

            # Disabled component gibberish, shown if a disabled track control gets
            # entered via e.g. the quick-mode-switch action.
            text = "*?&$"

            if track_controls_state:
                top_text, bottom_text = [
                    getattr(Notifications.TrackControls.EditTrackControl, name)
                    for name in (
                        track_controls_state.top_control,
                        track_controls_state.bottom_control,
                    )
                ]
                if top_text == bottom_text:
                    text = top_text
                else:
                    width = int(DISPLAY_WIDTH / 2)
                    text = f"{top_text[:width]}{bottom_text[:width]}"

        # Show the editor status in track control edit modes.
        elif main_mode_category is MainModeCategory.edit_track_controls:
            track_controls_mode_name = get_track_controls_mode(main_mode_name)
            assert track_controls_mode_name
            component_state = getattr(state, track_controls_mode_name)

            edit_window: Optional[TrackControlsEditWindow] = component_state.edit_window
            assert edit_window
            text = {
                TrackControlsEditWindow.action: "Act",
                TrackControlsEditWindow.action_alt: "Utl",
                TrackControlsEditWindow.bottom_control: "Bot",
                TrackControlsEditWindow.top_control: "Top",
            }[edit_window]

            text = f"{component_state.descriptor}{text}"
            # Hack to get popups to display if they were fired immediately before this
            # edit window was entered, i.e. as the result of an action or control
            # selection. This still lets the edit mode "back" button clear popups once
            # an edit screen has been opened. Note that popups will also be cleared by
            # the main mode text after the edit window has been closed.
            timestamp = component_state.edit_window_updated_at - 0.01

        elif main_mode_category in (
            MainModeCategory.standalone,
            MainModeCategory.hidden,
        ):
            # Make sure the text stays as `None` to avoid any rendering.
            pass

        # Show the mode name for all other modes.
        else:
            text = MAIN_MODE_DISPLAY_NAMES.get(main_mode_name, "")

        # Check if we need to scroll.
        if text and len(text) > DISPLAY_WIDTH:
            # No initial delay for mode display, the only scrolling one is the mode
            # select screen.
            scroll_offset = get_scroll_offset(state.main_modes.entered_at)

        return Content(
            _main_timestamp=timestamp, text=text, scroll_offset=scroll_offset
        )

    def notification_content(state, data: ScrollingNotificationData):
        content = main_view(state)
        if (
            # Don't handle notifications if the main text has been set to None - this
            # indicates no messages should be sent to the device.
            content.text is not None
            # Allow main mode changes to stomp on the notification display.
            and data.timestamp >= content._main_timestamp
        ):
            current_time = time()
            # logger.info(f"notif {data}")
            if (
                # Show a blink at the beginning if this is a repeated notification.
                (
                    data.replaced_text is not None
                    and data.flash_on_repeat
                    # Avoid blanking out the screen forever if the notifications are
                    # triggered very quickly.
                    and current_time - _RootViewState.last_flash_timestamp > BLINK
                    and data.replaced_text[:DISPLAY_WIDTH] == data.text[:DISPLAY_WIDTH]
                    and current_time - data.timestamp <= BLINK
                )
                # Show a blink at the end.
                or time() >= data.timestamp + data.duration - BLINK
            ):
                _RootViewState.last_flash_timestamp = current_time
                content.text = ""
                content.scroll_offset = 0
            else:
                content.text = data.text
                content.scroll_offset = min(
                    get_scroll_offset(data.timestamp, initial_delay=SCROLL_PRE_DELAY),
                    get_max_non_looping_scroll_offset(data.text),
                )

        return content

    return view.CompoundView(
        ScrollingNotificationView(
            notification_content, duration=SCROLL_PRE_DELAY + SCROLL_POST_DELAY + BLINK
        ),
        main_view,
    )


def protocol(elements):
    def display(content: Content):
        text = content.text
        if text is None:
            # Make sure we re-render next time, even if the text doesn't change.
            elements.display.clear_send_cache()
        else:
            if content.scroll_offset > 0:
                # Duplicate the string to get a "wrapping" scroll.
                wrapped_offset = content.scroll_offset % len(text)
                text = f"{text}{text}"[wrapped_offset:]
            # logger.info(f"display: {text[:DISPLAY_WIDTH]}")
            elements.display.display_message(text[:DISPLAY_WIDTH])

    return display


display_specification = DisplaySpecification(
    create_root_view=create_root_view, protocol=protocol, notifications=Notifications
)
