POETRY := $(shell command -v poetry 2> /dev/null)

# Recognize "Ableton Live 12 Suite", "Ableton Live 12 Lite", etc. Escape whitespace int
# he result so that we can use this as a target.
SYSTEM_MIDI_REMOTE_SCRIPTS_DIR := $(shell ls -d /Applications/Ableton\ Live\ 12\ *.app/Contents/App-Resources/MIDI\ Remote\ Scripts 2> /dev/null | head -n 1 | sed 's/ /\\ /g')

TEST_PROJECT_SET_NAMES := backlight default overrides standalone wide_clip_launch
TEST_PROJECT_DIR := tests/modeStep_tests_project
TEST_PROJECT_SETS := $(addprefix $(TEST_PROJECT_DIR)/, $(addsuffix .als, $(TEST_PROJECT_SET_NAMES)))

.PHONY: default
default: lint check

.PHONY: install
install: .make.install

.PHONY: lint
lint: .make.install
	$(POETRY) run ruff format --check .
	$(POETRY) run ruff check .

.PHONY: fix
format: .make.install
	$(POETRY) run ruff format .
	$(POETRY) run ruff check --fix .

.PHONY: check
check: .make.install __ext__/AbletonLive12_MIDIRemoteScripts/README.md
	$(POETRY) run pyright .

.PHONY: test
test: .make.install $(TEST_PROJECT_SETS)
	$(POETRY) run pytest

.PHONY: img
img: .make.install
	$(POETRY) run python img/generate.py

.PHONY: clean
clean:
# The .venv folder gets created by poetry (because virtualenvs.in-project is enabled).
	rm -rf .venv/
	rm -f .make.*

# Proxy target for the remote scripts submodule.
__ext__/AbletonLive12_MIDIRemoteScripts/README.md: .gitmodules
	git submodule update --init "$(@D)"

# Set files with different configurations for testing.
$(TEST_PROJECT_DIR)/%.als: .make.install $(TEST_PROJECT_DIR)/create_set.py
	$(POETRY) run python $(TEST_PROJECT_DIR)/create_set.py $*

# decompyle3 works for most files, and the ones where it doesn't don't
# matter for our purposes.
	$(POETRY) run decompyle3 -r -o $(@D)/ableton/ $(SYSTEM_MIDI_REMOTE_SCRIPTS_DIR)/ableton/

	touch $@

.make.install: pyproject.toml poetry.lock
	@if [ -z $(POETRY) ]; then echo "Poetry could not be found. See https://python-poetry.org/docs/"; exit 2; fi
	$(POETRY) install
	touch $@
