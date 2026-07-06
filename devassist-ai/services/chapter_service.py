from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import text


class ChapterService:
    @staticmethod
    async def get_chapters_for_review(session: AsyncSession, review_id: int):
        """
        Return chapters for a review.

        Chapters are stored two ways:
          1. In the `chapters` table (rows added during ensemble synthesis).
          2. As JSON inside review.pipeline_meta["chapters"] (fallback).

        We prefer the DB rows because they have proper ids; fall back to the
        JSON blob when the dedicated table is empty (e.g. old reviews or when
        the Chapter model table doesn't exist yet).
        """
        from models.chapter import Chapter
        from models.entities import Review
        from schemas.chapter import ChapterOut

        # --- Try dedicated chapters table first ---
        try:
            result = await session.execute(
                select(Chapter)
                .where(Chapter.review_id == review_id)
                .order_by(Chapter.order)
            )
            rows = result.scalars().all()
            if rows:
                return [
                    ChapterOut(
                        id=row.id,
                        order=row.order,
                        title=row.title,
                        summary=row.summary,
                        key_changes=[],
                        file_paths=[],
                        finding_count=0,
                    )
                    for row in rows
                ]
        except Exception:
            pass  # Table may not exist yet — fall through to pipeline_meta

        # --- Fallback: read from pipeline_meta JSON ---
        try:
            result = await session.execute(
                select(Review).where(Review.id == review_id)
            )
            review = result.scalars().first()
            if review and review.pipeline_meta:
                chapters_json = review.pipeline_meta.get("chapters", [])
                output = []
                for i, c in enumerate(chapters_json):
                    output.append(
                        ChapterOut(
                            id=c.get("id", i + 1),
                            order=c.get("order", i + 1),
                            title=c.get("title", f"Chapter {i+1}"),
                            summary=c.get("summary", ""),
                            key_changes=[],
                            file_paths=c.get("file_paths", []),
                            finding_count=0,
                        )
                    )
                return output
        except Exception:
            pass

        return []
