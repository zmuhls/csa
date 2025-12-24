#!/usr/bin/env python3
"""
Batch label images using Qwen VL Plus via OpenRouter API.
Reads from images_label_requests.jsonl and writes to images_label_responses.jsonl.
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Dict, List, Optional

import aiohttp
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()

IN_JSONL = Path('prompts/images_label_requests.jsonl')
OUT_JSONL = Path('prompts/images_label_responses.jsonl')

API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "qwen/qwen-vl-plus"
BATCH_SIZE = 5
MAX_RETRIES = 3
RETRY_DELAY = 2


def load_existing_responses() -> set:
    """Load IDs of already-processed images."""
    done = set()
    if OUT_JSONL.exists():
        with OUT_JSONL.open() as f:
            for line in f:
                if line.strip():
                    try:
                        obj = json.loads(line)
                        if obj.get('id'):
                            done.add(obj['id'])
                    except Exception:
                        pass
    return done


def load_requests() -> List[Dict]:
    """Load all pending label requests."""
    done = load_existing_responses()
    pending = []
    with IN_JSONL.open() as f:
        for line in f:
            if line.strip():
                try:
                    obj = json.loads(line)
                    if obj.get('id') and obj['id'] not in done:
                        pending.append(obj)
                except Exception:
                    pass
    return pending


async def label_image(session: aiohttp.ClientSession, request: Dict, api_key: str) -> Optional[Dict]:
    """Send a single image to the LLM for labeling."""
    image_b64 = request.get('image_b64')
    if not image_b64:
        return {"id": request['id'], "error": "No image data", "item_type": None, "subject": None}

    instructions = request.get('instructions', '')
    schema = request.get('schema', {})
    response_template = request.get('response_template', {})
    metadata_hint = request.get('metadata_hint', {})

    prompt = f"""{instructions}

Context hints:
- Session group: {metadata_hint.get('session_group_id', 'unknown')}
- Session index: {metadata_hint.get('session_index', 'unknown')}
- EXIF creation: {metadata_hint.get('exif_creation', 'unknown')}

Respond ONLY with valid JSON matching this schema:
{json.dumps(schema, indent=2)}

Start your response with {{ and end with }}. No other text."""

    payload = {
        "model": MODEL,
        "max_tokens": 500,
        "temperature": 0.1,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_b64}"
                        }
                    },
                    {
                        "type": "text",
                        "text": prompt
                    }
                ]
            }
        ]
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/cs-archive",
        "X-Title": "CS Archive Image Labeling"
    }

    for attempt in range(MAX_RETRIES):
        try:
            async with session.post(API_URL, json=payload, headers=headers, timeout=60) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    content = data.get('choices', [{}])[0].get('message', {}).get('content', '')

                    # Parse JSON from response
                    try:
                        # Find JSON in response
                        start = content.find('{')
                        end = content.rfind('}') + 1
                        if start >= 0 and end > start:
                            result = json.loads(content[start:end])
                            result['id'] = request['id']
                            return result
                    except json.JSONDecodeError:
                        pass

                    # Fallback: return raw response
                    return {
                        "id": request['id'],
                        "item_type": None,
                        "subject": None,
                        "notes": f"Failed to parse: {content[:200]}",
                        "confidence": 0.0
                    }
                elif resp.status == 429:
                    # Rate limited
                    await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                else:
                    error_text = await resp.text()
                    return {
                        "id": request['id'],
                        "error": f"API error {resp.status}: {error_text[:100]}",
                        "item_type": None,
                        "subject": None
                    }
        except asyncio.TimeoutError:
            await asyncio.sleep(RETRY_DELAY)
        except Exception as e:
            return {
                "id": request['id'],
                "error": str(e),
                "item_type": None,
                "subject": None
            }

    return {
        "id": request['id'],
        "error": "Max retries exceeded",
        "item_type": None,
        "subject": None
    }


async def process_batch(session: aiohttp.ClientSession, batch: List[Dict], api_key: str) -> List[Dict]:
    """Process a batch of requests concurrently."""
    tasks = [label_image(session, req, api_key) for req in batch]
    results = await asyncio.gather(*tasks)
    return [r for r in results if r is not None]


async def main():
    api_key = os.getenv("OPENROUTER_KEY")
    if not api_key:
        print("Error: OPENROUTER_KEY not found in environment")
        return

    requests = load_requests()
    if not requests:
        print("No pending requests to process")
        return

    print(f"Processing {len(requests)} images...")

    async with aiohttp.ClientSession() as session:
        with OUT_JSONL.open('a') as f_out:
            with tqdm(total=len(requests), desc="Labeling") as pbar:
                for i in range(0, len(requests), BATCH_SIZE):
                    batch = requests[i:i+BATCH_SIZE]
                    results = await process_batch(session, batch, api_key)

                    for result in results:
                        f_out.write(json.dumps(result) + "\n")
                        f_out.flush()

                    pbar.update(len(batch))

                    # Brief pause between batches
                    if i + BATCH_SIZE < len(requests):
                        await asyncio.sleep(0.5)

    print(f"Results written to {OUT_JSONL}")


if __name__ == '__main__':
    asyncio.run(main())
