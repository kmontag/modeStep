from conftest import (
    Device,
    DeviceState,
    cc_action,
    get_cc_for_key,
    get_color,
    stabilize_after_cc_action,
    sync,
)
from pytest_bdd import parsers, scenarios, then
from typeguard import typechecked

scenarios("transport.feature")


# Check that pressing a button twice toggles the light on/off, and toggles the
# corresponding display between "+{control}" and "-{control}" respectively, but don't
# care about whether the toggle is initially on or off.
#
# This allows checking the behavior of transport buttons whose state is saved globally
# in Live (i.e. not as part of the Set).
@then(parsers.parse('key {key_number:d} should toggle the "{control}" status'))
@sync
@typechecked
async def should_toggle_control(
    key_number: int,
    control: str,
    device: Device,
    device_state: DeviceState,
):
    cc = get_cc_for_key(key_number)

    # Check the LED status and the popup display immediately after pressing the button,
    # and see if it matches the given on/off status for the toggle.
    def assert_matches_status_after_press(status: bool):
        # All transport toggles are currently solid yellow. We can parametrize this if
        # needed in the future.
        color = get_color(key_number, device_state)
        expected_color = "solid yellow" if status else "off"
        assert (
            color == expected_color
        ), f"Expected color to be {expected_color}, but was {color}"

        expected_display_text = f'{"+" if status else "-"}{control}'
        assert (
            device_state.display_text == expected_display_text
        ), f'Expected display text to be "{expected_display_text}", but was "{device_state.display_text}"'

    current_status = False if get_color(key_number, device_state) == "off" else True

    for _ in range(2):
        await cc_action(cc, "press", device)
        await stabilize_after_cc_action(device)

        current_status = not current_status
        assert_matches_status_after_press(current_status)
