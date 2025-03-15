from qdrant_client import AsyncQdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct
import os 

# initialize Qdrant client
QDRANT_ENDPOINT = os.getenv("QDRANT_ENDPOINT", None)
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", None)
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "test")
VECTOR_SIZE = int(os.getenv("VECTOR_SIZE", 768))

assert QDRANT_ENDPOINT, "QDRANT_ENDPOINT environment variable is not set"
assert QDRANT_API_KEY, "QDRANT_API_KEY environment variable is not set"
assert VECTOR_SIZE, "VECTOR_SIZE environment variable is not set"

qdrant_aclient = AsyncQdrantClient(url=f"{QDRANT_ENDPOINT}:6333", api_key=QDRANT_API_KEY)


async def random_upsert(points: list[PointStruct]):
    await qdrant_aclient.upsert(
        collection_name=QDRANT_COLLECTION,
        points=points,
    )

async def _main:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("-u", "--upsert", help="Random upsert content of file")