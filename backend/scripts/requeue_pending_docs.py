"""Re-queue any documents stuck in pending status."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.document import Document
from app.workers.tasks import process_document_task


async def main() -> None:
    async with async_session_factory() as session:
        result = await session.execute(select(Document).where(Document.status == "pending"))
        docs = list(result.scalars().all())
        if not docs:
            print("No pending documents")
            return
        for doc in docs:
            process_document_task.delay(str(doc.id))
            print(f"Queued {doc.id} ({doc.file_name})")


if __name__ == "__main__":
    asyncio.run(main())
