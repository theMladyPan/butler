from qdrant_client import AsyncQdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct, ScoredPoint
from dotenv import load_dotenv
import os
import numpy as np
import openai
import logging
from datetime import datetime

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.WARNING, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")


load_dotenv()
QDRANT_ENDPOINT = os.getenv("QDRANT_ENDPOINT", None)
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", None)
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "test")
VECTOR_SIZE = int(os.getenv("VECTOR_SIZE", 768))

assert QDRANT_ENDPOINT, "QDRANT_ENDPOINT environment variable is not set"
assert QDRANT_API_KEY, "QDRANT_API_KEY environment variable is not set"
assert VECTOR_SIZE, "VECTOR_SIZE environment variable is not set"

client = AsyncQdrantClient(url=f"{QDRANT_ENDPOINT}:6333", api_key=QDRANT_API_KEY)

# Replace dotenv with Secret Manager
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", False)
assert OPENAI_API_KEY, "OPENAI_API_KEY environment variable is not set"

# Initialize OpenAI client
openai_client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)


async def create_embedding(text: str) -> list[float]:
    response = await openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=text,
        dimensions=VECTOR_SIZE,
    )

    return response.data[0].embedding


async def create_qdrant_collection():
    # Your async code using QdrantClient might be put here

    if not await client.collection_exists(QDRANT_COLLECTION):
        await client.create_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )


async def delete_qdrant_collection():
    pass


async def random_upsert():
    await client.upsert(
        collection_name=QDRANT_COLLECTION,
        points=[
            PointStruct(
                id=i,
                vector=np.random.rand(VECTOR_SIZE).tolist(),
                payload={"name": f"test_{i}"},
            )
            for i in range(100)
        ],
    )


async def search(search_phrase: str, limit: int = 5) -> list[ScoredPoint]:
    log.info(f"Creating embeddings for: {search_phrase}")
    query_vector = await create_embedding(search_phrase)

    log.info(f"Searching for: {search_phrase}")
    res = await client.search(
        collection_name=QDRANT_COLLECTION,
        query_vector=query_vector,  # type: ignore
        limit=limit,
    )
    max_similarity = max([point.score for point in res])
    log.info(f"Max similarity: {max_similarity}")

    return res


async def delete_collection():
    await client.delete_collection(collection_name=QDRANT_COLLECTION)


async def collection_info():
    count = await client.count(collection_name=QDRANT_COLLECTION)
    info = await client.info()
    return {"count": count, "info": info}


async def summarize(question: str, knowledge_bits: list[str]) -> str:
    input_data = [{"role": "user", "content": bit} for bit in knowledge_bits]
    input_data.append({"role": "developer", "content": question})

    response = await openai_client.responses.create(
        model="gpt-4o-mini",
        input=input_data,
        instructions="""
            Be concise.
            You are an AI business assistant that helps user using provided knowledge.
            Analyze provided knowledge and generate response to the question.
            If possible use the question's language in the response.
            Do not make summary of provided knowledge, just answer the question based on data provided.
            If suitable, add short recommendation.
            Current date and time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
            """,
    )

    return response.output_text


async def craft_knowledge_query(question: str) -> str:
    response = await openai_client.responses.create(
        model="gpt-4o-mini",
        instructions=f"""
            Craft a keyword or a phrase suitable for a search in the knowledge database based on user question.
            Current date and time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
            """,
        input=question,
    )
    query = response.output_text
    log.info(f"Crafted query: {query}")
    return query


async def retrieve_and_summarize(question: str) -> str:
    query = await craft_knowledge_query(question)
    points = await search(query)
    knowledge = [point.payload.get("information_shard") for point in points]
    return await summarize(question, knowledge)


if __name__ == "__main__":
    import asyncio
    import argparse

    parser = argparse.ArgumentParser(description="Qdrant collection of utils")
    # mutually exclucive operations
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-c", "--create", action="store_true", help="Create a Qdrant collection")
    group.add_argument("-d", "--delete", action="store_true", help="Delete a Qdrant collection")
    group.add_argument("-i", "--info", action="store_true", help="Get info about a Qdrant collection")
    group.add_argument("-r", "--random", action="store_true", help="Upsert random into a Qdrant collection")
    group.add_argument("-s", "--search", help="Search a Qdrant collection")
    group.add_argument("--ai", help="Search the knowledge and summarize the response")
    args = parser.parse_args()

    if args.create:
        asyncio.run(create_qdrant_collection())
    elif args.delete:
        asyncio.run(delete_collection())
    elif args.info:
        res = asyncio.run(collection_info())
        print(f"Collection info: {res}")
    elif args.random:
        asyncio.run(random_upsert())
    elif args.search:
        res = asyncio.run(search(args.search))
        print(res)
    elif args.ai:
        knowledge = asyncio.run(retrieve_and_summarize(args.ai))
        print(knowledge)
    else:
        parser.print_help()
