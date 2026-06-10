"""Reset failed documents to pending and re-queue."""

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
        result = await session.execute(select(Document).where(Document.status == "failed"))
        docs = list(result.scalars().all())
        for doc in docs:
            doc.status = "pending"
            doc.error_message = None
            await session.merge(doc)
        await session.commit()
        for doc in docs:
            process_document_task.delay(str(doc.id))
            print(f"Re-queued {doc.id} ({doc.file_name})")
        if not docs:
            print("No failed documents")


if __name__ == "__main__":
    asyncio.run(main())
