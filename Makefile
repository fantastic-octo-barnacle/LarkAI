.PHONY: setup run dev build test check collect
setup:
	npm ci --prefix frontend
	cargo fetch --locked
	@test -f .env || cp .env.example .env

# Serve the production React build and JSON API on one origin.
run: build
	cargo run --locked -p larkai

# Run in two terminals: make dev and cargo run -p larkai
# Vite proxies API and authorization paths to localhost:8000.
dev:
	npm run dev --prefix frontend

build:
	npm run build --prefix frontend

check:
	cargo fmt --all --check
	cargo clippy --workspace --all-targets --locked -- -D warnings
	npm run build --prefix frontend

test:
	cargo test --workspace --locked
	npm test --prefix frontend
	python3 -m unittest discover -s tests -v

collect:
	cargo run --locked -p larkai -- collect
