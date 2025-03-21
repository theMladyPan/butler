from qdrant_client import AsyncQdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct, ScoredPoint
from dotenv import load_dotenv
import os
import numpy as np
import openai
import logging
from datetime import datetime

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")


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
    res = await client.query_points(
        collection_name=QDRANT_COLLECTION,
        query=query_vector,  # type: ignore
        limit=limit,
    )
    res = res.points

    max_similarity = max([point.score for point in res])
    log.info(f"Max similarity: {max_similarity}")

    return res


async def summarize_knowledge_bit(knowledge: str, question: str) -> str:
    response = await openai_client.responses.create(
        model="gpt-4o-mini",
        input=[
            {"role": "developer", "content": knowledge},
            {"role": "user", "content": question},
        ],
        instructions=f"""
            Be concise.
            You are an AI business assistant that helps extract data from provided knowledge.
            Analyze provided knowledge and provide details from the knowledge for summarizing agent
            which will use these details while generating response to the question.
            Do not make summary of provided knowledge, just extract details from the knowledge.
            Do not use markdown or HTML, just plain text.
            Current date and time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
            """,
    )
    log.info(f"Summarized knowledge bit: {response.output_text}")

    return response.output_text


async def delete_collection():
    await client.delete_collection(collection_name=QDRANT_COLLECTION)


async def collection_info():
    count = await client.count(collection_name=QDRANT_COLLECTION)
    info = await client.info()
    return {"count": count, "info": info}


async def summarize(question: str, knowledge_bits: list[str]) -> str:
    input_data = [{"role": "developer", "content": bit} for bit in knowledge_bits]
    input_data.append({"role": "user", "content": question})

    response = await openai_client.responses.create(
        model="gpt-4o-mini",
        input=input_data,
        tools=[{"type": "web_search_preview"}],
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


async def web_search(keywords: str) -> str:
    response = await openai_client.responses.create(
        model="gpt-4o-mini",
        tools=[
            {
                "type": "web_search_preview",
                "search_context_size": "low",
            }
        ],
        input=keywords,
    )

    return response.output_text


async def craft_knowledge_query(question: str) -> str:
    response = await openai_client.responses.create(
        model="gpt-4o-mini",
        instructions=f"""
            Determine what you need to know to answer the question. Craft a set of keywords suitable 
            for a search in the knowledge database based on user question.
            Current date and time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
            The output is a set of keywords (5-20 words) that can be used to search the knowledge database.
            """,
        input=question,
    )
    query = response.output_text
    log.info(f"Crafted query: {query}")
    print(f"Searching for: {query} ... ")
    return query


async def retrieve_and_summarize(question: str) -> str:
    query = await craft_knowledge_query(question)
    points = await search(question)
    knowledge = [point.payload.get("information_shard") for point in points]
    #  = await web_search(question)
    knowledge_bits = [await summarize_knowledge_bit(bit, query) for bit in knowledge]
    return await summarize(question, knowledge_bits)


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
