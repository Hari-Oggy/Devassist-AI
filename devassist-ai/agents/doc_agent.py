"""
Documentation Agent — uses the LLM Router (never provider APIs directly).
"""

import os
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

    def generate_docstrings(self, file_path: str) -> dict:
        source_code = self._read_file(file_path)
        ext = os.path.splitext(file_path)[1].lower()

        request_id = generate_request_id()
        system_prompt = load_prompt("doc_prompt")

        llm_request = LLMRequest(
            task_type="documentation",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"File: {file_path}\nExtension: {ext}\n\nFind all undocumented or poorly documented public functions, methods, and classes in this file. Add proper documentation comments to them (e.g., JSDoc for TS, Javadoc for Java, Google-style for Python, Rustdoc for Rust). Do not document private/internal helpers unless they are complex.\n\nFull source:\n{source_code}\n\nReturn ONLY the complete updated file."},
            ],
            temperature=self.settings.DOC_TEMPERATURE,
            metadata={"request_id": request_id, "file": file_path},
        )

        response = self.router.generate(llm_request)

        if not response.success:
            logger.error(f"LLM call failed for docstrings: {response.error}")
            return {"file": file_path, "updated_code": source_code, "changes": 0, "error": response.error, "items_documented": []}

        updated_code = response.content.strip()
        
        # Strip markdown code fences if present (e.g., ```python ... ```)
        if updated_code.startswith("```"):
            lines = updated_code.splitlines()
            if len(lines) > 1 and lines[0].startswith("```"):
                lines = lines[1:]
            if len(lines) > 1 and lines[-1].startswith("```"):
                lines = lines[:-1]
            updated_code = "\n".join(lines).strip()

        changes = 1 if updated_code != source_code.strip() else 0

        return {
            "file": file_path,
            "updated_code": updated_code,
            "changes": changes,
            "items_documented": ["Auto-detected items"] if changes else [],
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
                {"role": "user", "content": f"Generate clean Markdown documentation for this source code module. Include: module overview, all public functions/classes with their parameters and return types, and 2-3 usage examples. Format nicely with headers.\n\nModule: {file_path}\n\n{code}"},
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
            logger.error(f"Failed to process {file_path}: {e}")
            return {"file": file_path, "success": False, "error": str(e)}
