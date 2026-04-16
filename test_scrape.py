import asyncio
from backend.services.extractor import extract_from_url

async def main():
    res = await extract_from_url('https://deepmind.google/blog/gemini-robotics-er-1-6/')
    print("TEXT LEN:", len(res.text))
    print("ERROR:", res.metadata.get('error'))

asyncio.run(main())
