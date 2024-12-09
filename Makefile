POETRY := $(shell command -v poetry 2> /dev/null)

# Recognize "Ableton Live 12 Suite", "Ableton Live 12 Lite", etc. Escape whitespace in
# the result so that this is (somewhat) usable elsewhere in the Makefile.
#
# TODO: Windows support.
SYSTEM_MIDI_REMOTE_SCRIPTS_DIR := $(shell ls -d /Applications/Ableton\ Live\ 12\ *.app/Contents/App-Resources/MIDI\ Remote\ Scripts 2> /dev/null | head -n 1 | sed 's/ /\\ /g')

# Targets for decompilation of Live's python libraries (one python file per .pyc file in
# the system Live installation).
#
# Note we expect there to be no whitespace in file/directory names beneath the
# SYSTEM_MIDI_REMOTE_SCRIPTS_DIR.
ABLETON_COMPILED_SOURCES := $(shell find $(SYSTEM_MIDI_REMOTE_SCRIPTS_DIR)/ableton -type f -name '*.pyc' | sed 's|^$(SYSTEM_MIDI_REMOTE_SCRIPTS_DIR)|__ext__/System_MIDIRemoteScripts_compiled|g')
ABLETON_SOURCES := $(patsubst %.pyc,%.py,$(subst System_MIDIRemoteScripts_compiled,System_MIDIRemoteScripts,$(ABLETON_COMPILED_SOURCES)))

TEST_PROJECT_SET_NAMES := backlight default overrides standalone wide_clip_launch
TEST_PROJECT_DIR := tests/modeStep_tests_project
TEST_PROJECT_SETS := $(addprefix $(TEST_PROJECT_DIR)/, $(addsuffix .als, $(TEST_PROJECT_SET_NAMES)))

.PHONY: default
default: lint check

.PHONY: install
install: .make.install

.PHONY: decompile
decompile: $(ABLETON_SOURCES)

.PHONY: lint
lint: .make.install
	$(POETRY) run ruff format --check .
	$(POETRY) run ruff check .

.PHONY: fix
format: .make.install
	$(POETRY) run ruff format .
	$(POETRY) run ruff check --fix .

.PHONY: check
check: .make.install $(ABLETON_SOURCES)
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
	rm -f __ext__/System_MIDIRemoteScripts_compiled
# The .venv folder gets created by poetry (because virtualenvs.in-project is enabled).
	rm -rf .venv/
	rm -f .make.install

# Set files with different configurations for testing.
$(TEST_PROJECT_DIR)/%.als: .make.install $(TEST_PROJECT_DIR)/create_set.py
	$(POETRY) run python $(TEST_PROJECT_DIR)/create_set.py $*

# Force a clean re-pull of the pycdc repository whenever its version changes. This is a
# bit heavy-handed but it ensures that we clean any lingering build artifacts.
__ext__/pycdc/README.md: .gitmodules
	rm -rf $(@D)
	git submodule update --init -- $(@D)
	touch $@

__ext__/pycdc/pycdc: __ext__/pycdc/README.md
	cd $(@D) && cmake . && make

# To avoid issues with spaces in the system remote scripts directory, "build" local pyc
# files by creating a local symlink to the system directory.
#
# The dependency on $(SYSTEM_MIDI_REMOTE_SCRIPTS_DIR) is a bit imprecise, but should
# generally ensure that the link gets recreated if the location of the system remote
# scripts directory changes, e.g. if the installed Live edition changes.
__ext__/System_MIDIRemoteScripts_compiled: $(SYSTEM_MIDI_REMOTE_SCRIPTS_DIR)
	ln -f -s $(SYSTEM_MIDI_REMOTE_SCRIPTS_DIR) __ext__/System_MIDIRemoteScripts_compiled

$(ABLETON_COMPILED_SOURCES): __ext__/System_MIDIRemoteScripts_compiled

__ext__/System_MIDIRemoteScripts/%.py: __ext__/System_MIDIRemoteScripts_compiled/%.pyc __ext__/pycdc/pycdc
	mkdir -p "$(@D)"
	set -o pipefail && __ext__/pycdc/pycdc $< | sed 's|^Unsupported|# Unsupported|g' | sed 's|^Warning|# Warning|g' > $@

.make.install: pyproject.toml poetry.lock
	@if [ -z $(POETRY) ]; then echo "Poetry could not be found. See https://python-poetry.org/docs/"; exit 2; fi
	$(POETRY) install
	touch $@
