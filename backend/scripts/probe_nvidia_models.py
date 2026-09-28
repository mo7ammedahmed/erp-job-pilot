"""Probe candidate NVIDIA chat models for JSON compliance before wiring them into MODEL_CATALOG."""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core  # noqa: E402,F401  -- loads backend/.env
import httpx  # noqa: E402

CANDIDATES = [
    "nvidia/nemotron-3-super-120b-a12b",
    "nvidia/nemotron-3-ultra-550b-a55b",
    "nvidia/nemotron-3.5-lightning-30b-a3b",
    "meta/llama-3.3-70b-instruct",
]

PROMPT = ('Extract as strict JSON, output ONLY JSON: {"city":"","country_code":""}\n'
          'Text: The role is based in Jeddah, Saudi Arabia.')


async def probe(client, key, model):
    body = {"model": model, "temperature": 0.1, "max_tokens": 300,
            "messages": [{"role": "system", "content": "Output only valid JSON."},
                         {"role": "user", "content": PROMPT}]}
    try:
        r = await client.post("https://integrate.api.nvidia.com/v1/chat/completions",
                              headers={"Authorization": f"Bearer {key}"}, json=body)
        if r.status_code != 200:
            return f"HTTP {r.status_code} {r.text[:120]}"
        content = r.json()["choices"][0]["message"]["content"]
        start, end = content.find("{"), content.rfind("}")
        parsed = json.loads(content[start:end + 1]) if start > -1 and end > start else None
        return f"OK json={parsed}"
    except Exception as e:
        return f"ERROR {type(e).__name__}: {str(e)[:120]}"


async def main():
    key = core.os.environ.get("NVIDIA_API_KEY", "").strip()
    async with httpx.AsyncClient(timeout=120) as client:
        for m in CANDIDATES:
            print(f"{m:45s} -> {await probe(client, key, m)}")


asyncio.run(main())
