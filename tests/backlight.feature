Feature: Backlight management
  Scenario Outline: Toggling the backlight when it is unconfigured
    Given the <set_name> set is open
    And the SS2 is initialized

    Then the backlight should be <initial_state>
    And the display should be "Trns"

    When I press key 0
    And I long-press key 9
    Then the display should be "Util"
    And light 6 should be solid <initial_color>

    When I press key 6
    Then light 6 should be solid <toggle_color>
    And the display should be "<toggle_disp>"
    And the backlight should be <toggle_state>

    When I press key 6
    Then light 6 should be solid <initial_color>
    And the display should be "<toggle2_disp>"
    And the backlight should be <toggle2_state>

  Examples:
    | set_name  | initial_state | toggle_state | toggle2_state | toggle_disp | toggle2_disp | initial_color | toggle_color |
    | default   | unmanaged     | on           | off           | +BaK        | -BaK         | red           | green        |
    | backlight | on            | off          | on            | -BaK        | +BaK         | green         | red          |
