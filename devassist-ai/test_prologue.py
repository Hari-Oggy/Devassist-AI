import asyncio
from llm.router import LLMRouter
from llm.schemas import LLMRequest

async def main():
    router = LLMRouter()
    
    system_prompt = (
        "You are an expert technical writer and software architect. "
        "Your job is to synthesize a high-level prologue (executive summary) of a Pull Request "
        "based on the PR's chapters, title, and commit messages.\n\n"
        "Return a JSON object matching this schema:\n"
        "{\n"
        '  "motivation": "A short paragraph explaining WHY this PR was made (inferred from title/commits).",\n'
        '  "outcome": "A short paragraph explaining WHAT this PR achieves.",\n'
        '  "focus_areas": ["List", "of", "high-level", "areas", "to", "review"],\n'
        '  "complexity": {"level": "low|medium|high", "reasoning": "Why this level?"},\n'
        '  "diagram": "Optional mermaid.js markdown diagram block showing architecture changes (or null)"\n'
        "}"
    )

    user_prompt = "PR Title: Auth fix\nPR Body: Fixing auth bugs\n\nCommit Messages:\n- Fix auth\n\nChapters in this PR:\n- Chapter 1: Auth - Auth changes\n\nSynthesize the prologue."

    request = LLMRequest(
        task_type="code_review",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.2,
        metadata={"pipeline_stage": "prologue_synthesis"}
    )

    response = router.generate(request)
    print("SUCCESS:", response.success)
    print("RAW CONTENT:", response.content)

asyncio.run(main())
