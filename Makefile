REGION := europe-central2
PROJECT_ID := butler-453810

run:
	if [ ! -d ".venv" ]; then \
		make-venv; \
	fi
	. ./.venv/bin/activate && uvicorn app.main:app --reload

make-venv:
	# if .venv directory does not exist, create it
	if [ ! -d ".venv" ]; then \
		python3 -m venv .venv; \
	fi
	# install dependencies
	. ./.venv/bin/activate && pip install -r requirements.txt

decrypt-env:
	@echo "Decrypting environment variables..."
	@gpg --quiet --batch --yes --decrypt --output .env .env.gpg

encrypt-env:
	@echo "Encrypting environment variables..."
	@gpg --quiet --batch --yes --symmetric --cipher-algo AES256 --output .env.gpg .env

google-auth:
	gcloud auth login
	gcloud config set project ${PROJECT_ID}
	gcloud auth application-default login

google-init:
	gcloud services enable artifactregistry.googleapis.com
	gcloud services enable run.googleapis.com
	gcloud services enable cloudbuild.googleapis.com
	gcloud services enable logging.googleapis.com
	gcloud services enable eventarc.googleapis.com
	gcloud config set run/region europe-central2

google-deploy-transcript:
	bash ./script/deploy_transcript.sh


build-on-document:
	docker build --pull --rm -f 'functions/document/Dockerfile' \
		-t 'butler-on-document:latest' 'functions/document'
	docker image push docker.io/themladypan/butler-on-document:latest

deploy-on-document:
	gcloud run deploy on-document \
		--image docker.io/themladypan/butler-on-document:latest \
		--platform managed \
		--region europe-central2 \
		--allow-unauthenticated

trigger-on-document:
	gcloud eventarc triggers create trigger-on-document \
		--location=us-central1 \
		--service-account=347891831748-compute@developer.gserviceaccount.com \
		--destination-run-service=on-document \
		--destination-run-region=europe-central2 \
		--destination-run-path="/" \
		--event-filters="bucket=butler-documents" \
		--event-filters="type=google.cloud.storage.object.v1.finalized"