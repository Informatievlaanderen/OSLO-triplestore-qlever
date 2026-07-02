-include .env

VERSION := $(shell cat VERSION)
PUBLISHEDIMAGE := $(shell cat PUBLISHED)
BASE_IMAGE := qlever-triple-store-base
APP_IMAGE := qlever-triple-store

build-base:
	docker build -f Dockerfile.base -t $(BASE_IMAGE):$(VERSION) .

build-base-linux:
	docker build --platform=linux/amd64 -f Dockerfile.base -t $(BASE_IMAGE):$(VERSION) .

# Requires build-base to be run first
build:
	docker build -f Dockerfile.build --build-arg "VERSION=$(VERSION)" -t $(APP_IMAGE):$(VERSION) .

# Requires build-base-linux to be run first
build-linux:
	docker build --platform=linux/amd64 -f Dockerfile.build --build-arg "VERSION=$(VERSION)" -t $(APP_IMAGE):$(VERSION) .

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

stop:
	docker stop $(APP_IMAGE)

publish:
	docker tag ${APP_IMAGE}:${VERSION} ${PUBLISHEDIMAGE}:${VERSION}
	docker push ${PUBLISHEDIMAGE}:${VERSION}
