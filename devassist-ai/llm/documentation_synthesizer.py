import logging
from typing import Dict, Any, List

from llm.router import LLMRouter

logger = logging.getLogger("api.llm.documentation")

class DocumentationSynthesizer:
    """Generates inline documentation for modified files in a PR."""

    def __init__(self, router: LLMRouter):
        self.router = router

    async def generate_docs(self, reviewable_files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not reviewable_files:
            return []
            
        docs = []
        # Process files concurrently using gather, but limit to top 5 files to save time
        import asyncio
        tasks = []
        for file in reviewable_files[:5]:
            tasks.append(self._generate_for_file(file))
            
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for res in results:
            if isinstance(res, dict) and "file" in res:
                docs.append(res)
                
        return docs

    async def _generate_for_file(self, file_data: Dict[str, Any]) -> Dict[str, Any]:
        filename = file_data.get("filename", "")
        patch = file_data.get("patch", "")
        
        prompt = f"""
You are an expert technical writer. Based on the code changes below, generate documentation.

File: {filename}
Diff:
{patch}

Return ONLY a valid JSON object with the following schema, and no other text:
{{
  "file": "{filename}",
  "updated_code": "The full function/method snippet with your new docstrings added.",
  "markdown": "A markdown block explaining the changes and how to use the updated code.",
  "changes_made": 1,
  "items_documented": ["list", "of", "functions", "or", "classes", "documented"]
}}
"""
        from llm.schemas import LLMRequest
        import json
        
        request = LLMRequest(
            task_type="code_review",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            metadata={"pipeline_stage": "documentation"}
        )
        
        try:
            # Note: generate is synchronous, so we don't await it. If we need async, we'd run in an executor.
            # But the router might have blocking calls, so we run in executor
            import asyncio
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(None, self.router.generate, request)
            
            if not response.success or not response.content:
                return {}
                
            content = response.content.strip()
            
            start_idx = content.find('{')
            end_idx = content.rfind('}')
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                content = content[start_idx:end_idx+1]
                
            return json.loads(content)
        except Exception as e:
            logger.error(f"Documentation generation failed for {filename}: {e}")
            return {}
