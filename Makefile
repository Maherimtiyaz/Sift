.PHONY: up down logs reset test typecheck api-dev web-dev

up:            ## build and start everything (web on :3000, API on :8000)
	docker compose up --build -d

down:          ## stop everything (data is kept)
	docker compose down

logs:          ## follow API and web logs
	docker compose logs -f api web

reset:         ## stop everything and DELETE the database
	docker compose down -v

test:          ## run the API tests against real Postgres and Redis (needs Docker)
	docker compose up -d --wait db redis
	docker compose exec -T db psql -U sift -tc "SELECT 1 FROM pg_database WHERE datname='sift_test'" | grep -q 1 || docker compose exec -T db createdb -U sift sift_test
	cd apps/api && pytest -q

typecheck:     ## typecheck the web app
	cd apps/web && npm run typecheck

api-dev:       ## run the API with auto-reload (needs the venv and env vars, see README)
	cd apps/api && alembic upgrade head && uvicorn app.main:app --reload --port 8000

web-dev:       ## run the web app with hot reload (needs apps/web/.env.local)
	cd apps/web && npm run dev
