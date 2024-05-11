SYSTEM_MIDI_REMOTE_SCRIPTS_DIR := /Applications/Ableton\ Live\ 12\ Suite.app/Contents/App-Resources/MIDI\ Remote\ Scripts
TEST_PROJECT_DIR = tests/modeStep_tests_project

.PHONY: deps
deps: __ext__/System_MIDIRemoteScripts/.make.decompile .make.pip-install

.PHONY: lint
lint: .make.pip-install
	.venv/bin/ruff format --check .
	.venv/bin/ruff check .

.PHONY: fix
fix: .make.pip-install
	.venv/bin/ruff format .
	.venv/bin/ruff check --fix .

.PHONY: check
check: .make.pip-install __ext__/System_MIDIRemoteScripts/.make.decompile
	.venv/bin/pyright .

.PHONY: test
test: .make.pip-install $(TEST_PROJECT_DIR)/default.als $(TEST_PROJECT_DIR)/overrides.als $(TEST_PROJECT_DIR)/standalone.als $(TEST_PROJECT_DIR)/wide_clip_launch.als
	.venv/bin/pytest

.PHONY: img
img: .make.pip-install
	cd img && ../.venv/bin/python generate.py

.PHONY: clean
clean:
	rm -rf .venv/
	rm -rf __ext__/System_MIDIRemoteScripts/
	rm -f .make.*

# Set files with different configurations for testing.
$(TEST_PROJECT_DIR)/%.als: .make.pip-install $(TEST_PROJECT_DIR)/create_set.py
	.venv/bin/python $(TEST_PROJECT_DIR)/create_set.py $*

__ext__/System_MIDIRemoteScripts/.make.decompile: $(SYSTEM_MIDI_REMOTE_SCRIPTS_DIR) | .make.pip-install
	rm -rf $(@D)/
	mkdir -p $(@D)/ableton/
# decompyle3 works for most files, and the ones where it doesn't don't
# matter for our purposes.
	.venv/bin/decompyle3 -r -o $(@D)/ableton/ $(SYSTEM_MIDI_REMOTE_SCRIPTS_DIR)/ableton/

	touch $@

.venv: .python-version
	python -m venv .venv

.make.pip-install: .venv requirements.txt .python-version
	.venv/bin/pip install -r requirements.txt
	touch $@
