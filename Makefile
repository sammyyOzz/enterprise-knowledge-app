run:
	uv sync
	docker compose up --build

stop:
	docker compose down

clean-notebook-outputs:
	jupyter nbconvert --clear-output --inplace notebooks/*/*.ipynb