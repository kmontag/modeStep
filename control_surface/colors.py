from __future__ import annotations

import logging
import typing
from enum import Enum

from ableton.v2.control_surface.mode import to_camel_case_name
from ableton.v3.control_surface.elements import (
    Color as ColorBase,
)

from .types import Action

logger = logging.getLogger(__name__)


class LedColor(Enum):
    # Values are the CC offsets for controlling the respective LEDs colors.
    RED = 20
    GREEN = 110


class LedMode(Enum):
    # These are set to the CC value that needs to be sent to set each
    # mode.
    OFF = 0
    ON = 1
    BLINK = 2
    FAST_BLINK = 3
    FLASH = 4


class ColorInterfaceMixin:
    # Send a color using the standard red and green CCs. Arguments are
    # the values to be sent on each CC.
    #
    # If delay is true, the send should be performed asynchronously on
    # the next tick. This can be used to keep blinking LEDs reasonably
    # in sync when many of them are activated at once.
    def send_color(self, red: int, green: int, color: Color, delay: bool = False):
        raise NotImplementedError

    # Send a color using SoftStep's older API for setting
    # colors. Needed for solid yellow. Arguments are the values to be
    # sent on the color and state CCs, plus the color object being sent.
    def send_deprecated_color(self, value: int, state: int, color: Color):
        raise NotImplementedError


class Color(ColorBase):
    def __init__(
        self,
        mode: LedMode = LedMode.OFF,
        color: LedColor = LedColor.GREEN,
        accent_mode: LedMode = LedMode.OFF,
        *a,
        **k,
    ):
        """
        :param LedColor color: The main color to activate.
        :param LedMode mode: The mode of the specified LED color.
        :param LedMode accent_mode: Mode for the other LED. This can be used to create yellow LEDs, or even e.g. a yellow blinking effect against a constant green or red background.

        """
        super().__init__(*a, **k)
        self._mode = mode
        self._color = color
        self._accent_mode = accent_mode

    @property
    def color(self):
        return self._color

    @property
    def mode(self):
        return self._mode

    @property
    def accent_mode(self):
        return self._accent_mode

    def draw(self, interface: typing.Any):
        if not isinstance(interface, ColorInterfaceMixin):
            return

        def get_mode(color: LedColor):
            return self.mode if self.color is color else self.accent_mode

        red = get_mode(LedColor.RED)
        green = get_mode(LedColor.GREEN)
        if red is LedMode.ON and green is LedMode.ON:
            interface.send_deprecated_color(
                # Value for the color CC (green = 0, red = 1, yellow = 2).
                value=2,
                # Set the mode to ON.
                state=1,
                color=self,
            )

        interface.send_color(
            red=red.value,
            green=green.value,
            delay=(self._mode == LedMode.BLINK),
            color=self,
        )

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return (
                other.color == self.color
                and other.mode == self.mode
                and other.accent_mode == self.accent_mode
            )
        else:
            return False

    def __str__(self):
        return f"{self._color.name[0]}{self._mode.value}A{self._accent_mode.value}"


# Constants for convenience.
OFF = Color(LedMode.OFF)

GREEN_ON = Color(LedMode.ON, LedColor.GREEN)
GREEN_BLINK = Color(LedMode.BLINK, LedColor.GREEN)
GREEN_FAST_BLINK = Color(LedMode.FAST_BLINK, LedColor.GREEN)
GREEN_FLASH = Color(LedMode.FLASH, LedColor.GREEN)

RED_ON = Color(LedMode.ON, LedColor.RED)
RED_BLINK = Color(LedMode.BLINK, LedColor.RED)
RED_FAST_BLINK = Color(LedMode.FAST_BLINK, LedColor.RED)
RED_FLASH = Color(LedMode.FLASH, LedColor.RED)

YELLOW_ON = Color(LedMode.ON, LedColor.RED, LedMode.ON)
YELLOW_BLINK = Color(LedMode.BLINK, LedColor.RED, LedMode.BLINK)
YELLOW_FAST_BLINK = Color(LedMode.FAST_BLINK, LedColor.RED, LedMode.FAST_BLINK)
YELLOW_FLASH = Color(LedMode.FLASH, LedColor.RED, LedMode.FLASH)


# Get a blinking version of the given color.
def _blink(color: Color, mode: LedMode = LedMode.BLINK) -> Color:
    return Color(
        mode,
        color.color,
        LedMode.OFF if color.accent_mode is LedMode.OFF else mode,
    )


TOGGLE_ON = GREEN_ON
TOGGLE_OFF = RED_ON


