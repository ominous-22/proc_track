SESSION ?= 2025R1

.PHONY: fetch replay perturb derive check clean

fetch:    ## download a session to cache/  (make fetch SESSION=2023R1)
	python scripts/fetch_session.py $(SESSION)

replay:   ## coverage + ranked halts + uncovered fragments
	python scripts/bulk_replay.py $(SESSION)

perturb:  ## false-accept measurement
	python scripts/perturbation_test.py $(SESSION)

derive:   ## learn per-chamber transition graphs from the corpus
	python scripts/derive_chamber_flows.py $(SESSION)

check:    ## the gate — must exit 0 before any commit
	python scripts/check.py $(SESSION)

clean:
	rm -rf cache/*.json __pycache__ scripts/__pycache__
