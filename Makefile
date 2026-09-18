PYTHON ?= python3

.PHONY: install run test collect notify export

install:
	$(PYTHON) -m pip install -r requirements.txt

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
