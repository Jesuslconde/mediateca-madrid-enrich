SHELL := /bin/bash

q ?= cine
pages ?= 1
limit ?= 20

.PHONY: help up down build logs ps init migrate harvest index worker-logs worker-shell test lint fmt shell psql clean

help: ## Mostrar la ayuda
	@grep -E '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

up: ## Levantar PostgreSQL, Meilisearch y worker
	docker compose up -d --build

down: ## Detener los servicios
	docker compose down

build: ## Construir la imagen
	docker compose build

logs: ## Ver logs en vivo
	docker compose logs -f --tail=100

worker-logs: ## Ver logs del worker en vivo
	docker compose logs -f --tail=100 worker

worker-shell: ## Abrir shell en el worker
	docker compose exec worker bash

ps: ## Estado de los servicios
	docker compose ps

init: ## Crear tablas e indice de busqueda
	docker compose run --rm worker mediateca init-db

migrate: ## Aplicar migraciones idempotentes
	docker compose exec -T db psql -U $${POSTGRES_USER:-mediateca} -d $${POSTGRES_DB:-mediateca} < scripts/migrate_disponibilidad.sql
	docker compose exec -T db psql -U $${POSTGRES_USER:-mediateca} -d $${POSTGRES_DB:-mediateca} < scripts/migrate_ingesta.sql

harvest: ## Recolectar del OPAC: make harvest q=cine pages=2 limit=20
	docker compose run --rm worker mediateca harvest --query "$(q)" --max-pages $(pages) $(if $(limit),--limit $(limit),)

index: ## Indexar todas las ediciones
	docker compose run --rm worker mediateca index

test: ## Ejecutar pytest
	docker compose run --rm worker pytest -q

lint: ## Ejecutar ruff
	docker compose run --rm worker ruff check src tests

fmt: ## Formatear con ruff
	docker compose run --rm worker ruff format src tests

shell: ## Abrir shell en el worker
	docker compose exec worker bash

psql: ## Abrir psql
	docker compose exec db psql -U $${POSTGRES_USER:-mediateca} -d $${POSTGRES_DB:-mediateca}

clean: ## Detener y borrar volumenes (destructivo)
	docker compose down -v
