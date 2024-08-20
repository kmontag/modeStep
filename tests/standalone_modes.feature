Feature: Standalone modes
  Background:
    Given the standalone set is open

  Scenario: Setting the standalone background mode
    Given the SS2 is initialized
    Then the standalone background program should be active

  Scenario: Switching into and out of standalone modes
    Given the SS2 is initialized
    Then the display should be "Trns"

    # Check the presence of the standalone modes on the mode select
    # screen.
    When I press key 0
    Then the mode select screen should be active
    And light 5 should be blinking yellow

    # Open the main standalone mode.
    When I hold key 5 without waiting
    Then releasing key 5 should enter standalone program 1
    # Sanity check.
    And the SS2 should be in standalone mode

    # Go back to mode select.
    When I hold the standalone exit button
    Then releasing the standalone exit button should enter hosted mode
    # Sanity check.
    And the SS2 should be in hosted mode
    And the mode select screen should be active

    # Go to another mode, then quick-switch to the standalone mode.
    When I press key 7
    Then the display should be "Prss"

    When I hold key 0
    And I wait to trigger a long-press
    Then light 0 should be fast-blinking green
    And releasing key 0 should enter standalone program 1

    # Quick-switch back to the main mode.
    When I hold the standalone exit button
    And I wait to trigger a long-press
    Then releasing the standalone exit button should enter hosted mode
    And the display should be "Prss"
    And light 0 should be solid green
    And light 5 should be solid red

    # Go to the alternate standalone mode.
    When I press key 0
    And I hold key 5
    And I wait to trigger a long-press
    Then light 5 should be fast-blinking green
    And releasing key 5 should enter standalone program 2

    # Go back and select the primary standalone mode.
    When I hold the standalone exit button
    Then releasing the standalone exit button should enter hosted mode
    And the mode select screen should be active

    When I hold key 5 without waiting
    Then releasing key 5 should enter standalone program 1

    # Switch directly between the standalone modes.
    When I hold the standalone exit button
    And I wait to trigger a long-press
    Then releasing the standalone exit button should switch directly to standalone program 2

    When I hold the standalone exit button
    And I wait to trigger a long-press
    Then releasing the standalone exit button should switch directly to standalone program 1

    # Go back to a hosted mode and quick-switch again.
    When I hold the standalone exit button
    Then releasing the standalone exit button should enter hosted mode
    And the mode select screen should be active

    When I press key 8
    Then the display should be "Incr"

    When I hold key 0
    And I wait to trigger a long-press
    Then light 0 should be fast-blinking green
    And releasing key 0 should enter standalone program 1

    When I hold the standalone exit button
    And I wait to trigger a long-press
    Then releasing the standalone exit button should enter hosted mode
    And the display should be "Incr"

    # Another permutation of quick-switching from a hosted mode after
    # previously quick-switching between standalone modes.
    When I hold key 0
    And I wait to trigger a long-press
    Then releasing key 0 should enter standalone program 1

    When I hold the standalone exit button
    Then releasing the standalone exit button should enter hosted mode
    And the mode select screen should be active

    When I hold key 5
    And I wait to trigger a long-press
    Then releasing key 5 should enter standalone program 2

    When I hold the standalone exit button
    And I wait to trigger a long-press
    Then releasing the standalone exit button should switch directly to standalone program 1

    When I hold the standalone exit button
    Then releasing the standalone exit button should enter hosted mode
    And the mode select screen should be active

    When I press key 9
    Then the display should be "Trns"

    When I hold key 0
    And I wait to trigger a long-press
    Then light 0 should be fast-blinking green
    And releasing key 0 should enter standalone program 1

  Scenario: Switching into a standalone mode which is an alternate of a non-standalone mode
    Given the SS2 is initialized
    When I press key 0
    Then the mode select screen should be active
    And light 4 should be blinking red

    When I press key 4
    Then the display should be "Mute"

    When I press key 0
    Then the mode select screen should be active

    When I hold key 4
    And I wait to trigger a long-press
    Then light 4 should be fast-blinking green
    And releasing key 4 should enter standalone program 3

    When I hold the standalone exit button
    Then releasing the standalone exit button should enter hosted mode
    And the mode select screen should be active

  Scenario: Switching into a standalone mode with no alternate mode
    Given the SS2 is initialized
    When I press key 0
    Then the mode select screen should be active
    And light 3 should be blinking yellow

    When I hold key 3 without waiting
    Then releasing key 3 should enter standalone program 0

    When I hold the standalone exit button
    Then releasing the standalone exit button should enter hosted mode
    And the mode select screen should be active
