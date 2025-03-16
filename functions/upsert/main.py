import functions_framework
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, UpdateResult
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
QDRANT_ENDPOINT = os.getenv("QDRANT_ENDPOINT", None)
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", None)
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "test")
VECTOR_SIZE = int(os.getenv("VECTOR_SIZE"))

assert QDRANT_ENDPOINT, "QDRANT_ENDPOINT environment variable is not set"
assert QDRANT_API_KEY, "QDRANT_API_KEY environment variable is not set"
assert VECTOR_SIZE, "VECTOR_SIZE environment variable is not set"

BUCKET_PROCESSED = os.getenv("BUCKET_PROCESSED")
assert BUCKET_PROCESSED, "BUCKET_PROCESSED environment variable is not set"

client = QdrantClient(url=f"{QDRANT_ENDPOINT}:6333", api_key=QDRANT_API_KEY)


# Initialize Google Cloud Storage client
storage_client = storage.Client()


class AnalysisModel(BaseModel):
    phrases: list[str]
    keypoints: list[str]


class KnowledgeModel(BaseModel):
    information: str
    analysis: AnalysisModel
    embeddings: list[float]


def upsert_points(points: list[PointStruct]) -> UpdateResult:
    result = client.upsert(
        collection_name=QDRANT_COLLECTION,
        points=points,
        wait=True,
    )

    return result


def prepare_points(knowledge: KnowledgeModel) -> list[PointStruct]:
    points = [
        PointStruct(
            id=int(time.time() * 1e6),
            vector=knowledge.embeddings,
            payload={"information_shard": knowledge.information},
        ),
    ]
    return points


def get_knowledge(knowledge_str: str) -> KnowledgeModel:
    knowledge_dict = json.loads(knowledge_str)
    return KnowledgeModel(**knowledge_dict)


def process_knowledge(knowledge_str: str) -> UpdateResult:
    knowledge = get_knowledge(knowledge_str)
    points = prepare_points(knowledge)
    result = upsert_points(points)
    return result


# Triggered by a change in a Google Cloud Storage bucket
@functions_framework.cloud_event
def on_knowledge(cloud_event):
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
