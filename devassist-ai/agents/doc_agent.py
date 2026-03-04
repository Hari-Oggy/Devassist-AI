"""
Documentation Agent — uses the LLM Router (never provider APIs directly).
"""

import os
import ast
import json
from pathlib import Path

from core.config import get_settings
from core.logger import get_logger, generate_request_id
from llm.router import LLMRouter
from llm.schemas import LLMRequest
from prompts import load_prompt

logger = get_logger("agents.doc")


class DocumentationAgent:
    def __init__(self):
        self.settings = get_settings()
        self.router = LLMRouter()

    def _read_file(self, file_path: str) -> str:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

    def _has_docstring(self, node) -> bool:
        return ast.get_docstring(node) is not None

    def _find_undocumented(self, source_code: str) -> list[dict]:
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return []

        undocumented = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if not self._has_docstring(node):
                    name = node.name
                    if name.startswith("_") and len(node.body) < 5:
                        continue
                    node_type = "class" if isinstance(node, ast.ClassDef) else "function"
                    snippet = source_code.splitlines()[node.lineno - 1:node.lineno + 9]
                    undocumented.append({
                        "name": name,
                        "type": node_type,
                        "lineno": node.lineno,
                        "source_snippet": "\n".join(snippet),
                    })
        return undocumented

    def generate_docstrings(self, file_path: str) -> dict:
        source_code = self._read_file(file_path)
        undocumented = self._find_undocumented(source_code)

        if not undocumented:
            return {
                "file": file_path,
                "updated_code": source_code,
                "changes": 0,
                "message": "All functions already documented",
                "items_documented": [],
            }

        request_id = generate_request_id()
        system_prompt = load_prompt("doc_prompt")
        items_json = json.dumps([{"name": i["name"], "type": i["type"], "snippet": i["source_snippet"]} for i in undocumented])

        llm_request = LLMRequest(
            task_type="documentation",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"File: {file_path}\n\nUndocumented items: {items_json}\n\nFull source:\n{source_code}\n\nReturn the complete updated file."},
            ],
            temperature=self.settings.DOC_TEMPERATURE,
            metadata={"request_id": request_id, "file": file_path},
        )

        response = self.router.generate(llm_request)

        if not response.success:
            logger.error(f"LLM call failed for docstrings: {response.error}")
            return {"file": file_path, "updated_code": source_code, "changes": 0, "error": response.error, "items_documented": []}

        updated_code = response.content
        # Strip markdown code fences if present
        if updated_code.startswith("```python"):
            updated_code = updated_code[9:]
        if updated_code.startswith("```"):
            updated_code = updated_code[3:]
        if updated_code.endswith("```"):
            updated_code = updated_code[:-3]
        updated_code = updated_code.strip()

        names = [item["name"] for item in undocumented]
        return {
            "file": file_path,
            "updated_code": updated_code,
            "changes": len(undocumented),
            "items_documented": names,
            "model_used": response.model,
            "provider_used": response.provider,
        }

    def generate_module_markdown(self, file_path: str, updated_code: str = None) -> str:
        code = updated_code if updated_code else self._read_file(file_path)
        request_id = generate_request_id()

        llm_request = LLMRequest(
            task_type="documentation",
            messages=[
                {"role": "system", "content": "You are a technical documentation writer."},
                {"role": "user", "content": f"Generate clean Markdown documentation for this Python module. Include: module overview, all public functions/classes with their parameters and return types, and 2-3 usage examples. Format nicely with headers.\n\nModule: {file_path}\n\n{code}"},
            ],
            temperature=self.settings.DOC_TEMPERATURE,
            metadata={"request_id": request_id, "file": file_path},
        )

        response = self.router.generate(llm_request)
        if not response.success:
            return f"Error generating documentation: {response.error}"
        return response.content

    def process_file(self, file_path: str, save_updated: bool = False) -> dict:
        try:
            results = self.generate_docstrings(file_path)
            updated_code = results.get("updated_code", "")
            markdown = self.generate_module_markdown(file_path, updated_code)

            if save_updated and results.get("changes", 0) > 0:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(updated_code)
                md_path = str(Path(file_path).with_suffix('.md'))
                with open(md_path, "w", encoding="utf-8") as f:
                    f.write(markdown)

            return {
                "file": file_path,
                "updated_code": updated_code,
                "markdown": markdown,
                "changes_made": results.get("changes", 0),
                "items_documented": results.get("items_documented", []),
                "model_used": results.get("model_used", ""),
                "provider_used": results.get("provider_used", ""),
                "success": True,
            }
        except Exception as e:
            logger.error(f"process_file failed: {e}")
            return {"file": file_path, "success": False, "error": str(e)}
