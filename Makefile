.PHONY: setup train test api image up load drift down

export PYTHONPATH := src:.

setup:          ## Python environment
	python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt

train:          ## Download the real dataset and train the model
	python -m energy.train

test: train     ## Unit and API tests
	pytest -q

api: train      ## Run the API locally on port 8000
	uvicorn service.app:app --port 8000

image:          ## Build the container (trains inside the build) and push it to the local registry
	bash scripts/start_registry.sh
	docker build -t localhost:5001/energy-api:local .
	docker push localhost:5001/energy-api:local

up: image       ## Create the kind cluster and deploy everything with Terraform
	cd infra/terraform && terraform init && terraform apply

load:           ## Replay real May readings at 20 requests per second for 5 minutes
	python scripts/load_test.py --period test --rps 20 --seconds 300

drift:          ## Simulate a heatwave (+6 C) to trip the critical drift alert
	python scripts/load_test.py --period test --rps 20 --seconds 900 --shift-temp 6

down:           ## Delete the cluster and the local registry
	cd infra/terraform && terraform destroy
	docker rm -f kind-registry
