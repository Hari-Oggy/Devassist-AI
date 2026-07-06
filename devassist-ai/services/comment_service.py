from sqlalchemy.ext.asyncio import AsyncSession

class CommentService:
    @staticmethod
    async def get_threads_for_review(session: AsyncSession, review_id: int):
        return []
