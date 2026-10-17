.PHONY: install run test eval mcp
install:
	pip install -r requirements.txt
run:
	./run.sh
test:
	pytest -q
eval:
	python evals/run_eval.py
mcp:
	python -m app.mcp_server
