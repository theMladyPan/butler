import functions_framework
import logging
import openai
from google.cloud import storage
import base64
import dotenv
import os

dotenv.load_dotenv()

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Initialize OpenAI client
openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Initialize Google Cloud Storage client
storage_client = storage.Client()

ANALYZER_SYSTEM_PROMPT = """
You are an AI assistant that analyzes uploaded text, files or transcription.
Extract all data and details suitable for embedding creation.
Do not use markdown, just plain text.
If suitable add a quick summary at the end.
"""


def analyze_with_gpt(file_content: str) -> str:
    """Send the file content to GPT-4o for analysis."""
    response = openai_client.responses.create(
        model="gpt-4o",
        instructions=ANALYZER_SYSTEM_PROMPT,
        input=file_content,
    )

    return response.output_text


def transcribe_audio(file_content: bytes) -> str:
    audio_file = open("audio.mp3", "wb")
    audio_file.write(file_content)
    audio_file.close()

    with open("audio.mp3", "rb") as audio_file:
        transcription = openai_client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
        )

    response = openai_client.responses.create(
        model="gpt-4o",
        instructions=ANALYZER_SYSTEM_PROMPT,
        input=transcription.text,
    )

    return response.output_text


def analyze_file(file_content: bytes) -> str:
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
        return response


# Triggered by a change in a Google Cloud Storage bucket
@functions_framework.cloud_event
def hello_gcs(cloud_event):
    data = cloud_event.data

    event_id = cloud_event["id"]
    event_type = cloud_event["type"]

    bucket_name = data["bucket"]
    file_name = data["name"]

    log.info(f"Processing file: {bucket_name}:{file_name}")
    log.info(f"Event ID: {event_id}, Event type: {event_type}")

    try:
        # Read file from GCS
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(file_name)
        try:
            if file_name.endswith(".mp3"):
                file_content = blob.download_as_bytes()
                analysis = transcribe_audio(file_content)

            elif file_name.endswith(".pdf"):
                file_content = blob.download_as_bytes()
                analysis = analyze_file(file_content)

            else:
                # try read plain utf-8 encoded text
                file_content = blob.download_as_text()
                # Send file content to GPT-4o for analysis
                analysis = analyze_with_gpt(file_content)
        except UnicodeDecodeError:
            # if not utf-8 encoded, try read as binary
            file_content = blob.download_as_bytes()
            analysis = analyze_file(file_content)
        except Exception as e:
            log.error(f"Error reading file {file_name}: {e}")
            return

        log.info(f"Analysis: {analysis}")

        # tidy up and remove file
        blob.delete()

    except Exception as e:
        log.error(f"Error processing file {file_name}: {e}")
        return
