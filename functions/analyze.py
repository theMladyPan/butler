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


# Initialize Google Cloud Storage client
storage_client = storage.Client()

ANALYZER_SYSTEM_PROMPT = """
You are an AI assistant that analyzes uploaded text, files or transcription.
Extract all data and details suitable for embedding creation and integration
into vector database as a knowledge base.
Do not use markdown, just plain text.
Output: 10 example phrases in original language that can be used to search for this text,
do not include the original text in the examples, do not number the examples.
"""

MAX_TEXT_LENGTH = 4096
OVERLAP = 1024

AUDIO_FOLDER = os.getenv("AUDIO_FOLDER", "audio")
TRANSCRIPT_FOLDER = os.getenv("TRANSCRIPT_FOLDER", "transcript")
PROCESSED_FOLDER = os.getenv("PROCESSED_FOLDER", "processed")


class AnalysisModel(BaseModel):
    phrases: list[str]


class KnowledgeModel(BaseModel):
    information: str
    analysis: AnalysisModel
    embeddings: list[float]


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


def chunk_text(text: str) -> list[str]:
    if len(text) < MAX_TEXT_LENGTH:
        return [text]
    else:
        return [text[i : i + MAX_TEXT_LENGTH + OVERLAP] for i in range(0, len(text), MAX_TEXT_LENGTH)]


async def analyze_with_gpt(transcription: str) -> AnalysisModel:
    assert transcription, "Transcription cannot be empty"
    assert isinstance(transcription, str), "Transcription must be a string"

    schema = AnalysisModel.model_json_schema()
    schema["additionalProperties"] = False

    response = await openai_aclient.responses.create(
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


async def create_embedding(text: str) -> dict:
    VECTOR_SIZE = int(os.getenv("VECTOR_SIZE"))
    assert VECTOR_SIZE, "VECTOR_SIZE environment variable is not set"

    response = await openai_aclient.embeddings.create(
        model="text-embedding-3-small",
        input=text,
        dimensions=VECTOR_SIZE,
    )

    return response.data[0].embedding


async def complete_audio_analysis(audio: bytes, file_name: str) -> KnowledgeModel:
    transcription = await transcribe_audio(audio)
    transcription = chunk_text(transcription)

    for enum, chunk in enumerate(transcription):
        chunk_analysis: AnalysisModel = await analyze_with_gpt(chunk)
        chunk_embedding = await create_embedding(chunk)
        knowledge = KnowledgeModel(
            information=chunk,
            analysis=chunk_analysis,
            embeddings=chunk_embedding,
        )
        with open(
            f"{'.'.join(file_name.split('.')[:-1])}_knowledge_{enum}.json",
            "w",
        ) as f:
            f.write(knowledge.model_dump_json())


async def _main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-a", "--audio", help="Transcribe audio file")
    parser.add_argument("-t", "--transcription", help="Transcription to analyze")
    parser.add_argument("-e", "--embedding", help="Create embedding for text")
    parser.add_argument("-c", "--complete", help="Complete audio analysis process")
    args = parser.parse_args()

    if args.audio:
        with open(args.audio, "rb") as audio_file:
            transcription = await transcribe_audio(audio_file.read())

        transcription = chunk_text(transcription)
        for enum, text in enumerate(transcription):
            with open(
                f"{'.'.join(args.audio.split('.')[:-1])}_transcript_{enum}.txt",
                "w",
            ) as f:
                f.write(text)
        print(transcription)

    elif args.transcription:
        with open(args.transcription, "r") as f:
            transcription = f.read()
        analysis = await analyze_with_gpt(transcription)
        with open(
            f"{args.transcription.split('_transcript')[0]}_analysis.txt",
            "w",
        ) as f:
            f.write("\n".join(analysis.phrases))
        print(analysis)

    elif args.embedding:
        with open(args.embedding, "r") as f:
            text = f.read()
        embedding = await create_embedding(text)
        with open(
            f"{args.embedding.split('_analysis')[0]}_embedding.txt",
            "w",
        ) as f:
            f.write(str(embedding))

    elif args.complete:
        with open(args.complete, "rb") as f:
            audio_bytes = f.read()
        await complete_audio_analysis(audio_bytes, args.complete)

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
                new_blob = bucket.blob(f"{NEW_TRANSCRIPT_FOLDER}/{file_name}.txt")
                new_blob.upload_from_string(transcription)

            except Exception as e:
                log.error(f"Error reading file {file_name}: {e}")
                return

            # tidy up and remove file
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
