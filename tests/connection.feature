Feature: Device connection/disconnection events
  Scenario Outline: Reconnecting the SS2
    Given the SS2 is connected
    And the default set is open
    And the SS2 is initialized

    Then the display should be "Trns"

    # Disconnect/reconnect and make sure the initial mode loads again within a short delay.
    When I disconnect the SS2
    And I wait for <delay>s
    And <before_connect_action>
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
    And <before_connect_action>
    And I connect the SS2
    And I wait for the SS2 to be initialized

    Then the display should be "Prss"
    And light 0 should be solid green

    # Switch to the mode select screen and make sure it gets reloaded on reconnect.
    When I press key 0
    Then the mode select screen should be active

    When I disconnect the SS2
    And I wait for <delay>s
    And <before_connect_action>
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

  # With a short delay, Live might send stray CCs after reconnect but before the device
  # is re-initialized. With a longer delay, we expect that no stray CCs will be sent.
  Examples:
    | delay | before_connect_action                              |
    |   0.1 | I allow stray display updates until initialization |
    |   4.0 | I do nothing                                       |

  Scenario: Connecting the SS2 after a set is loaded
    Given the default set is open

    When I wait for 5.0s
    And I connect the SS2
    And I wait for the SS2 to be initialized

    Then the display should be "Trns"
    And light 5 should be solid red
    And light 0 should be solid green

  Scenario: Opening other sets
    Given the SS2 is connected
    And the default set is open
    And the SS2 is initialized

    Then the display should be "Trns"

    # Switch the mode so we can make sure it gets reset when the set is reopened.
    When I press key 0
    And I press key 8
    Then the display should be "Incr"

    # "Forget" the device state so that we can wait for it to be re-initialized.
    When I forget the SS2's state
    And I allow stray display updates until initialization
    And I open the default set
    And I wait for the SS2 to be initialized

    Then the display should be "Trns"

    When I long-press key 0
    Then the mode select screen should be active

    # Open a different set with a different configuration, to make sure the
    # configuration can change between sets without restarting Live.
    When I forget the SS2's state
    And I allow stray display updates until initialization
    And I open the alt_initial_mode set
    And I wait for the SS2 to be initialized

    Then the display should be "Util"
