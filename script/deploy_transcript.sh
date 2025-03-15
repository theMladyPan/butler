#!/bin/bash

# Load environment variables from .env file
set -a  # Automatically export variables
source .env
set +a  # Stop automatically exporting variables
BASE_IMAGE=python312

echo "Using loaded environment variables:"
echo "OPENAI_API_KEY: ${OPENAI_API_KEY}"
echo "AUDIO_FOLDER: ${AUDIO_FOLDER}"
echo "TRANSCRIPT_FOLDER: ${TRANSCRIPT_FOLDER}"
echo "PROCESSED_FOLDER: ${PROCESSED_FOLDER}"
echo "BASE_IMAGE: ${BASE_IMAGE}"

gcloud run deploy on-new-audio \
    --source functions/ \
    --function on_new_audio \
    --base-image ${BASE_IMAGE} \
    --set-env-vars OPENAI_API_KEY=${OPENAI_API_KEY} \
    --set-env-vars AUDIO_FOLDER=${AUDIO_FOLDER} \
    --set-env-vars TRANSCRIPT_FOLDER=${TRANSCRIPT_FOLDER} \
    --set-env-vars PROCESSED_FOLDER=${PROCESSED_FOLDER}
