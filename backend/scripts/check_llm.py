"""Check whether the configured AI provider is actually reachable, and what the app returns."""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core  # noqa: E402,F401  -- importing core is what loads backend/.env


async def main():
    key = (os.environ.get("NVIDIA_API_KEY") or "").strip()
    print("NVIDIA_API_KEY present:", bool(key))

    import httpx
    payload = {"model": "meta/llama-3.3-70b-instruct", "temperature": 0.2, "max_tokens": 64,
               "messages": [{"role": "user", "content": "Reply with exactly: PONG"}]}
    try:
        async with httpx.AsyncClient(timeout=90) as c:
            r = await c.post("https://integrate.api.nvidia.com/v1/chat/completions",
                             headers={"Authorization": f"Bearer {key}"}, json=payload)
        print("status:", r.status_code)
        if r.status_code == 200:
            print("content:", r.json()["choices"][0]["message"]["content"][:200])
        else:
            print("body:", r.text[:300])
    except Exception as e:
        print("ERROR:", type(e).__name__, str(e)[:200])


asyncio.run(main())
