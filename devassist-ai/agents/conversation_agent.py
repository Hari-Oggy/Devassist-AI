"""
Conversation Agent — responds to developer replies on bot review comments.

When a developer replies to a DevAssist AI comment on a PR, this agent:
  1. Fetches the original bot comment + code context
  2. Sends the conversation to the LLM for a contextual response
  3. Posts the AI's reply back on the PR
"""

import json
from datetime import datetime

from core.config import get_settings
from core.logger import get_logger, generate_request_id
from llm.router import LLMRouter
from llm.schemas import LLMRequest
from rag.retriever import CodebaseRetriever
from agents.tools.github_tool import get_github_client

logger = get_logger("agents.conversation")

CONVERSATION_SYSTEM_PROMPT = """You are DevAssist AI, an intelligent code review assistant.
A developer is replying to one of your previous review comments on a Pull Request.

Your job:
1. Understand what the developer is asking or saying
2. Provide a helpful, contextual response
3. If they're asking for clarification, explain your reasoning
4. If they disagree with your suggestion, acknowledge their point and provide alternatives
5. If they're asking how to fix something, give a concrete code example

Be concise, friendly, and technically precise. Use markdown formatting.
Do NOT include JSON arrays in your response — just write natural prose/code."""


class ConversationAgent:
    def __init__(self):
        self.settings = get_settings()
        self.router = LLMRouter()
        self.retriever = CodebaseRetriever()
        self.github_client = get_github_client()

    def respond(self, pr_number: int, comment_id: int = None, user_comment: str = "") -> dict:
        """
        Respond to a developer's reply on a PR comment.

        Args:
            pr_number: The PR number
            comment_id: The ID of the comment the developer replied to (if available)
            user_comment: The developer's reply text
        """
        request_id = generate_request_id()
        logger.info(f"[{request_id}] Conversation on PR #{pr_number}")

        # 1. Get the original bot comment context (if we have comment_id)
        original_context = ""
        code_context = ""
        if comment_id:
            comment_data = self.github_client.get_comment_context(comment_id)
            if comment_data:
                original_context = comment_data.get("body", "")
                code_context = comment_data.get("diff_hunk", "")
                file_path = comment_data.get("path", "")
                logger.info(f"Context: {file_path}, line {comment_data.get('line')}")

        # 2. Get RAG context for deeper understanding
        rag_context = ""
        try:
            rag_context = self.retriever.get_context(user_comment, k=2)
        except Exception as e:
            logger.debug(f"RAG context unavailable: {e}")

        # 3. Build the conversation for the LLM
        user_content_parts = []

        if code_context:
            user_content_parts.append(f"**Code being discussed:**\n```\n{code_context}\n```")

        if original_context:
            user_content_parts.append(f"**Your previous review comment:**\n{original_context}")

        user_content_parts.append(f"**Developer's reply:**\n{user_comment}")

        if rag_context:
            user_content_parts.append(f"**Relevant codebase context:**\n{rag_context}")

        user_content = "\n\n---\n\n".join(user_content_parts)

        llm_request = LLMRequest(
            task_type="code_review",
            messages=[
                {"role": "system", "content": CONVERSATION_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
            metadata={"request_id": request_id, "pr_number": pr_number, "type": "conversation"},
        )

        # 4. Call the LLM
        logger.info("Sending conversation to LLM Router...")
        llm_response = self.router.generate(llm_request)

        if not llm_response.success:
            logger.error(f"LLM call failed: {llm_response.error}")
            return {"success": False, "error": llm_response.error}

        response_text = llm_response.content

        # 5. Post the reply on GitHub
        if comment_id:
            success = self.github_client.reply_to_comment(pr_number, comment_id, response_text)
        else:
            # Fallback: post as a general comment
            success = self.github_client.post_general_comment(pr_number, response_text)

        if success:
            logger.info(f"Conversation reply posted on PR #{pr_number}")
        else:
            logger.warning(f"Failed to post conversation reply on PR #{pr_number}")

        return {
            "success": success,
            "pr_number": pr_number,
            "response": response_text,
            "model_used": llm_response.model,
            "provider_used": llm_response.provider,
        }
