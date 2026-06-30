-include .env

# Hardcoded variables
VERSION := latest
PUBLISHEDIMAGE := informatievlaanderen/triple-store
BASE_IMAGE := triple-store-base
APP_IMAGE := triple-store-informatievlaanderen

build-base:
	docker build -f Dockerfile.base -t $(BASE_IMAGE):$(VERSION) .

# Requires build-base to be run first
build:
	docker build -f Dockerfile.build --build-arg "VERSION=$(VERSION)" -t $(APP_IMAGE):$(VERSION) .

# Runs the container exactly like your docker-compose file did
run:
	docker run -d --name $(APP_IMAGE) \
		--restart unless-stopped \
		-p 8000:8000 -p 8888:8888 \
		-v $(PWD)/qlever:/app/qlever \
		-v $(PWD)/logs:/app/logs \
		-v $(PWD)/validation_data:/app/validation_data \
		-v $(PWD)/data-vlaanderen-scraper-output:/app/data-vlaanderen-scraper-output \
		-e TZ=Europe/Brussels \
		$(APP_IMAGE):$(VERSION)