run:
	uv sync
	docker compose up --build

stop:
	docker compose down

clean-notebook-outputs:
	jupyter nbconvert --clear-output --inplace notebooks/*/*.ipynb

verify-migrations-to-head-sql:
	docker compose exec api alembic -c /app/apps/api/src/alembic.ini upgrade head --sql

migrate-to-head:
	docker compose exec api alembic -c /app/apps/api/src/alembic.ini upgrade head

test:
	uv run --package api pytest apps/api/tests