# Helper to output the config clip names that should be pasted into each set in this
# project. The data here isn't referenced anywhere else in the python application or
# tests, but it's tedious/error-prone to edit JSON directly in the sets.
import argparse
import gzip
import json
import os
from typing import TYPE_CHECKING, Dict
from xml.sax.saxutils import escape

from rich.console import Console

if TYPE_CHECKING:
    # The control_surface namespace is available to the type checker but not at runtime.
    from control_surface.configuration import Configuration
else:
    # Otherwise, use a fake config class that just implements a passthrough _asdict.
    class Configuration:
        def __init__(self, **k):
            self._dict: dict = k

        def _asdict(self):
            return self._dict


configurations: Dict[str, Configuration] = {
    "default": Configuration(),
    "alt_initial_mode": Configuration(
        initial_mode="utility",
        initial_last_mode="device_parameters_xy",
    ),
    "backlight": Configuration(backlight=True),
    "overrides": Configuration(
        override_elements={
            "transport": [
                ("left_buttons_raw[6]", "Session_Navigation", "left_button"),
                ("right_buttons_raw[6]", "Session_Navigation", "right_button"),
                ("up_buttons_raw[6]", "Background", "up_button"),
                ("down_buttons_raw[6]", "Background", "down_button"),
            ]
        },
        override_key_safety_strategies={
            "track_controls_1": "adjacent_lockout",
            "track_controls_2": "single_key",
            "track_controls_3": "all_keys",
        },
        override_modes={
            "6": ("utility", "device_parameters_increment"),
            "7": ("device_expression_map", None),
            "8": None,
        },
        override_track_controls={
            # Track select is useful for testing the key safety strategies, since it
            # doesn't push unsaved changes to the set.
            "1": ("track_select", "track_select", "session_record"),
            "2": ("track_select", "track_select", "session_record"),
            # Also configure an action on this one.
            "3": ("track_select", "track_select", "play_toggle"),
            # Separate controls with an action.
            "4": ("mute", "stop_track_clip", "backlight"),
            # Disabled track controls.
            "5": None,
        },
    ),
    "standalone": Configuration(
        override_modes={
            "3": ("standalone_1", None),
            "4": ("track_controls_4", "standalone_4"),
            "5": ("standalone_2", "standalone_3"),
        },
        background_program=10,
    ),
    "wide_clip_launch": Configuration(
        wide_clip_launch=True,
    ),
}

if __name__ == "__main__":
    parser = argparse.ArgumentParser("create_set")
    parser.add_argument("name", help="The configuration name to use for the set")
    args = parser.parse_args()

    name: str = args.name
    dirname = os.path.dirname(os.path.realpath(__file__))
    filename = f"{name}.als"

    configuration = configurations[name]
    configuration_clip_name = f"ms={json.dumps(configuration._asdict())}"

    # The base set is the default Live set with:
    # - the two audio tracks removed
    # - five MIDI tracks added (for a total of 7)
    # - a clip on track 1, scene 1 with name "REPLACE_ME"
    # - a clip on track 3, scene 2
    # - a clip on track 6, scene 1
    #
    # All test sets are based on this set, with a different modeStep configuration
    # applied via the "REPLACE_ME" clip. The base set can be updated as testing
    # requirements evolve.
    set_xml: str
    with gzip.open(os.path.join(dirname, "_base.als"), "rt") as base_set:
        # The set is just a gzipped xml document.
        base_set_xml = base_set.read()
        set_xml = base_set_xml.replace(
            "REPLACE_ME",
            # The clip name is set on an XML attribute, so it needs to be escaped. See
            # https://stackoverflow.com/questions/1546717/escaping-strings-for-use-in-xml.
            escape(configuration_clip_name, entities={"'": "&apos;", '"': "&quot;"}),
        )

    with gzip.open(os.path.join(dirname, filename), "wt") as target_set:
        target_set.write(set_xml)

    console = Console()
    console.print(f"Wrote [bold green]{filename}[/bold green]")
    console.print(f"--> configuration: {configuration_clip_name}")
