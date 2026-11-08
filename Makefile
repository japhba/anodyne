PYTHON ?= build/venv/bin/python
VENV ?= $(patsubst %/bin/python,%,$(PYTHON))
export PATH := $(abspath $(VENV))/bin:$(PATH)
FONTS ?= fonts
MASTERS ?= build/masters

.PHONY: setup qa-setup fetch prepare build release sources package edit check qa instance proof specimen

setup: $(VENV)/.installed

$(VENV)/.installed: requirements.lock
	test -x $(PYTHON) || python3 -m venv $(VENV)
	$(PYTHON) -m ensurepip --upgrade
	$(PYTHON) -m pip install -r requirements.lock
	touch $@

qa-setup: setup
	$(PYTHON) -m pip install -r requirements-qa-build.lock
	$(PYTHON) -m pip install --no-build-isolation opentype-sanitizer==9.2.0
	$(PYTHON) -m pip install -r requirements-qa.lock

fetch:
	python3 sources/fetch_sources.py

prepare: setup
	PYTHONHASHSEED=0 $(PYTHON) sources/pipeline.py prepare --masters $(MASTERS)

build: setup
	PYTHONHASHSEED=0 $(PYTHON) sources/pipeline.py build --masters $(MASTERS)

# Updates the checkout's distributed files; does not publish, tag or push.
release: setup
	PYTHONHASHSEED=0 $(PYTHON) sources/pipeline.py release --masters $(MASTERS)

sources: setup
	$(PYTHON) sources/archive.py --masters $(MASTERS)

package: build
	$(PYTHON) sources/archive.py --binary

edit: prepare
	$(PYTHON) sources/masters.py unpack $(MASTERS)/Roman/Anodyne-Roman.designspace $(MASTERS)/Italic/Anodyne-Italic.designspace

check: setup
	ANODYNE_FONTS=$(FONTS) $(PYTHON) -m unittest discover -s tests
	$(PYTHON) sources/check.py --fonts $(FONTS) --sanitize --json build/qa.json

qa: check qa-setup
	$(PYTHON) sources/qa.py --fonts $(FONTS)

# AXES='--weight 550 --width 75 --grade 50'; add --italic if wanted.
instance: setup
	$(PYTHON) sources/instance.py $(AXES)

proof: setup
	$(PYTHON) sources/proof.py --fonts $(FONTS)

specimen: qa-setup
	$(PYTHON) sources/render_text_specimen.py --fonts $(FONTS)
	$(PYTHON) sources/render_specimen.py --fonts $(FONTS)
	$(PYTHON) sources/render_greek_specimen.py --fonts $(FONTS)
