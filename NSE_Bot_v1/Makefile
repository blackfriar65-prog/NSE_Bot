.PHONY: install api dashboard cli test

install:
	python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt

api:
	PYTHONPATH=src uvicorn nse_bot.api.main:app --reload --port 8000

dashboard:
	PYTHONPATH=src streamlit run dashboard/app.py --server.port 8501

cli:
	PYTHONPATH=src python -m nse_bot.cli

test:
	PYTHONPATH=src pytest -q
