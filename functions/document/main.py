import functions_framework
from dotenv import load_dotenv
from google.cloud import storage, secretmanager
import os
import logging
import json
from pydantic import BaseModel
import time
from datetime import datetime

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def get_secret(secret_name):
    """Fetch secret from Google Secret Manager"""
    client = secretmanager.SecretManagerServiceClient()
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    secret_path = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
    response = client.access_secret_version(request={"name": secret_path})
    return response.payload.data.decode("UTF-8")


load_dotenv()

BUCKET_PROCESSED = os.getenv("BUCKET_PROCESSED")
BUCKET_TRANSCRIPTS = os.getenv("BUCKET_TRANSCRIPTS")
assert BUCKET_TRANSCRIPTS, "BUCKET_TRANSCRIPTS environment variable is not set"
assert BUCKET_PROCESSED, "BUCKET_PROCESSED environment variable is not set"


# Initialize Google Cloud Storage client
storage_client = storage.Client()


# Triggered by a change in a Google Cloud Storage bucket
@functions_framework.cloud_event
def on_document(cloud_event):
    data = cloud_event.data

    event_id = cloud_event["id"]
    event_type = cloud_event["type"]

    bucket_name = data["bucket"]
    file_name = data["name"]

    log.info(f"Processing file: {bucket_name}:{file_name}")
    log.info(f"Event ID: {event_id}, Event type: {event_type}")

    if file_name.endswith(".json"):
        try:
            # Read file from GCS
            bucket = storage_client.bucket(bucket_name)
            blob = bucket.blob(file_name)
            knowledge_str = blob.download_as_string().decode("utf-8")
            result = process_knowledge(knowledge_str)
            log.info(f"Upsert result: {result}")

        except UnicodeDecodeError as e:
            log.error(f"Error decoding file: {e}")
            return

        except Exception as e:
            log.error(f"Error reading file {file_name}: {e}")
            log.error("File not longer exists")
            return
    else:
        log.error(f"File {file_name} is not a knowledge file")

    try:
        # tidy up and move audio file to processed folder
        bucket_processed = storage_client.bucket(BUCKET_PROCESSED)

        # construct filename with datetime in format YYMMDD_HHMMSS
        new_file_name = f"{datetime.now().strftime('%y%m%d_%H%M%S')}_{file_name}"
        bucket.copy_blob(blob, bucket_processed, new_file_name)
        blob.delete()
        log.info(f"File {file_name} moved to {BUCKET_PROCESSED}")

    except Exception as e:
        log.error(f"Error archiving file {file_name}: {e}")
        log.error(f"to bucket {BUCKET_PROCESSED}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="upsert knowledge to Qdrant")
    parser.add_argument("knowledge", help="Knowledge filename to upsert")
    args = parser.parse_args()

    with open(args.knowledge, "r") as f:
        knowledge_str = f.read()

    result = process_knowledge(knowledge_str)
    log.info(f"Upsert result: {result}")
