PYTHON ?= $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)

.PHONY: setup check run test collect notify export

install:
	$(PYTHON) -m pip install -r requirements.txt

setup:
	python3 -m venv .venv
	$(PYTHON) -m pip install -r requirements.txt
	@test -f .env || cp .env.example .env
	@echo "Ready. Edit .env, then: make check && make run"

check:
	$(PYTHON) -m scripts.check_setup

run:
	$(PYTHON) run.py

test:
	$(PYTHON) -m unittest discover -s tests

collect:
	$(PYTHON) -m scripts.collect

notify:
	$(PYTHON) -m scripts.collect --notify

export:
	$(PYTHON) -m scripts.export_static --out site
