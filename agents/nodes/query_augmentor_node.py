"""
Node 1: query_augmentor_node

Augments the raw user question with IR-domain context, intent classification,
file extraction directives, and output format expectations.

LLM: GPT-4.1 (analysis, temperature=0.2)
"""

from __future__ import annotations

import os
import logging
from typing import Any, Dict

from langchain_core.messages import HumanMessage
from tavily import TavilyClient

from agents.state import AgentState
from agents.augmenter_models import AugmentedQuery
from agents.LLM_CALLs.llm_handler import llm_handler
from agents.prompts.augmenter_prompt import AUGMENTER_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def _build_file_catalog(available_files) -> str:
    """Format the available files into a readable catalog string."""
    if not available_files:
        return "No files uploaded."
    lines = []
    for f in available_files:
        lines.append(
            f"- file_id={f.get('file_id', 'N/A')} | name={f.get('name', 'N/A')} "
            f"| chars={f.get('num_chars', 0):,} | topic={f.get('topic_hint', 'N/A')}"
        )
    return "\n".join(lines)


def _build_conversation_context(messages) -> str:
    """Extract conversation history for the augmentor."""
    lines = []
    for msg in messages:
        role = "User" if isinstance(msg, HumanMessage) else "Assistant"
        content = msg.content if hasattr(msg, "content") else str(msg)
        lines.append(f"[{role}]: {content[:2000]}")  # truncate very long messages
    return "\n\n".join(lines)


def query_augmentor_node(state: AgentState) -> Dict[str, Any]:
    """
    LangGraph node: augments the user query with structured IR context.

    Reads:  state.messages, state.available_files
    Writes: state.planner_question, state.augmentor_payload
    """
    messages = state.get("messages", [])
    available_files = state.get("available_files", [])
    metadata = state.get("metadata", {})
    web_search_enabled = metadata.get("web_search_enabled", False)

    if not messages:
        logger.warning("query_augmentor_node: No messages in state.")
        return {"planner_question": "", "augmentor_payload": {}}

    # Build user content for the LLM
    file_catalog = _build_file_catalog(available_files)
    conversation_context = _build_conversation_context(messages)
    
    web_search_status = "ENABLED. You may generate `search_queries` if needed." if web_search_enabled else "DISABLED. Leave `search_queries` empty."

    user_content = (
        f"## Web Search Status\n{web_search_status}\n\n"
        f"## Available Files\n{file_catalog}\n\n"
        f"## Conversation History\n{conversation_context}\n\n"
        f"Produce the AugmentedQuery JSON now."
    )

    try:
        augmented: AugmentedQuery = llm_handler.call_structured(
            task_type="analysis",
            system_prompt=AUGMENTER_SYSTEM_PROMPT,
            user_content=user_content,
            output_schema=AugmentedQuery,
            temperature=0.2,
            max_tokens=8192,
        )
        planner_question = augmented.to_brief()
        augmentor_payload = augmented.model_dump()
        logger.info(f"query_augmentor_node: intent={augmented.query_intent}, clarity={augmented.query_clarity}, searches={len(augmented.search_queries)}")
        
        # Execute proactive Web Search if queries are generated
        if web_search_enabled and augmented.search_queries:
            tavily_api_key = os.getenv("TAVILY_API_KEY", "")
            if not tavily_api_key:
                logger.warning("TAVILY_API_KEY not found in environment. Skipping web search.")
            else:
                try:
                    logger.info(f"Executing {len(augmented.search_queries)} Tavily searches...")
                    client = TavilyClient(api_key=tavily_api_key)
                    search_results_text = []
                    for sq_idx, sq in enumerate(augmented.search_queries):
                        resp = client.search(sq, search_depth="advanced")
                        search_results_text.append(f"### Search Query: {sq}")
                        for res in resp.get("results", [])[:3]:  # Take top 3 results per query to avoid context bloom
                            search_results_text.append(f"Source: {res.get('url')}\nContent: {res.get('content')}\n")
                    
                    if search_results_text:
                        web_context = "\n".join(search_results_text)
                        planner_question += f"\n\n## Web Search Results (LIVE INTERNET DATA)\n{web_context}"
                except Exception as e:
                    logger.error(f"Tavily search failed: {e}")

    except Exception as e:
        logger.error(f"query_augmentor_node failed: {e}. Falling back to raw question.")
        # Fallback: use raw user question
        raw_question = messages[-1].content if messages else ""
        planner_question = raw_question
        augmentor_payload = {"fallback": True, "raw_question": raw_question}

    return {
        "planner_question": planner_question,
        "augmentor_payload": augmentor_payload,
    }