class Skin:
    class ClipActions:
        Quantize = YELLOW_ON
        QuantizePressed = OFF

    class Device:
        ExprOn = TOGGLE_ON
        ExprOff = TOGGLE_OFF

        LockOn = GREEN_ON
        LockOff = RED_ON

        ParameterOn = GREEN_ON
        AltParameterOn = RED_ON
        ParameterOff = AltParameterOff = OFF

        # In case navigation gets assigned to a button by overrides.
        Navigation = YELLOW_ON

        class Bank:
            Selected = TOGGLE_ON
            NotSelected = TOGGLE_OFF

            Navigation = YELLOW_ON

    class DefaultButton:
        On = GREEN_ON
        Off = OFF
        Disabled = OFF

    class MainModes:
        class ModeSelect:
            On = RED_ON
            PressDelayed = GREEN_FAST_BLINK
            Off = GREEN_ON
            PopMode = RED_ON

        class _Category:
            # Mode buttons for most categories shouldn't generally show up while the
            # mode is active. This causes a brief blink during mode switch, however.
            On = OFF

            # This gets set if the long-press mode is a standalone mode.
            PressDelayed = GREEN_FAST_BLINK

        class Device(_Category):
            Off = GREEN_BLINK

        class TrackControls(_Category):
            Off = RED_BLINK

        class EditTrackControls(TrackControls):
            pass

        class Standalone(_Category):
            Off = YELLOW_BLINK

        class Uncategorized(_Category):
            Off = YELLOW_BLINK

    # Individual toggle mode components.
    class AutoArmModes:
        class Off:
            On = TOGGLE_OFF

        class On:
            On = TOGGLE_ON

    class BacklightModes:
        class Off:
            On = TOGGLE_OFF

        class On:
            On = TOGGLE_ON

    class Mixer:
        ArmOn = GREEN_ON
        ArmOff = RED_ON
        ImplicitArmOn = YELLOW_ON

        MuteOn = GREEN_ON
        MuteOff = RED_ON

        NoTrack = OFF

        SoloOn = GREEN_ON
        SoloOff = RED_ON

        Selected = TOGGLE_ON
        NotSelected = TOGGLE_OFF

        TrackVolume = YELLOW_ON

    class SceneNavigation:
        On = Pressed = GREEN_ON
        Off = OFF

    class TrackNavigation:
        On = Pressed = GREEN_ON
        Off = OFF

    class Transport:
        AutomationArmOn = YELLOW_ON
        AutomationArmOff = OFF
        CanCaptureMidi = RED_ON

        MetronomeOn = YELLOW_ON
        MetronomeOff = OFF
        PlayOn = GREEN_BLINK
        PlayOff = GREEN_ON
        TapTempo = YELLOW_ON
        TapTempoPressed = OFF

    class Recording:
        ArrangementRecordOn = RED_BLINK
        ArrangementRecordOff = RED_ON

        SessionRecordOn = RED_BLINK
        SessionRecordOff = RED_ON
        SessionRecordTransition = RED_FAST_BLINK
        SessionRecordStopping = RED_FAST_BLINK

        CaptureAndInsertScenePressed = OFF
        CaptureAndInsertScene = GREEN_ON

        NewPressed = OFF
        New = RED_ON

    class Session:
        StopAllClips = RED_ON
        StopAllClipsPressed = RED_ON
        StopAllClipsTriggered = RED_FAST_BLINK

        StopClip = RED_ON
        StopClipTriggered = RED_FAST_BLINK
        StopClipDisabled = YELLOW_ON

        ClipPlaying = GREEN_BLINK
        ClipRecording = RED_BLINK
        ClipStopped = GREEN_ON
        ClipTriggeredPlay = GREEN_FAST_BLINK
        ClipTriggeredRecord = RED_FAST_BLINK

        Slot = OFF  # Stop button with no clip.
        NoSlot = OFF
        SlotLacksStop = OFF
        SlotTriggeredPlay = YELLOW_FAST_BLINK
        SlotTriggeredRecord = RED_FAST_BLINK
        SlotRecordButton = RED_ON

        Scene = GREEN_ON
        SceneTriggered = GREEN_FAST_BLINK

        Navigation = YELLOW_ON
        NavigationPressed = OFF

    class TrackControls:
        Enabled = RED_BLINK
        Disabled = OFF

        EditAction = YELLOW_ON

        Cancel = RED_ON
        WarnDelete = RED_FAST_BLINK

        TrackSelect = GREEN_BLINK
        Arm = RED_BLINK
        Mute = YELLOW_BLINK
        Solo = GREEN_BLINK
        Volume = YELLOW_BLINK
        ClipLaunch = GREEN_BLINK
        StopTrackClip = RED_BLINK

    class UndoRedo:
        Disabled = UndoPressed = RedoPressed = OFF
        Undo = RED_ON
        Redo = GREEN_ON

    class ViewControl:
        # Navigation buttons.
        Scene = YELLOW_ON
        ScenePressed = OFF
        Track = YELLOW_ON
        TrackPressed = OFF


def _inject_track_controls_colors(control_preset):
    action_colors: typing.Dict[Action, Color] = {
        "arrangement_record": Skin.Recording.ArrangementRecordOn,
        "auto_arm": Skin.AutoArmModes.On.On,
        "automation_arm": Skin.Transport.AutomationArmOn,
        "backlight": Skin.BacklightModes.On.On,
        "capture_and_insert_scene": Skin.Recording.CaptureAndInsertScene,
        "capture_midi": Skin.Transport.CanCaptureMidi,
        "device_lock": Skin.Device.LockOn,
        "launch_selected_scene": Skin.Session.Scene,
        "metronome": Skin.Transport.MetronomeOn,
        "new": Skin.Recording.New,
        "play_toggle": Skin.Transport.PlayOn,
        "quantize": Skin.ClipActions.Quantize,
        "redo": Skin.UndoRedo.Redo,
        "selected_track_arm": Skin.Mixer.ArmOn,
        "session_record": Skin.Recording.SessionRecordOn,
        "stop_all_clips": Skin.Session.StopAllClips,
        "tap_tempo": Skin.Transport.TapTempo,
        "undo": Skin.UndoRedo.Undo,
    }

    for action, color in action_colors.items():
        class_name = to_camel_case_name(action)
        if not hasattr(control_preset, class_name):
            setattr(control_preset, class_name, _blink(color))


_inject_track_controls_colors(Skin.TrackControls)
