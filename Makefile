.PHONY: up down build logs test lint

up:
	docker compose up -d

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f backend

test:
	cd backend && pytest tests/ -v

lint:
	cd backend && ruff check app/

dev-backend:
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-frontend:
	cd frontend && npm run dev

dev-worker:
	cd backend && celery -A app.workers.celery_app worker --loglevel=info

setup:
	cp -n .env.example .env || true
	cd backend && pip install -r requirements.txt
	cd frontend && npm install
