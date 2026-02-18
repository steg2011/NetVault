.PHONY: help init setup test lint run stop logs clean build

help:
	@echo "AGNCF - Air-Gapped Network Config Fortress"
	@echo ""
	@echo "Available targets:"
	@echo "  init          - Initialize environment and generate keys"
	@echo "  setup         - Install dependencies"
	@echo "  test          - Run all tests"
	@echo "  test-scrubber - Run scrubber tests only"
	@echo "  lint          - Check code style"
	@echo "  run           - Start Docker services"
	@echo "  stop          - Stop Docker services"
	@echo "  logs          - View application logs"
	@echo "  clean         - Remove containers and volumes"
	@echo "  build         - Build Docker images"
	@echo "  db-backup     - Backup PostgreSQL database"
	@echo "  db-restore    - Restore PostgreSQL database from backup"

init:
	python3 scripts/init_env.py

setup:
	pip install -r requirements.txt

test:
	pytest tests/ -v

test-scrubber:
	pytest tests/test_scrubber.py -v

lint:
	flake8 app/ tests/ --max-line-length=120
	black --check app/ tests/

format:
	black app/ tests/

run:
	docker compose up -d

stop:
	docker compose down

logs:
	docker compose logs -f app

clean:
	docker compose down -v
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete
	find . -type f -name '.coverage' -delete
	rm -rf htmlcov/

build:
	docker compose build

db-backup:
	@mkdir -p backups
	docker exec agncf-db pg_dump -U agncf_user agncf > backups/db_backup_$(shell date +%Y%m%d_%H%M%S).sql
	@echo "Database backed up to backups/"

db-restore:
	@if [ -z "$(FILE)" ]; then echo "Usage: make db-restore FILE=backups/db_backup_*.sql"; exit 1; fi
	docker exec -i agncf-db psql -U agncf_user agncf < $(FILE)
	@echo "Database restored from $(FILE)"

shell:
	docker exec -it agncf-app /bin/bash

db-shell:
	docker exec -it agncf-db psql -U agncf_user -d agncf

.DEFAULT_GOAL := help
