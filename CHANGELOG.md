# CHANGELOG

## v0.0.1 (2024-08-19)

### Chore

* chore: switch minimum python version to 3.8 ([`0eb913f`](https://github.com/kmontag/modeStep/commit/0eb913f5efdad9dbe5682889be984387f795beb6))

* chore: switch to `poetry` for project management ([`326201f`](https://github.com/kmontag/modeStep/commit/326201f64f1ec42d0de834300d9b62ccb4450110))

### Ci

* ci: publish releases using semantic-release ([`295c043`](https://github.com/kmontag/modeStep/commit/295c043eab85230ce8a74b27e801d58ed711f8dd))

* ci: cache decompiled MIDI remote scripts ([`6df7e77`](https://github.com/kmontag/modeStep/commit/6df7e77d53859b8025ce569340aa3ad1ac28942a))

* ci: allow revert commits ([`491664b`](https://github.com/kmontag/modeStep/commit/491664b4e4ce3e151302944a63f992c2843c5cb0))

* ci: add semantic PRs config ([`87cede4`](https://github.com/kmontag/modeStep/commit/87cede46154ef5532dc1269c081298b159192bf3))

* ci: switch to latest macos ([`3602d65`](https://github.com/kmontag/modeStep/commit/3602d65e3026be44857e25afd67d6764f5366207))

* ci: add action to access CI server over VNC ([`1673a9a`](https://github.com/kmontag/modeStep/commit/1673a9a7c275eb09b747720491c57cf6dd6753d2))

* ci: add type-checking step with real Live resources ([`62f801a`](https://github.com/kmontag/modeStep/commit/62f801af1862b25eeadaa1507749389be66c3711))

* ci: switch to poetry for CI checks ([`bd28b9b`](https://github.com/kmontag/modeStep/commit/bd28b9b3b49da5b8e3cef13f8dbd9eb4109ed94a))

### Fix

* fix: fix elements type-checker issue ([`fca08d0`](https://github.com/kmontag/modeStep/commit/fca08d0a7c74d4e5746fa4de14d0f5a9e79104b0))

* fix: fix some typing issues ([`b396ad7`](https://github.com/kmontag/modeStep/commit/b396ad7383b2cbf06e9e2870e27713aec3cf5a6e))

### Unknown

* Revert &#34;ci: add action to access CI server over VNC&#34;

This reverts commit ed20bbcbe682790f8c98be63005cf198007dd31b.

The idea here was to use the GUI to build a `Preferences.cfg` that would allow tests to be run
in a GH action. Unfortunately Live crashes when opened in the GitHub runner, so this isn&#39;t
really useful as-is. ([`28d2731`](https://github.com/kmontag/modeStep/commit/28d2731e91aba4e1303a39f191438a73881f7839))

* Remove empty .gitmodules file ([`36ad3d3`](https://github.com/kmontag/modeStep/commit/36ad3d37ca5e5d5d85514445bac35e24b4c56693))

* Updates to backlight management and standalone/hosted mode transitions (#3)

* Cleaner handling of standalone/hosted mode state cache

* Clean up transitions between hosted and standalone modes

* Fix event expectations in standalone tests

* Disable backlight management by default

It causes issues with LEDs, and probably is a bit intrusive.

* Send a backlight update on disconnect if configured

* Force-update LEDs a few seconds after setting backlight

Works around a firmware issue where the LEDs revert to their values
from one of the standalone presets after sending a backlight sysex.

* Fix type check error

* Remove references to SSCOM port name ([`d1e3d88`](https://github.com/kmontag/modeStep/commit/d1e3d88c277d71915bf53367ed679c181b6cb322))

* Update README ([`8de012a`](https://github.com/kmontag/modeStep/commit/8de012a6b2aa68cc43864681d54c7d22fec5657b))

* Update README ([`c88259a`](https://github.com/kmontag/modeStep/commit/c88259ad4965756fe1bde0ef04127eeca50a0812))

* Update README ([`80e932b`](https://github.com/kmontag/modeStep/commit/80e932b07aa1912743a1c063494e0655eedb8d96))

* Remove unnecessary sysexes during standalone transitions ([`dfed784`](https://github.com/kmontag/modeStep/commit/dfed784bd8f5917aa7adcfcb25ff28a9795b1517))

* Update sysexes and handshake for SS firmware v2.x ([`9678e70`](https://github.com/kmontag/modeStep/commit/9678e70983c82b40cbff03698cb0df5b6022a42e))

* Live 12 also supported ([`caf29e2`](https://github.com/kmontag/modeStep/commit/caf29e225d3664429217179c528f2f4fa62c2644))

* Fix clip launch tests when auto arm is enabled ([`2f3a35d`](https://github.com/kmontag/modeStep/commit/2f3a35dede31a0e360438e1dcc33a3517217c052))

* Add venv setup ([`42b562c`](https://github.com/kmontag/modeStep/commit/42b562cfa243b605e0c0100fc514d9ceb209c2f8))

* Add tests for wide clip launch ([`2c980c3`](https://github.com/kmontag/modeStep/commit/2c980c36f8d24f011996e560bb3a7ab9562d6300))

* Update README ([`51c0200`](https://github.com/kmontag/modeStep/commit/51c0200909bd5850f5ddbe7aa18024ceb0bb21ba))

* Remove unused uncompyle dependency ([`13bd305`](https://github.com/kmontag/modeStep/commit/13bd305bfa3f7a63f0659413d9025d781f30235e))

* Validation workflow cleanup ([`429b77b`](https://github.com/kmontag/modeStep/commit/429b77b29258d24a107f50453d7fc3c75037ef2d))

* Fix README typo ([`edfdcff`](https://github.com/kmontag/modeStep/commit/edfdcff3bf7bd909ef9d2faa489e36d68082ba9d))

* Increase default full-pressure setting ([`db9ebca`](https://github.com/kmontag/modeStep/commit/db9ebca6bddcfe8cd6ab370f5160cac961d04eb0))

* Linter fixes ([`5b1fabf`](https://github.com/kmontag/modeStep/commit/5b1fabfa8903bf41193627ef7517dc5a7205661f))

* Change scene launch notification to match scene select ([`e42b6e6`](https://github.com/kmontag/modeStep/commit/e42b6e6031255590e6698e2b9c7260ba8033f4e3))

* Disable arm notifications ([`916c5bc`](https://github.com/kmontag/modeStep/commit/916c5bcdac53c68631817fb34d9c0b91c4671e60))

* Remove saved preferences ([`fe25f73`](https://github.com/kmontag/modeStep/commit/fe25f737a2b01cb6bf0a2f559c23c3e567f398ce))

* README updates ([`a4f31aa`](https://github.com/kmontag/modeStep/commit/a4f31aa23bce2506a72ea482b8406a24832da03e))

* Create LICENSE ([`e190a09`](https://github.com/kmontag/modeStep/commit/e190a09b06df79c19d3b8a84efde410aa77ff222))

* Initial publish ([`85fcd0d`](https://github.com/kmontag/modeStep/commit/85fcd0d001420a32cf6237b660167e78d71cb602))
