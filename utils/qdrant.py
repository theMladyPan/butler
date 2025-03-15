from qdrant_client import AsyncQdrantClient
from dotenv import load_dotenv
from qdrant_client.models import VectorParams, Distance, PointStruct
import os
import numpy as np

load_dotenv()
QDRANT_ENDPOINT = os.getenv("QDRANT_ENDPOINT", None)
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", None)
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "test")
VECTOR_SIZE = int(os.getenv("VECTOR_SIZE", 768))

assert QDRANT_ENDPOINT, "QDRANT_ENDPOINT environment variable is not set"
assert QDRANT_API_KEY, "QDRANT_API_KEY environment variable is not set"
assert VECTOR_SIZE, "VECTOR_SIZE environment variable is not set"

client = AsyncQdrantClient(url=f"{QDRANT_ENDPOINT}:6333", api_key=QDRANT_API_KEY)


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


async def search(query_vector: np.ndarray):
    res = await client.search(
        collection_name=QDRANT_COLLECTION,
        query_vector=query_vector,  # type: ignore
        limit=10,
    )
    return res


async def delete_collection():
    await client.delete_collection(collection_name=QDRANT_COLLECTION)


async def collection_info():
    count = await client.count(collection_name=QDRANT_COLLECTION)
    info = await client.info()
    return {"count": count, "info": info}


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
    group.add_argument("-s", "--search", action="store_true", help="Search a Qdrant collection")
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
        query_vector = np.random.rand(VECTOR_SIZE)
        res = asyncio.run(search(query_vector))
        print(res)
    else:
        parser.print_help()
