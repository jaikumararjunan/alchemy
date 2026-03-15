.PHONY: install dev build up down logs shell test health

install:
	pip install -r requirements.txt

dev:
	python main.py

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

shell:
	docker exec -it emotion-engine-v2 bash

health:
	curl -s http://localhost:8001/api/v2/health | python3 -m json.tool

test-analyze:
	curl -s -X POST http://localhost:8001/api/v2/analyze \
	  -H "Content-Type: application/json" \
	  -d '{"articles":[{"title":"Bitcoin ETF approved by SEC","summary":"The SEC approved the first spot Bitcoin ETF today in a landmark decision for crypto markets.","source":"Reuters"}]}' \
	  | python3 -m json.tool

recent:
	curl -s http://localhost:8001/api/v2/analyses/recent | python3 -m json.tool
