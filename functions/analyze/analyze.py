import functions_framework
import logging
import openai
from google.cloud import storage, secretmanager
import dotenv
import os
from datetime import datetime
from pydantic import BaseModel
import json

dotenv.load_dotenv()

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def get_secret(secret_name):
    """Fetch secret from Google Secret Manager"""
    client = secretmanager.SecretManagerServiceClient()
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    secret_path = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
    response = client.access_secret_version(request={"name": secret_path})
    return response.payload.data.decode("UTF-8")


# Replace dotenv with Secret Manager
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", False)
if not OPENAI_API_KEY:
    os.environ["OPENAI_API_KEY"] = get_secret("OPENAI_API_KEY")
assert OPENAI_API_KEY, "OPENAI_API_KEY environment variable is not set"


MAX_TEXT_LENGTH = int(os.getenv("MAX_TEXT_LENGTH", 4096))
OVERLAP = int(os.getenv("OVERLAP", 1024))
VECTOR_SIZE = int(os.getenv("VECTOR_SIZE"))
assert VECTOR_SIZE, "VECTOR_SIZE environment variable is not set"

BUCKET_KNOWLEDGE = os.getenv("BUCKET_KNOWLEDGE")
BUCKET_PROCESSED = os.getenv("BUCKET_PROCESSED")
assert BUCKET_KNOWLEDGE, "BUCKET_KNOWLEDGE environment variable is not set"
assert BUCKET_PROCESSED, "BUCKET_PROCESSED environment variable is not set"


ANALYZER_SYSTEM_PROMPT = f"""
You are an AI assistant that analyzes uploaded text, files or transcription.
Extract all data and details suitable for embedding creation and integration
into vector database as a knowledge base. The knowledge base should be
searchable and retrievable by the user. The knowledge base should contain
all relevant information, analysis, and embeddings for the uploaded content.
Phrases should contain frequently asked question regarding this chunk of information.
Keypoints should contain extracted, factual data from the text. Numbers, dates, names, laws, paragraphs, etc.
Respond in analyzed texts original language.
Current date and time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""

# Initialize OpenAI client
openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)


# Initialize Google Cloud Storage client
storage_client = storage.Client()


class AnalysisModel(BaseModel):
    phrases: list[str]
    keypoints: list[str]


class KnowledgeModel(BaseModel):
    information: str
    analysis: AnalysisModel
    embeddings: list[float]


def chunk_text(text: str) -> list[str]:
    if len(text) < MAX_TEXT_LENGTH:
        return [text]
    else:
        return [text[i : i + MAX_TEXT_LENGTH + OVERLAP] for i in range(0, len(text), MAX_TEXT_LENGTH)]


def analyze_with_gpt(transcription: str) -> AnalysisModel:
    assert transcription, "Transcription cannot be empty"
    assert isinstance(transcription, str), "Transcription must be a string"

    schema = AnalysisModel.model_json_schema()
    schema["additionalProperties"] = False

    response = openai_client.responses.create(
        model="gpt-4o-mini",
        instructions=ANALYZER_SYSTEM_PROMPT,
        input=transcription,
        text={
            "format": {
                "type": "json_schema",
                "name": "probable_questions",
                "schema": schema,
                "strict": True,
            }
        },
    )
    structured_response = json.loads(response.output_text)
    return AnalysisModel(**structured_response)


def create_embedding(text: str) -> dict:
    response = openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=text,
        dimensions=VECTOR_SIZE,
    )

    return response.data[0].embedding


def create_knowledge(information: str) -> KnowledgeModel:
    analysis = analyze_with_gpt(information)
    analysis_text = "\n".join(analysis.phrases) + "\n".join(analysis.keypoints)

    embedding = create_embedding(analysis_text)

    knowledge = KnowledgeModel(
        information=information,
        analysis=analysis,
        embeddings=embedding,
    )

    return knowledge


def _main():
    parser = argparse.ArgumentParser()
    parser.add_argument("transcription", help="Transcription to analyze")
    args = parser.parse_args()

    if args.transcription:
        with open(args.transcription, "r") as f:
            transcription = f.read()

        knowledge = create_knowledge(transcription)

        log.info(f"Knowledge analysis: {knowledge.analysis}")
        with open(
            f"{args.transcription.rstrip('.txt')}_knowledge.json",
            "wb",
        ) as f:
            f.write(knowledge.model_dump_json().encode("utf-8"))

    else:
        log.error("No arguments provided")
        parser.print_help()
        exit(1)


# Triggered by a change in a Google Cloud Storage bucket
@functions_framework.cloud_event
def on_new_transcript(cloud_event):
    data = cloud_event.data

    event_id = cloud_event["id"]
    event_type = cloud_event["type"]

    bucket_name = data["bucket"]
    file_name = data["name"]

    log.info(f"Processing file: {bucket_name}:{file_name}")
    log.info(f"Event ID: {event_id}, Event type: {event_type}")

    if file_name.endswith(".txt"):
        try:
            # Read file from GCS
            bucket = storage_client.bucket(bucket_name)
            blob = bucket.blob(file_name)

            knowledge = create_knowledge(blob.download_as_string().decode("utf-8"))

            knowledge_file_name = f"{file_name.rstrip('.txt')}_knowledge.json"
            log.info(f"Saving knowledge analysis to {BUCKET_KNOWLEDGE}:{knowledge_file_name}")

            bucket_knowledge = storage_client.bucket(BUCKET_KNOWLEDGE)
            knowledge_blob = bucket_knowledge.blob(knowledge_file_name)

            dumps = knowledge.model_dump_json()
            knowledge_blob.upload_from_string(dumps)

        except UnicodeDecodeError as e:
            log.error(f"Error decoding file: {e}")
            return

        except Exception as e:
            log.error(f"Error processing file: {e}")
            return

    else:
        log.error(f"File {file_name} is not a transcription")

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

    return


if __name__ == "__main__":
    import argparse

    _main()
