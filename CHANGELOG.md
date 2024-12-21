# CHANGELOG

## v0.1.0 (2024-12-21)

### Chore

* chore: hide terraform directory and add required PR checks ([`05b6969`](https://github.com/kmontag/modeStep/commit/05b6969ede28de1f580c546885e077b755cbbb5a))

### Documentation

* docs: update downloaded folder naming requirements ([`01a5430`](https://github.com/kmontag/modeStep/commit/01a54309652d879c4381d9486d85f886a90603d7))

### Feature

* feat: add display notifications for some transport actions (#10) ([`e808b53`](https://github.com/kmontag/modeStep/commit/e808b534c2c1bef11d6c68a150829e3462d4f4c2))

## v0.0.5 (2024-12-17)

### Documentation

* docs: use consistent indentation in standalone user.py example ([`7293e43`](https://github.com/kmontag/modeStep/commit/7293e4301a5c5395143553af623ff71b9697cb18))

* docs: fix typo in example user.py ([`cd1cfa4`](https://github.com/kmontag/modeStep/commit/cd1cfa4ea8a53eca10770ea89e89c208ec979177))

### Fix

* fix: improve robustness of device initialization on disconnect/reconnect (#9)

- cleans up startup logic for more predictable device initialization
- suppresses stray CCs which would otherwise be sent at startup and/or
when switching to standalone modes
- adds tests for disconnect/reconnect events and other device init
scenarios
- updates application python version to 3.11, following Live 12.1 ([`8c08b55`](https://github.com/kmontag/modeStep/commit/8c08b551c81e5267219f57a66997c60f7517eb5a))

## v0.0.4 (2024-12-11)

### Chore

* chore: remove stray decompyle call ([`e3f2a6e`](https://github.com/kmontag/modeStep/commit/e3f2a6eb2628a0f02a0e04df2efbb9abac0bddc5))

* chore: ensure that disabled mode is the first activated mode

Avoids added complexity with the pre-init mode in the mode stack. ([`2fd63da`](https://github.com/kmontag/modeStep/commit/2fd63da9715235ecaa877effddb436aab52f0478))

### Fix

* fix: unavailable runtime import ([`e572fca`](https://github.com/kmontag/modeStep/commit/e572fca99fdc301bed594c4c43e58b65f64c84f7))

## v0.0.3 (2024-12-11)

### Fix

* fix: increase attempts to reset LEDs after backlight changes

The underlying firmware bug sometimes triggers later than expected. ([`63c9fd6`](https://github.com/kmontag/modeStep/commit/63c9fd64f4c16fcfca0e917bcffb31b49ec2d43d))

* fix: fix MIDI messages out of order when exiting a standalone mode

Live&#39;s internal MIDI batching was causing sysex messages (i.e. to transition back to
hosted mode) to be sent before the background mode program change. ([`de12e1d`](https://github.com/kmontag/modeStep/commit/de12e1dabcae5d891d94d9dad3df548fc5288724))

* fix: fix some mode buttons not updating during mode switches ([`d81f005`](https://github.com/kmontag/modeStep/commit/d81f00511bce09472c518ebf737d7aee770d9500))

## v0.0.2 (2024-12-10)

### Chore

* chore: move semantic config to canonical location ([`e4b787d`](https://github.com/kmontag/modeStep/commit/e4b787d0bf1a463e6ada843a2a950c17e45d8304))

* chore: add terraform configuration for modeStep repo ([`870c7ad`](https://github.com/kmontag/modeStep/commit/870c7ad2962e024555228e678a38c37de08e39ae))

* chore: add configuration for semantic PR checks ([`b1df97e`](https://github.com/kmontag/modeStep/commit/b1df97e703d44289819c52a77fa8c2f4a4a23022))

### Documentation

* docs: prettify README ([`b7b3fd2`](https://github.com/kmontag/modeStep/commit/b7b3fd25773eb61011da53aec69e02d97c9594ca))

* docs: remove Live 11 support guarantee

Tests haven&#39;t been run against Live 11 in awhile. ([`d72956b`](https://github.com/kmontag/modeStep/commit/d72956baab4e70740ec507a35078c8399b468c21))

### Fix

* fix: broken type checks as of Live 12.1 (#7)

Live 12.1 switched to python 3.11, which is currently impractical to
decompile. See
https://github.com/gluon/AbletonLive12_MIDIRemoteScripts/issues/2 for
more discussion.

`pycdc` does decompile some basic structural elements of the Live
libraries, but outputs mostly empty function and class definitions.
https://pylingual.io/ seems to work better but isn&#39;t currently possible
to integrate in an automated way.

This PR adds https://github.com/gluon/AbletonLive12_MIDIRemoteScripts
(currently not updated for 12.1 but seems to work fine for our use
cases) as a submodule and sets it up for use with the typechecker. ([`26b748c`](https://github.com/kmontag/modeStep/commit/26b748cc4e72d7fc1aa6c7291cd4c44cc0c5532a))

### Unknown

* Update README.md ([`bd4e310`](https://github.com/kmontag/modeStep/commit/bd4e31099fe1acaafaf2044ed2f4023215bd7ef7))

* Update README.md ([`d9e4638`](https://github.com/kmontag/modeStep/commit/d9e4638bc9b08b3bfd9f48ddb39179a1747171e3))

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
