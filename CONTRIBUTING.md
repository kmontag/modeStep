## Development

modeStep uses [poetry](https://python-poetry.org/) for project management and
development tasks. The project's `Makefile` also contains targets for common tasks.

## Testing

Tests work by opening Live, impersonating the MIDI output of the SoftStep, and checking
the messages that Live sends back.

To get this working, you need to configure a "modeStep" control surface to use "modeStep
test" as its inputs and outputs. However, that source won't show up until tests are
actually running, so you'll need to configure the control surface manually while you're
running tests for the first time.

You can safely add this test control surface alongside your primary modeStep control
surface, if you don't want to deal with switching the input/output when you want to run
tests.

To run tests, use:

```shell
make test
```

For debug output:

```shell
DEBUG=1 make test
```

To run only e.g. specs tagged with `@now`:

```shell
poetry run pytest -m now
```

## Linting and type checks

Before submitting a PR, make sure the following are passing:

```shell
make lint # Validates code style.
make check # Validates types.
```

Some lint errors can be fixed automatically with:

```shell
make format
```
