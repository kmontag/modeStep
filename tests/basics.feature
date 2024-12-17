Feature: Basic usage
  Background:
    Given the SS2 is connected
    And the default set is open
    And the SS2 is initialized

  Scenario: Putting the device into hosted mode
    Then the SS2 should be in hosted mode

  Scenario: Navigating between modes
    Then the display should be "Trns"

    # Initially there should be no previous mode.
    When I long-press key 0
    Then the mode select screen should be active

    # Exit mode select.
    When I press key 0
    Then the display should be "Trns"

    # Select utility mode.
    When I press key 0
    Then the mode select screen should be active

    When I long-press key 9
    Then the display should be "Util"

    # Quick-switch.
    When I long-press key 0
    Then the display should be "Trns"

    # Open and close the mode select screen, then quick switch again.
    When I press key 0
    Then the mode select screen should be active

    When I press key 0
    Then the display should be "Trns"

    When I long-press key 0
    Then the display should be "Util"

    # Switch modes again.
    When I press key 0
    Then the mode select screen should be active

    When I long-press key 8
    Then the display should be "Expr"
    And lights 6-9 should be solid red
    And lights 1-4 should be solid red

    # Quick switch.
    When I long-press key 0
    Then the display should be "Util"

    # Quick switch from the mode select screen.
    When I press key 0
    Then the mode select screen should be active

    When I long-press key 0
    Then the display should be "Expr"
