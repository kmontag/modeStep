Feature: Device connection/disconnection events
  Scenario Outline: Reconnecting the SS2
    Given the SS2 is connected
    And the default set is open
    And the SS2 is initialized

    Then the display should be "Trns"

    # Disconnect/reconnect and make sure the initial mode loads again within a short delay.
    When I disconnect the SS2
    And I wait for <delay>s
    And I connect the SS2
    And I wait for the SS2 to be initialized

    Then the display should be "Trns"
    And light 5 should be solid red
    And light 0 should be solid green

    # Switch to another mode and make sure the UI gets updated on reconnect.
    When I press key 0
    Then the mode select screen should be active

    When I press key 7
    Then the display should be "Prss"

    When I disconnect the SS2
    And I wait for <delay>s
    And I connect the SS2
    And I wait for the SS2 to be initialized

    Then the display should be "Prss"
    And light 0 should be solid green

    # Switch to the mode select screen and make sure it gets reloaded on reconnect.
    When I press key 0
    Then the mode select screen should be active

    When I disconnect the SS2
    And I wait for <delay>s
    And I connect the SS2
    And I wait for the SS2 to be initialized

    Then the mode select screen should be active
    And light 0 should be solid red

    # Make sure the mode select screen exits back to the correct place.
    When I press key 0
    Then the display should be "Prss"
    And light 0 should be solid green

    # Make sure the quick-switch history was preserved.
    When I long-press key 0
    Then the display should be "Trns"
    And light 0 should be solid green
    And light 5 should be solid red

  Examples:
    | delay |
    |   0.1 |
    |   4.0 |
