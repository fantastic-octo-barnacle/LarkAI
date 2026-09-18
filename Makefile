PYTHON ?= python3

.PHONY: install run test collect export

install:
	$(PYTHON) -m pip install -r requirements.txt

run:
	$(PYTHON) run.py

test:
	$(PYTHON) -m unittest discover -s tests

collect:
	$(PYTHON) -m scripts.collect

export:
	$(PYTHON) -m scripts.export_static --out site
