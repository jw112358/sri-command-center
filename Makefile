# SRI OS Command Center — dev launcher
# Usage:
#   make install   — install all deps (frontend + backend venv)
#   make dev       — start both servers concurrently (port 5173 + 8000)
#   make dev-ui    — frontend only (Vite, port 5173)
#   make dev-api   — backend only (uvicorn, port 8000)
#   make build     — production build of the frontend

.PHONY: install dev dev-ui dev-api build

install:
	cd sri-command-center && npm install
	cd sri-command-center-api && bash setup.sh

dev:
	cd sri-command-center && npm run dev:all

dev-ui:
	cd sri-command-center && npm run dev

dev-api:
	cd sri-command-center-api && \
	  source .venv/bin/activate && \
	  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

build:
	cd sri-command-center && npm run build
