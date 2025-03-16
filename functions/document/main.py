import functions_framework
from dotenv import load_dotenv
from google.cloud import storage, secretmanager
import os
import logging
import json
from pydantic import BaseModel
import time
import base64
from datetime import datetime
import openai

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


# Replace dotenv with Secret Manager
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", False)
if not OPENAI_API_KEY:
    os.environ["OPENAI_API_KEY"] = get_secret("OPENAI_API_KEY")
assert OPENAI_API_KEY, "OPENAI_API_KEY environment variable is not set"


# Initialize OpenAI client
openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)


# Initialize Google Cloud Storage client
storage_client = storage.Client()


ANALYZER_SYSTEM_PROMPT = f"""
You are an AI assistant that analyzes documents.
Extract all data and details suitable for embedding creation and integration
into vector database as a knowledge base.
Write a short summary what is the document about page by page.
Extract all the key points and details.
Respond in analyzed texts original language.
Do not use markdown or HTML, just plain text.
Current date and time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""


def transcribe_pdf(file_content: bytes) -> str:
    base64_string = base64.b64encode(file_content).decode("utf-8")

    response = openai_client.responses.create(
        model="gpt-4o",
        input=[
            {"role": "system", "content": ANALYZER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_file",
                        "filename": "file.pdf",
                        "file_data": f"data:application/pdf;base64,{base64_string}",
                    },
                ],
            },
        ],
    )
    try:
        return response.output_text

    except Exception as e:
        log.error(f"Error analyzing file: {e}")
        return str(response)


def _main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", help="Transcribe audio file")
    args = parser.parse_args()

    with open(args.pdf, "rb") as audio_file:
        transcription = transcribe_pdf(audio_file.read())

    with open(
        f"{args.pdf}_transcript.txt",
        "w",
    ) as f:
        f.write(transcription)
    print(transcription)


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

    BUCKET_TRANSCRIPTS = os.getenv("BUCKET_TRANSCRIPTS")
    BUCKET_PROCESSED = os.getenv("BUCKET_PROCESSED")
    assert BUCKET_TRANSCRIPTS, "BUCKET_TRANSCRIPTS environment variable is not set"
    assert BUCKET_PROCESSED, "BUCKET_PROCESSED environment variable is not set"

    if file_name.endswith(".pdf"):
        try:
            # Read file from GCS
            bucket = storage_client.bucket(bucket_name)
            blob = bucket.blob(file_name)
            pdf_bytes = blob.download_as_bytes()
        except Exception as e:
            log.error(f"Error reading file {file_name}: {e}")
            log.error("File not longer exists")
            return

        try:
            transcription = transcribe_pdf(pdf_bytes)
            log.info(f"Transcription: {transcription[:100]}...")

        except Exception as e:
            log.error(f"Error transcribing file {file_name}: {e}")
            return

        try:
            bucket_transcripts = storage_client.bucket(BUCKET_TRANSCRIPTS)
            # save transcription to new file
            new_blob = bucket_transcripts.blob(f"{file_name}.txt")
            new_blob.upload_from_string(transcription)
        except Exception as e:
            log.error(f"Error saving transcription to bucket {BUCKET_TRANSCRIPTS}: {e}")
            log.error(f"{file_name}: {e}")
            return

        log.info(f"Transcription saved to {BUCKET_TRANSCRIPTS}/{file_name}.txt")

    else:
        log.warning(f"File {file_name} is not an audio file")

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
