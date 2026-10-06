# Local development shortcuts (PROMPT.md §32). Same commands as the root package.json scripts
# (`npm run <name>`), for machines without make. Docker Desktop must be running.
.PHONY: up down logs migrate makemigrations seed test test-backend test-frontend lint lint-backend lint-frontend dev e2e ci

up:            ## PostgreSQL + Azurite + Django (migrates and seeds on start)
	docker compose up -d --build
down:
	docker compose down
logs:
	docker compose logs -f backend
migrate:
	docker compose exec backend python manage.py migrate
makemigrations:
	docker compose exec backend python manage.py makemigrations
seed:          ## FY 2026 schedule, admin, two doctors with applications (idempotent)
	docker compose exec backend python manage.py seed_dev_data
test-backend:
	docker compose exec backend pytest -q --ds=config.settings.test
test-frontend:
	npm --prefix frontend test
test: test-backend test-frontend
lint-backend:
	docker compose exec backend ruff check .
	docker compose exec backend ruff format --check .
lint-frontend:
	npm --prefix frontend run lint
	npm --prefix frontend run typecheck
	npm --prefix frontend run rtl:check
lint: lint-backend lint-frontend
dev:           ## Vite on http://localhost:5173 (proxies /api to Django on :8000)
	npm --prefix frontend run dev
e2e:           ## Playwright against the running stack
	npm --prefix frontend run test:e2e
ci: lint test
	npm --prefix frontend run build
