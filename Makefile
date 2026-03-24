.PHONY: start stop test lint clean seed

start:
	cp -n .env.example .env 2>/dev/null || true
	@echo "Start services locally:"
	@echo "  1) Run Redis"
	@echo "  2) Run API from backend/"
	@echo "  3) Run worker from backend/"
	@echo "  4) Run streamlit from frontend/"
	@echo ""
	@echo "  Local endpoints:"
	@echo "  Streamlit UI  → http://localhost:8501"
	@echo "  API (Swagger) → http://localhost:8000/docs"
	@echo "  Flower        → http://localhost:5555"
	@echo ""

stop:
	@echo "Stop local processes from their terminals."

logs:
	@echo "Logs are available in each local terminal."

test:
	cd backend && python -m pytest tests/ -v --tb=short

lint:
	cd backend && python -m ruff check .
	cd backend && python -m mypy . --ignore-missing-imports

clean:
	rm -rf data/vector_store data/uploads

seed:
	@echo "Knowledge base is auto-seeded on API startup."
	curl -s http://localhost:8000/health | python3 -m json.tool
