"""CLI entry point for copilot-sync command."""

import asyncio
import os
from pathlib import Path

from .sync import run_sync
from .api_client import CopilotAPIClient
from .local.sqlite_store import SQLiteStore
from .local.chroma_store import ChromaStore


async def _sync():
    data_dir = Path(os.environ.get("FLOXBOT_COPILOT_DATA_DIR", "."))
    client = CopilotAPIClient()
    store = SQLiteStore(data_dir / "copilot.db")
    await store.init()
    chroma = ChromaStore(persist_dir=str(data_dir / "chroma"))
    results = await run_sync(client, store, chroma, data_dir, "local_user", timeout=30.0)
    await store.close()
    await client.close()
    canon = results["canon"]
    queues = results["queues"]
    errors = results["errors"]
    print(f"Canon: {canon} chunks synced")
    print(f"Queues: {queues} records flushed")
    if errors:
        for e in errors:
            print(f"Warning: {e}")
    else:
        print("Sync complete.")


def main():
    asyncio.run(_sync())


if __name__ == "__main__":
    main()
