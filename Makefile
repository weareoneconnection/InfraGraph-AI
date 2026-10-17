run:
	./run.sh

test:
	PYTHONPATH=. pytest -q

eval:
	PYTHONPATH=. python evals/run_eval.py
