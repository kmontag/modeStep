POETRY := $(shell command -v poetry 2> /dev/null)

# Recognize "Ableton Live 12 Suite", "Ableton Live 12 Lite", etc. Escape whitespace int
# he result so that we can use this as a target.
SYSTEM_MIDI_REMOTE_SCRIPTS_DIR := $(shell ls -d /Applications/Ableton\ Live\ 12\ *.app/Contents/App-Resources/MIDI\ Remote\ Scripts 2> /dev/null | head -n 1 | sed 's/ /\\ /g')

TEST_PROJECT_SET_NAMES := backlight default overrides standalone wide_clip_launch
TEST_PROJECT_DIR := tests/modeStep_tests_project
TEST_PROJECT_SETS := $(addprefix $(TEST_PROJECT_DIR)/, $(addsuffix .als, $(TEST_PROJECT_SET_NAMES)))

.PHONY: deps
deps:  .make.install __ext__/System_MIDIRemoteScripts/.make.decompile

.PHONY: lint
lint: .make.install
	$(POETRY) run ruff format --check .
	$(POETRY) run ruff check .

.PHONY: fix
format: .make.install
	$(POETRY) run ruff format .
	$(POETRY) run ruff check --fix .

.PHONY: check
check: .make.install __ext__/System_MIDIRemoteScripts/.make.decompile
	$(POETRY) run pyright .

.PHONY: test
test: .make.install $(TEST_PROJECT_SETS)
	$(POETRY) run pytest

.PHONY: img
img: .make.install
	$(POETRY) run python img/generate.py

.PHONY: clean
clean:
	rm -rf __ext__/System_MIDIRemoteScripts/
# The .venv folder gets created by poetry (because virtualenvs.in-project is enabled).
	rm -rf .venv/
	rm -f .make.install

# Set files with different configurations for testing.
$(TEST_PROJECT_DIR)/%.als: .make.install $(TEST_PROJECT_DIR)/create_set.py
	$(POETRY) run python $(TEST_PROJECT_DIR)/create_set.py $*

__ext__/System_MIDIRemoteScripts/.make.decompile: $(SYSTEM_MIDI_REMOTE_SCRIPTS_DIR) | .make.install
# Sanity check before rm'ing.
	@if [ -z "$(@D)" ]; then \
		echo "Sanity check failed: compile dir is not set"; \
		exit 1; \
	fi
	rm -rf $(@D)/
	mkdir -p $(@D)/ableton/
	@if [ -z $(SYSTEM_MIDI_REMOTE_SCRIPTS_DIR) ]; then \
		echo "System remote scripts directory not found" ; \
		exit 1; \
	fi
	@if [ ! -d $(SYSTEM_MIDI_REMOTE_SCRIPTS_DIR) ]; then \
		echo "The specified remote scripts directory ("$(SYSTEM_MIDI_REMOTE_SCRIPTS_DIR)") does not exist"; \
		exit 1; \
	fi

# decompyle3 works for most files, and the ones where it doesn't don't
# matter for our purposes.
	$(POETRY) run decompyle3 -r -o $(@D)/ableton/ $(SYSTEM_MIDI_REMOTE_SCRIPTS_DIR)/ableton/

	touch $@

.make.install: pyproject.toml poetry.lock
	@if [ -z $(POETRY) ]; then echo "Poetry could not be found. See https://python-poetry.org/docs/"; exit 2; fi
	$(POETRY) install
	touch $@
