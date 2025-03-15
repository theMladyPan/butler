import functions_framework
import logging
import openai
from google.cloud import storage, secretmanager
import dotenv
import os
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


# Initialize OpenAI client
openai_aclient = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)


# Initialize Google Cloud Storage client
storage_client = storage.Client()


AUDIO_FOLDER = os.getenv("AUDIO_FOLDER", "audio")
TRANSCRIPT_FOLDER = os.getenv("TRANSCRIPT_FOLDER", "transcript")
PROCESSED_FOLDER = os.getenv("PROCESSED_FOLDER", "processed")


async def transcribe_audio(file_content: bytes) -> list[str]:
    audio_file = open("audio.mp3", "wb")
    audio_file.write(file_content)
    audio_file.close()

    with open("audio.mp3", "rb") as audio_file:
        transcription = await openai_aclient.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
        )

    return transcription.text


async def _main():
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", help="Transcribe audio file")
    args = parser.parse_args()

    if args.audio:
        with open(args.audio, "rb") as audio_file:
            transcription = await transcribe_audio(audio_file.read())

        with open(
            f"{'.'.join(args.audio.split('.')[:-1])}_transcript.txt",
            "w",
        ) as f:
            f.write(transcription)
        print(transcription)

    else:
        log.error("No arguments provided")
        parser.print_help()
        exit(1)


# Triggered by a change in a Google Cloud Storage bucket
@functions_framework.cloud_event
async def on_new_audio(cloud_event):
    data = cloud_event.data

    event_id = cloud_event["id"]
    event_type = cloud_event["type"]

    bucket_name = data["bucket"]
    file_name = data["name"]

    log.info(f"Processing file: {bucket_name}:{file_name}")
    log.info(f"Event ID: {event_id}, Event type: {event_type}")

    if file_name.endswith(".mp3"):
        try:
            # Read file from GCS
            bucket = storage_client.bucket(bucket_name)
            blob = bucket.blob(file_name)
            try:
                transcription = await transcribe_audio(blob.download_as_bytes())
                # save transcription to new file
                new_blob = bucket.blob(f"{TRANSCRIPT_FOLDER}/{file_name}.txt")
                new_blob.upload_from_string(transcription)

            except Exception as e:
                log.error(f"Error reading file {file_name}: {e}")
                return

            # tidy up and move audio file to processed folder
            processed_blob = bucket.blob(f"{PROCESSED_FOLDER}/{file_name}")
            processed_blob.upload_from_filename(file_name)
            blob.delete()

        except Exception as e:
            log.error(f"Error processing file {file_name}: {e}")
            return
    else:
        log.error(f"File {file_name} is not an audio file")
        return


if __name__ == "__main__":
    import argparse
    import asyncio

    asyncio.run(_main())
