.PHONY: setup test demo ingest run report data-report clean lint

PY ?= python3

setup:
	$(PY) -m pip install -e ".[dev]"

test:
	$(PY) -m pytest tests -q

lint:
	$(PY) -m ruff check src tests

# Full offline run against generated EDGAR fixtures. No network, no vendor data.
demo:
	$(PY) -m crowdflow.cli demo -v

# Real EDGAR. Requires CROWDFLOW_USER_AGENT to be a real contact address.
ingest:
	$(PY) -m crowdflow.cli ingest -v

run:
	$(PY) -m crowdflow.cli run --prices $(PRICES) --crosswalk $(CROSSWALK) -v

report:
	$(PY) -m crowdflow.cli report --out memo/crowdflow_memo.pdf

# Audit of the ingest + curate layers: what was dropped, repaired, deduplicated,
# and what the point-in-time store actually knew on any given day.
data-report:
	$(PY) scripts/data_report.py --out docs/DATA.md $(ARGS)

clean:
	rm -rf data/10_parsed data/20_curated data/30_features data/40_results
