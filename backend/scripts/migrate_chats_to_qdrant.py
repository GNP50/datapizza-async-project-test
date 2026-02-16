#!/usr/bin/env python3
"""
Migration script to index existing chats into Qdrant.

This script:
1. Fetches all existing chats from the database
2. Indexes them into Qdrant with proper user_id filtering
3. Skips chats without title or summary (no searchable content)

Usage:
    python scripts/migrate_chats_to_qdrant.py [--batch-size 100] [--dry-run]
"""
import asyncio
import argparse
import logging
from sqlalchemy import select
from app.services.database import db_manager
from app.models.chat import Chat
from app.services.vector import chat_index_manager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def migrate_chats(batch_size: int = 100, dry_run: bool = False):
    """
    Migrate all existing chats to Qdrant.

    Args:
        batch_size: Number of chats to process in each batch
        dry_run: If True, only show what would be indexed without actually indexing
    """
    logger.info("Starting chat migration to Qdrant")
    logger.info(f"Batch size: {batch_size}, Dry run: {dry_run}")

    total_chats = 0
    indexed_chats = 0
    skipped_chats = 0
    failed_chats = 0

    try:
        async with db_manager.session() as db:
            # Get total count
            count_result = await db.execute(select(Chat))
            all_chats = count_result.scalars().all()
            total_chats = len(all_chats)
            logger.info(f"Found {total_chats} total chats to process")

            # Process in batches
            for i in range(0, total_chats, batch_size):
                batch = all_chats[i:i + batch_size]
                logger.info(f"Processing batch {i // batch_size + 1} ({len(batch)} chats)")

                for chat in batch:
                    # Skip chats without searchable content
                    if not chat.title and not chat.summary:
                        logger.debug(f"Skipping chat {chat.id}: no title or summary")
                        skipped_chats += 1
                        continue

                    if dry_run:
                        logger.info(
                            f"[DRY RUN] Would index chat {chat.id} "
                            f"(user={chat.user_id}, title='{chat.title or 'N/A'}')"
                        )
                        indexed_chats += 1
                        continue

                    try:
                        # Index chat in Qdrant
                        point_id = await chat_index_manager.index_chat(
                            chat_id=chat.id,
                            user_id=chat.user_id,
                            title=chat.title,
                            summary=chat.summary,
                            created_at=chat.created_at
                        )

                        if point_id:
                            indexed_chats += 1
                            logger.debug(
                                f"Indexed chat {chat.id} "
                                f"(user={chat.user_id}, title='{chat.title}')"
                            )
                        else:
                            skipped_chats += 1
                            logger.debug(f"Skipped chat {chat.id}: no searchable content")

                    except Exception as e:
                        failed_chats += 1
                        logger.error(f"Failed to index chat {chat.id}: {e}")

                # Progress update
                progress = min(i + batch_size, total_chats)
                logger.info(
                    f"Progress: {progress}/{total_chats} "
                    f"({indexed_chats} indexed, {skipped_chats} skipped, {failed_chats} failed)"
                )

    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        raise

    # Final summary
    logger.info("=" * 80)
    logger.info("Migration Summary:")
    logger.info(f"  Total chats:    {total_chats}")
    logger.info(f"  Indexed:        {indexed_chats}")
    logger.info(f"  Skipped:        {skipped_chats}")
    logger.info(f"  Failed:         {failed_chats}")
    logger.info("=" * 80)

    if dry_run:
        logger.info("DRY RUN - No changes were made to Qdrant")

    return indexed_chats, skipped_chats, failed_chats


def main():
    parser = argparse.ArgumentParser(description="Migrate existing chats to Qdrant")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of chats to process per batch (default: 100)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be indexed without actually indexing"
    )
    args = parser.parse_args()

    asyncio.run(migrate_chats(batch_size=args.batch_size, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
