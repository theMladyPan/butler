import functions_framework
import logging
import openai
from google.cloud import storage, secretmanager
import dotenv
import os

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
openai_aclient = openai.OpenAI(api_key=OPENAI_API_KEY)


# Initialize Google Cloud Storage client
storage_client = storage.Client()


def transcribe_audio(file_content: bytes) -> list[str]:
    audio_file = open("audio.mp3", "wb")
    audio_file.write(file_content)
    audio_file.close()

    with open("audio.mp3", "rb") as audio_file:
        transcription = openai_aclient.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
        )

    return transcription.text


def _main():
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", help="Transcribe audio file")
    args = parser.parse_args()

    if args.audio:
        with open(args.audio, "rb") as audio_file:
            transcription = transcribe_audio(audio_file.read())

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
def on_new_audio(cloud_event):
    data = cloud_event.data

    event_id = cloud_event["id"]
    event_type = cloud_event["type"]

    bucket_name = data["bucket"]
    file_name = data["name"]

    log.info(f"Processing file: {bucket_name}:{file_name}")
    log.info(f"Event ID: {event_id}, Event type: {event_type}")

    BUCKET_AUDIO = os.getenv("BUCKET_AUDIO")
    BUCKET_TRANSCRIPTS = os.getenv("BUCKET_TRANSCRIPTS")
    BUCKET_PROCESSED = os.getenv("BUCKET_PROCESSED")
    assert BUCKET_AUDIO, "BUCKET_AUDIO environment variable is not set"
    assert BUCKET_TRANSCRIPTS, "BUCKET_TRANSCRIPTS environment variable is not set"
    assert BUCKET_PROCESSED, "BUCKET_PROCESSED environment variable is not set"

    if file_name.endswith(".mp3"):
        # Read file from GCS
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(file_name)
        audio_bytes = blob.download_as_bytes()
        try:
            transcription = transcribe_audio(audio_bytes)
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

    else:
        log.warning(f"File {file_name} is not an audio file")

        try:
            # tidy up and move audio file to processed folder
            bucket_processed = storage_client.bucket(BUCKET_PROCESSED)
            bucket.copy_blob(blob, bucket_processed, file_name)
            blob.delete()

        except Exception as e:
            log.error(f"Error archiving file {file_name}: {e}")
            log.error(f"to bucket {BUCKET_PROCESSED}")

        return


if __name__ == "__main__":
    import argparse

    _main()
