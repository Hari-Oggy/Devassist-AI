import json
from llm.router import LLMRouter
from llm.schemas import LLMRequest
from schemas.chapter import ChapterOut

class ChapterClusterer:
    def __init__(self, router: LLMRouter):
        self.router = router

    async def cluster(self, reviewable_files: list[dict], impact_report: dict) -> list[ChapterOut]:
        if not reviewable_files:
            return []

        system_prompt = (
            "You are a technical architect. Your job is to organize a list of changed files into logical 'Chapters' "
            "for a pull request review. A chapter represents a distinct logical component or feature (e.g., 'Database Schema', 'Frontend UI', 'Authentication').\n\n"
            "Return a JSON array of chapter objects matching this schema:\n"
            "[\n"
            "  {\n"
            '    "id": 1,\n'
            '    "order": 1,\n'
            '    "title": "Chapter Title",\n'
            '    "summary": "Brief summary of what changed in this chapter",\n'
            '    "file_paths": ["src/api/auth.py", "src/models/user.py"]\n'
            "  }\n"
            "]\n"
            "Assign every file to EXACTLY one chapter. Use 2 to 5 chapters total, depending on the PR size."
        )

        files_list = "\n".join([f"- {f.get('filename')}" for f in reviewable_files])

        user_prompt = (
            f"Please organize the following files into logical chapters:\n{files_list}\n\n"
            "Respond ONLY with the JSON array."
        )

        request = LLMRequest(
            task_type="code_review",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.1,
            metadata={"pipeline_stage": "chapter_clustering"}
        )

        response = self.router.generate(request)
        if not response.success or not response.content:
            return self._fallback(reviewable_files)

        try:
            content = response.content.strip()
            
            # Robust JSON array extraction
            data = None
            # Try 1: Direct parse
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                pass
            
            # Try 2: Extract from markdown code fences
            if data is None:
                import re
                fence_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', content, re.DOTALL)
                if fence_match:
                    try:
                        data = json.loads(fence_match.group(1).strip())
                    except json.JSONDecodeError:
                        pass
            
            # Try 3: Find outermost [ ... ] array
            if data is None:
                start = content.find('[')
                end = content.rfind(']')
                if start != -1 and end != -1 and end > start:
                    data = json.loads(content[start:end + 1])
            
            chapters = []
            for i, c in enumerate(data):
                chapters.append(
                    ChapterOut(
                        id=c.get("id", i + 1),
                        order=c.get("order", i + 1),
                        title=c.get("title", f"Chapter {i+1}"),
                        summary=c.get("summary", ""),
                        key_changes=[],
                        file_paths=c.get("file_paths", []),
                        finding_count=0
                    )
                )
            if not chapters:
                return self._fallback(reviewable_files)
            return chapters
        except Exception:
            return self._fallback(reviewable_files)

    def _fallback(self, reviewable_files: list[dict]) -> list[ChapterOut]:
        return [
            ChapterOut(
                id=1,
                order=1,
                title="Code Changes",
                summary="All modified files in this Pull Request.",
                key_changes=[],
                file_paths=[f.get("filename") for f in reviewable_files],
                finding_count=0
            )
        ]
