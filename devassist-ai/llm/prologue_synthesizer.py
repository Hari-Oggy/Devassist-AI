import json
import re
import logging
from llm.router import LLMRouter
from llm.schemas import LLMRequest
from schemas.prologue import PrologueOut, Complexity, FocusArea

logger = logging.getLogger("llm.prologue")


class PrologueSynthesizer:
    def __init__(self, router: LLMRouter):
        self.router = router

    async def synthesize(self, chapters: list, commit_messages: list[str], pr_title: str = "", pr_body: str = "") -> PrologueOut:
        system_prompt = (
            "You are an expert technical writer and software architect.\n"
            "Your job is to synthesize a high-level prologue (executive summary) of a Pull Request.\n\n"
            "CRITICAL OUTPUT RULES:\n"
            "1. Return ONLY a single valid JSON object. No markdown, no code fences, no commentary.\n"
            "2. Every string value must be properly JSON-escaped (use \\n for newlines, \\\\ for backslashes).\n"
            "3. The 'diagram' field must contain RAW Mermaid syntax ONLY — do NOT wrap it in ```mermaid``` code fences.\n"
            "   Example diagram value: \"graph LR\\n  A[Client] --> B[Server]\\n  B --> C[Database]\"\n\n"
            "JSON SCHEMA (follow exactly):\n"
            "{\n"
            '  "motivation": "A short paragraph explaining WHY this PR was created.",\n'
            '  "outcome": "A short paragraph explaining WHAT this PR achieves.",\n'
            '  "focus_areas": [\n'
            '    {\n'
            '      "type": "security|breaking-change|high-complexity|data-integrity|new-pattern|architecture|performance|testing-gap",\n'
            '      "severity": "critical|high|medium|info",\n'
            '      "title": "Short title of the focus area",\n'
            '      "description": "Brief explanation of why this area needs attention"\n'
            '    }\n'
            '  ],\n'
            '  "complexity": {\n'
            '    "level": "low|medium|high|very-high",\n'
            '    "reasoning": "Brief explanation of why this complexity level was chosen"\n'
            '  },\n'
            '  "diagram": "Raw Mermaid syntax string showing architecture or data flow changes, or null if not applicable"\n'
            "}\n\n"
            "IMPORTANT:\n"
            "- focus_areas MUST be an array of objects with type, severity, title, description fields.\n"
            "- diagram MUST be a plain string of Mermaid syntax (e.g. graph LR\\n  A --> B) or null.\n"
            "  NEVER use triple backticks or ```mermaid``` fences inside the diagram value.\n"
            "- Return ONLY the JSON object, nothing else."
        )

        # Build context from inputs
        chapters_context = "\n".join([f"- Chapter {c.get('order', 0)}: {c.get('title', '')} - {c.get('summary', '')}" for c in chapters])
        commits_context = "\n".join([f"- {msg}" for msg in commit_messages[:10]])

        user_prompt = (
            f"PR Title: {pr_title}\n"
            f"PR Body: {pr_body}\n\n"
            f"Commit Messages:\n{commits_context}\n\n"
            f"Chapters in this PR:\n{chapters_context}\n\n"
            "Synthesize the prologue. Return ONLY the JSON object."
        )

        request = LLMRequest(
            task_type="code_review",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.2,
            metadata={"pipeline_stage": "prologue_synthesis"}
        )

        response = self.router.generate(request)
        if not response.success or not response.content:
            logger.warning("Prologue LLM request failed or returned empty content")
            return self._fallback()

        try:
            data = self._extract_json(response.content)
            
            # Parse focus areas — handle both string arrays and object arrays
            raw_focus = data.get("focus_areas", [])
            focus_areas = self._parse_focus_areas(raw_focus)

            # Parse complexity with validation
            raw_complexity = data.get("complexity", {})
            complexity_level = raw_complexity.get("level", "medium") if isinstance(raw_complexity, dict) else "medium"
            complexity_reasoning = raw_complexity.get("reasoning", "N/A") if isinstance(raw_complexity, dict) else "N/A"
            # Ensure level is valid
            valid_levels = {"low", "medium", "high", "very-high"}
            if complexity_level not in valid_levels:
                complexity_level = "medium"

            # Clean diagram — strip any accidental markdown fences the LLM may have added
            diagram = data.get("diagram")
            if diagram:
                diagram = self._clean_diagram(diagram)
                if not diagram:
                    diagram = None

            logger.info(
                "Prologue parsed successfully: motivation=%d chars, outcome=%d chars, "
                "focus_areas=%d, diagram=%s",
                len(data.get("motivation", "")),
                len(data.get("outcome", "")),
                len(focus_areas),
                "present" if diagram else "null"
            )

            return PrologueOut(
                motivation=data.get("motivation", "Motivation not provided."),
                outcome=data.get("outcome", "Outcome not provided."),
                diagram=diagram,
                key_changes=[],
                focus_areas=focus_areas,
                complexity=Complexity(
                    level=complexity_level,
                    reasoning=complexity_reasoning
                )
            )
        except Exception as e:
            logger.error(
                "Failed to parse prologue json. Error: %s, Content (first 500 chars): %s",
                e, response.content[:500] if response.content else "None"
            )
            return self._fallback()

    def _extract_json(self, content: str) -> dict:
        """Robustly extract a JSON object from LLM output.
        
        Handles:
        - Raw JSON
        - JSON wrapped in ```json ... ``` code fences
        - JSON with leading/trailing text
        """
        content = content.strip()
        
        # Step 1: Try direct parse first (ideal case)
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        
        # Step 2: Strip markdown code fences
        # Match ```json ... ``` or ``` ... ```
        fence_pattern = re.compile(r'```(?:json)?\s*\n?(.*?)\n?\s*```', re.DOTALL)
        match = fence_pattern.search(content)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass
        
        # Step 3: Find the outermost { ... } using bracket matching
        start = content.find('{')
        if start == -1:
            raise ValueError("No JSON object found in LLM response")
        
        depth = 0
        in_string = False
        escape_next = False
        end = start
        
        for i in range(start, len(content)):
            ch = content[i]
            if escape_next:
                escape_next = False
                continue
            if ch == '\\' and in_string:
                escape_next = True
                continue
            if ch == '"' and not escape_next:
                in_string = not in_string
                continue
            if not in_string:
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
        
        if depth != 0:
            raise ValueError("Unbalanced braces in LLM response")
        
        json_str = content[start:end + 1]
        return json.loads(json_str)

    def _clean_diagram(self, diagram: str) -> str:
        """Strip markdown code fences from diagram string if LLM added them."""
        if not isinstance(diagram, str):
            return ""
        
        diagram = diagram.strip()
        
        # Remove ```mermaid ... ``` wrapping
        if diagram.startswith("```mermaid"):
            diagram = diagram[len("```mermaid"):]
        if diagram.startswith("```"):
            diagram = diagram[3:]
        if diagram.endswith("```"):
            diagram = diagram[:-3]
        
        diagram = diagram.strip()
        
        # Validate it looks like actual Mermaid syntax
        mermaid_keywords = ["graph ", "flowchart ", "sequenceDiagram", "classDiagram",
                           "stateDiagram", "erDiagram", "gantt", "pie ", "gitgraph",
                           "mindmap", "timeline", "journey", "C4Context", "graph\n",
                           "graph\r"]
        if not any(diagram.startswith(kw) or diagram.startswith(kw.upper()) for kw in mermaid_keywords):
            logger.warning("Diagram does not look like valid Mermaid syntax: %s...", diagram[:80])
            return ""
        
        return diagram

    def _parse_focus_areas(self, raw_focus: list) -> list[FocusArea]:
        """Parse focus areas, handling both string arrays and object arrays."""
        if not isinstance(raw_focus, list):
            return []
        
        focus_areas = []
        valid_types = {"security", "breaking-change", "high-complexity", "data-integrity",
                      "new-pattern", "architecture", "performance", "testing-gap"}
        valid_severities = {"critical", "high", "medium", "info"}
        
        for item in raw_focus:
            try:
                if isinstance(item, str):
                    # LLM returned simple strings — convert to FocusArea objects
                    focus_areas.append(FocusArea(
                        type="architecture",
                        severity="medium",
                        title=item,
                        description=item
                    ))
                elif isinstance(item, dict):
                    fa_type = item.get("type", "architecture")
                    if fa_type not in valid_types:
                        fa_type = "architecture"
                    
                    fa_severity = item.get("severity", "medium")
                    if fa_severity not in valid_severities:
                        fa_severity = "medium"
                    
                    focus_areas.append(FocusArea(
                        type=fa_type,
                        severity=fa_severity,
                        title=item.get("title", "Review Area"),
                        description=item.get("description", "")
                    ))
            except Exception as e:
                logger.warning("Skipping invalid focus area: %s (error: %s)", item, e)
                continue
        
        return focus_areas

    def _fallback(self) -> PrologueOut:
        return PrologueOut(
            motivation="Could not determine motivation.",
            outcome="Could not synthesize outcome.",
            diagram=None,
            key_changes=[],
            focus_areas=[],
            complexity=Complexity(level="medium", reasoning="Fallback.")
        )
