"""Shared utilities for overnight GPU experiments."""

import json
import os
import time
import requests
from pathlib import Path

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:14b")


def call_qwen(prompt: str, max_tokens: int = 4000, temperature: float = 0.0, json_mode: bool = False) -> str:
    """Call Qwen via Ollama. Returns raw text response."""
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }
    if json_mode:
        payload["format"] = "json"

    resp = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=300)
    resp.raise_for_status()
    return resp.json()["response"].strip()


def call_qwen_chat(messages: list[dict], max_tokens: int = 4000, temperature: float = 0.0, json_mode: bool = False) -> str:
    """Call Qwen via Ollama chat API."""
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }
    if json_mode:
        payload["format"] = "json"

    resp = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=300)
    resp.raise_for_status()
    return resp.json()["message"]["content"].strip()


def check_ollama():
    """Verify Ollama is running and model is available."""
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=10)
        resp.raise_for_status()
        models = [m["name"] for m in resp.json().get("models", [])]
        # Check if our model (or a variant) is available
        base_model = MODEL.split(":")[0]
        found = any(base_model in m for m in models)
        if not found:
            print(f"WARNING: Model {MODEL} not found. Available: {models}")
            print(f"Pull with: ollama pull {MODEL}")
            return False
        return True
    except Exception as e:
        print(f"ERROR: Cannot connect to Ollama at {OLLAMA_URL}: {e}")
        return False


def get_franklin_conversations(limit: int = 20) -> list[dict]:
    """Load Franklin conversations from the Franklin subject DB."""
    import sqlite3
    db_path = os.environ.get(
        "EXPERIMENT_DB",
        str(Path(__file__).parent.parent.parent.parent / "subjects" / "franklin_memory" / "data" / "database" / "memory.db")
    )
    if not os.path.exists(db_path):
        print(f"ERROR: Database not found at {db_path}")
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Get conversations with their messages
    rows = conn.execute("""
        SELECT c.id, c.title, GROUP_CONCAT(m.content_text, '\n\n') as full_text
        FROM conversations c
        JOIN messages m ON m.conversation_id = c.id
        WHERE m.content_text IS NOT NULL AND LENGTH(m.content_text) > 50
        GROUP BY c.id
        ORDER BY c.created_at
        LIMIT ?
    """, (limit,)).fetchall()

    convos = [{"id": r["id"], "title": r["title"], "text": r["full_text"]} for r in rows]
    conn.close()
    return convos


def save_results(experiment_name: str, results: dict):
    """Save experiment results to JSON."""
    results_dir = os.environ.get(
        "EXPERIMENT_RESULTS_DIR",
        str(Path(__file__).parent / "results")
    )
    os.makedirs(results_dir, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    path = os.path.join(results_dir, f"{experiment_name}_{timestamp}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"Results saved to: {path}")
    return path
