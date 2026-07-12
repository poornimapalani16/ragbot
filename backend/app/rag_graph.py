"""
LangGraph orchestration of the RAG flow:

    [retrieve] -> [generate]

Kept as an explicit graph (rather than a single chained call) so it's easy
to extend later -- e.g. add a "grade_documents" or "rewrite_query" node --
without restructuring the whole pipeline.
"""
from typing import List, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langgraph.graph import StateGraph, END

from app.config import settings
from app.database import vector_store_manager
from app.llm import get_chat_model
from app.memory import get_history, add_turn
from app.utils.exceptions import LLMProviderError
from app.utils.logger import get_logger
from app.utils.retry import resilient_call

logger = get_logger(__name__)


class RAGState(TypedDict):
    bot_id: str
    session_id: str
    question: str
    system_prompt: str
    context_docs: List[dict]
    answer: str


def retrieve_node(state: RAGState) -> RAGState:
    results = vector_store_manager.similarity_search(state["bot_id"], state["question"])
    context_docs = [
        {
            "content": doc.page_content,
            "source": doc.metadata.get("source", "unknown"),
            "score": score,
        }
        for doc, score in results
    ]
    state["context_docs"] = context_docs
    return state


@resilient_call(exceptions=(Exception,))
def _invoke_llm(messages):
    model = get_chat_model()
    return model.invoke(messages)


def generate_node(state: RAGState) -> RAGState:
    context_text = "\n\n---\n\n".join(
        f"[Source: {d['source']}]\n{d['content']}" for d in state["context_docs"]
    ) or "No relevant context was found in the knowledge base."

    history = get_history(state["session_id"])
    messages = [SystemMessage(content=f"{state['system_prompt']}\n\nContext:\n{context_text}")]
    for role, content in history:
        if role == "user":
            messages.append(HumanMessage(content=content))
        else:
            messages.append(AIMessage(content=content))
    messages.append(HumanMessage(content=state["question"]))

    try:
        response = _invoke_llm(messages)
        answer = response.content if hasattr(response, "content") else str(response)
    except Exception as e:
        logger.error(f"LLM generation failed after retries: {e}")
        raise LLMProviderError(str(e))

    state["answer"] = answer
    add_turn(state["session_id"], "user", state["question"])
    add_turn(state["session_id"], "assistant", answer)
    return state


def build_graph():
    graph = StateGraph(RAGState)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("generate", generate_node)
    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", END)
    return graph.compile()


_compiled_graph = None


def get_rag_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph


def run_rag(bot_id: str, session_id: str, question: str, system_prompt: str) -> RAGState:
    graph = get_rag_graph()
    initial_state: RAGState = {
        "bot_id": bot_id,
        "session_id": session_id,
        "question": question,
        "system_prompt": system_prompt,
        "context_docs": [],
        "answer": "",
    }
    return graph.invoke(initial_state)
