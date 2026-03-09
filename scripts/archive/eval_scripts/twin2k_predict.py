"""
Twin-2K-500 Prediction Harness (v2)

Matches the Digital-Twin-Simulation methodology exactly:
  - ALL questions in ONE prompt per participant (not one at a time)
  - Their exact question formatting (format_question_text with Answer: [Masked])
  - Their exact prompt structure (persona header + questions + JSON format instructions)
  - Structured JSON output: {Q1: {Question Type, Reasoning, Answers: {...}}, Q2: ...}
  - Ground truth from wave4_Q_w13A.json (wave 1-3 answers)
  - For C2: Base Layer brief replaces persona_text as the ONLY change

Conditions:
  C1: No persona context — just questions (baseline)
  C2: Base Layer brief as persona context
  C3: Full persona_text as persona context (replicates their best baseline)

Usage:
    python twin2k_predict.py --participant 0 --condition C1
    python twin2k_predict.py --all --condition C3
    python twin2k_predict.py --all --condition C2 --brief-dir path/to/briefs/
    python twin2k_predict.py --participant 0 --dry-run   # Show prompt without calling API
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
SUBJECTS_DIR = Path(os.environ.get(
    "TWIN2K_DIR",
    Path(__file__).parent.parent.parent / "subjects" / "twin2k"
))
RESULTS_DIR = SUBJECTS_DIR / "results"

# Model configs
MODELS = {
    "gpt-4.1-mini": {"provider": "openai", "model_id": "gpt-4.1-mini"},
    "gpt-4.1": {"provider": "openai", "model_id": "gpt-4.1"},
    "sonnet": {"provider": "anthropic", "model_id": "claude-sonnet-4-6"},
    "opus": {"provider": "anthropic", "model_id": "claude-opus-4-6"},
    "haiku": {"provider": "anthropic", "model_id": "claude-haiku-4-5-20251001"},
    "qwen": {"provider": "ollama", "model_id": "qwen2.5:14b"},
}

# ---------------------------------------------------------------------------
# Question formatting — ported from Digital-Twin-Simulation
# ---------------------------------------------------------------------------

def strip_html(text):
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    text = re.sub(r'<[^>]*>', ' ', text)
    text = text.replace('&nbsp;', ' ')
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def format_question_matrix(question, with_answers=False):
    columns = question.get("Columns", [])
    answers = question.get("Answers", {})
    lines = ["Question Type: Matrix\n"]
    if columns:
        lines.append("Options:\n")
        for i, col in enumerate(columns, 1):
            lines.append(f"  {i} = {strip_html(col)}\n")
        rows = question.get("Rows", [])
        sel_pos = answers.get("SelectedByPosition", [])
        sel_txt = answers.get("SelectedText", [])
        for i, row in enumerate(rows):
            lines.append(f"{i+1}. {strip_html(row)}\n")
            if with_answers and i < len(sel_pos) and i < len(sel_txt):
                lines.append(f"Answer: {sel_pos[i]} - {strip_html(sel_txt[i])}\n")
            else:
                lines.append("Answer: [Masked]\n")
        lines.append("\n")
    return ''.join(lines)


def format_question_mc(question, with_answers=False):
    options = question.get("Options", [])
    answers = question.get("Answers", {})
    settings = question.get("Settings", {})
    selector = settings.get("Selector", "")
    lines = []
    if selector in ("MAVR", "MAHR"):
        lines.append("Question Type: Multiple Choice\n")
    else:
        lines.append("Question Type: Single Choice\n")
    if options:
        lines.append("Options:\n")
        for i, opt in enumerate(options, 1):
            lines.append(f"  {i} - {strip_html(opt)}\n")
        if with_answers:
            sel_pos = answers.get("SelectedByPosition")
            sel_txt = answers.get("SelectedText")
            if sel_pos is not None:
                if selector in ("SAVR", "SAHR"):
                    lines.append(f"Answer: {sel_pos} - {strip_html(str(sel_txt))}\n")
                else:
                    if not isinstance(sel_pos, list):
                        sel_pos = [sel_pos]
                        sel_txt = [sel_txt]
                    for i, sp in enumerate(sel_pos):
                        if i < len(sel_txt):
                            lines.append(f"Answer: {sp} - {strip_html(str(sel_txt[i]))}\n")
            else:
                lines.append("Answer: [No Answer Provided]\n")
        else:
            lines.append("Answer: [Masked]\n")
    lines.append("\n")
    return ''.join(lines)


def format_question_slider(question, with_answers=False):
    answers = question.get("Answers", {})
    values = answers.get("Values", [])
    statements = question.get("Statements", [])
    lines = ["Question Type: Slider\n"]
    if values or statements:
        for i, stmt in enumerate(statements):
            display = strip_html(stmt) if stmt else "[No Statement Needed]"
            lines.append(f"{i+1}. {display}\n")
            if with_answers and i < len(values):
                lines.append(f"Answer: {strip_html(str(values[i]))}\n")
            else:
                lines.append("Answer: [Masked]\n")
    else:
        lines.append("Answer: [Masked]\n")
    lines.append("\n")
    return ''.join(lines)


def format_question_te(question, with_answers=False):
    settings = question.get("Settings", {})
    answers = question.get("Answers", {})
    selector = settings.get("Selector", "")
    lines = []
    if selector == "FORM":
        lines.append("Question Type: Text Entry (Form)\n")
        form_rows = question.get("Rows", [])
        form_answers = answers.get("Text", [])
        answer_lookup = {}
        for ans_item in form_answers:
            if isinstance(ans_item, dict):
                answer_lookup.update(ans_item)
        for row_label in form_rows:
            clean = strip_html(row_label)
            if with_answers:
                val = strip_html(str(answer_lookup.get(row_label, "[No Answer Provided]")))
                lines.append(f"{clean}: {val}\n")
            else:
                lines.append(f"{clean}: [Masked]\n")
    else:
        lines.append("Question Type: Text Entry\n")
        if with_answers:
            text_answer = answers.get("Text")
            if text_answer is not None:
                lines.append(f"Answer: {strip_html(str(text_answer))}\n")
            else:
                lines.append("Answer: [No Answer Provided]\n")
        else:
            lines.append("Answer: [Masked]\n")
    lines.append("\n")
    return ''.join(lines)


def format_question_text(question, with_answers=False):
    q_text = strip_html(question.get('QuestionText', ''))
    q_type = question.get("QuestionType", "")
    if q_type == "Matrix":
        body = format_question_matrix(question, with_answers)
    elif q_type == "MC":
        body = format_question_mc(question, with_answers)
    elif q_type == "Slider":
        body = format_question_slider(question, with_answers)
    elif q_type == "TE":
        body = format_question_te(question, with_answers)
    elif q_type == "DB":
        return q_text + "\n[Descriptive Information]\n\n"
    else:
        return q_text + "\n\n"
    return q_text + "\n" + body


# ---------------------------------------------------------------------------
# Format instructions — verbatim from their convert_question_json_to_text.py
# ---------------------------------------------------------------------------

GENERAL_LLM_INSTRUCTION = """Please answer the following questions as if you were taking this survey. The expected output is a JSON object and the format is provided in the end.
---

"""

FORMAT_INSTRUCTIONS = """
### Format Instructions:
In order to facilitate the postprocessing, you should generate string that can be parsed into a valid JSON object with the following format:
{
    "Q1": {
    "Question Type": "XX",
    "Reasoning": "Concise reasoning for the answer",
    "Answers": {
        see below
    }
    },
    "Q2": {
    "Question Type": "XX",
    "Reasoning": "Concise reasoning for the answer",
    "Answers": {
        see below
    }
    },
    ....
}

The question type can be one of the following:
1. Matrix
For Matrix questions, the answers should include two lists, one for the selected positions and one for the selected texts.
For example,

Would you support or oppose...
Question Type: Matrix
Options:
1 = Strongly oppose
2 = Somewhat oppose
3 = Neither oppose nor support
4 = Somewhat support
5 = Strongly support
1. Placing a tax on carbon emissions?
Answer: [Masked]
2. Ensuring 40% of all new clean energy infrastructure development spending goes to low-income communities?
Answer: [Masked]

Examples Answers:
{
    "Answers": {
        "SelectedByPosition": [1, 2],
        "SelectedText": ["Strongly oppose", "Somewhat oppose"]
    }
}

2. Single Choice
For Single Choice questions, the answers should include the selected position and the selected text.
For example,

Question Type: Single Choice
Options:
1 - I strongly favor program A
2 - I favor program A
3 - I slightly favor program A
4 - I slightly favor program B
5 - I favor program B
6 - I strongly favor program B
Answer: [Masked]

Examples Answers:
{
    "Answers": {
        "SelectedByPosition": 1,
        "SelectedText": "I strongly favor program A"
    }
}

3. Slider
For Slider questions, the answers should simply include the a list of answers.
For example,

Question Type: Slider
1. [No Statement Needed]
Answer: [Masked]

Examples Answers:
{
    "Answers": {
        "Values": ["55"],
    }
}

4. Text Entry
For Text Entry questions, the answers should simply include the text.
For example,

Question Type: Text Entry
Answer: [Masked]

Examples Answers:
{
    "Answers": {
        "Text": "70"
    }
}
"""

PERSONA_HEADER = "## Persona Profile (This individual's past survey responses):\n"
PERSONA_SEPARATOR = "\n\n---\n## New Survey Question & Instructions (Please respond as the persona described above):\n"
NO_CONTEXT_HEADER = "## New Survey Questions:\n"

# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------

def build_question_text(wave4_data):
    """Format all non-DB questions from wave4 JSON into the question prompt.
    Returns (question_text, question_metadata) where metadata maps Q-number to QID info.
    """
    lines = [GENERAL_LLM_INSTRUCTION]
    metadata = {}  # {Q_number: {qid, q_type, block_name, ...}}
    count = 0

    for block in wave4_data:
        if block.get("ElementType") != "Block":
            continue
        block_name = block.get("BlockName", "")
        for question in block.get("Questions", []):
            q_type = question.get("QuestionType", "")
            if q_type == "DB":
                lines.append(format_question_text(question, with_answers=False))
                continue
            count += 1
            q_num = f"Q{count}"
            lines.append(f"{q_num}:\n" + format_question_text(question, with_answers=False))
            metadata[q_num] = {
                "qid": question.get("QuestionID", ""),
                "q_type": q_type,
                "block_name": block_name,
                "question": question,
            }

    lines.append(FORMAT_INSTRUCTIONS)
    return ''.join(lines), metadata


def build_persona_text(wave4_data):
    """Format the persona's survey responses (with answers shown) as persona context.
    This creates the persona_text equivalent from the wave4_Q_w13A.json data,
    showing the person's wave 1-3 answers."""
    lines = []
    for block in wave4_data:
        if block.get("ElementType") != "Block":
            continue
        for question in block.get("Questions", []):
            lines.append(format_question_text(question, with_answers=True))
    return ''.join(lines)


def build_prompt(condition, question_text, persona_text=None, brief_text=None,
                 full_persona_text=None, summary_text=None):
    """Build the full prompt for a given condition.

    C1: questions only (no persona context)
    C2: Base Layer brief as persona + questions
    C3: full persona_text (from persona_text.txt file, ~130K chars) + questions
    C4: Base Layer brief + full persona_text (stacking test)
    C5: persona_summary.txt (~13K chars) as persona context
    """
    if condition == "C1":
        return NO_CONTEXT_HEADER + question_text

    elif condition == "C2":
        if not brief_text:
            raise ValueError("C2 requires brief_text")
        return (PERSONA_HEADER + brief_text + PERSONA_SEPARATOR + question_text)

    elif condition == "C3":
        if not full_persona_text:
            raise ValueError("C3 requires full_persona_text")
        return (PERSONA_HEADER + full_persona_text + PERSONA_SEPARATOR + question_text)

    elif condition == "C4":
        if not brief_text or not full_persona_text:
            raise ValueError("C4 requires both brief_text and full_persona_text")
        combined = ("## Behavioral Brief\n\n" + brief_text +
                    "\n\n## Full Survey Responses\n\n" + full_persona_text)
        return (PERSONA_HEADER + combined + PERSONA_SEPARATOR + question_text)

    elif condition == "C5":
        if not summary_text:
            raise ValueError("C5 requires summary_text")
        return (PERSONA_HEADER + summary_text + PERSONA_SEPARATOR + question_text)

    else:
        raise ValueError(f"Unknown condition: {condition}")


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------

def get_openai_client():
    try:
        from openai import OpenAI
    except ImportError:
        print("ERROR: 'openai' package required. pip install openai")
        sys.exit(1)
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: Set OPENAI_API_KEY environment variable")
        sys.exit(1)
    return OpenAI(api_key=api_key)


def get_anthropic_client():
    try:
        import anthropic
        return anthropic.Anthropic()
    except ImportError:
        print("ERROR: 'anthropic' package required. pip install anthropic")
        sys.exit(1)


def call_model(user_prompt, model_name="gpt-4.1-mini", max_tokens=8000):
    """Call model with user prompt only (no system prompt, matching their methodology)."""
    config = MODELS.get(model_name)
    if not config:
        raise ValueError(f"Unknown model: {model_name}. Options: {list(MODELS.keys())}")

    if config["provider"] == "ollama":
        import requests
        ollama_url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
        response = requests.post(
            f"{ollama_url}/api/chat",
            json={
                "model": config["model_id"],
                "messages": [{"role": "user", "content": user_prompt}],
                "stream": False,
                "options": {"temperature": 0, "num_predict": max_tokens},
            },
            timeout=300,
        )
        response.raise_for_status()
        return response.json()["message"]["content"].strip()
    elif config["provider"] == "openai":
        client = get_openai_client()
        response = client.chat.completions.create(
            model=config["model_id"],
            messages=[{"role": "user", "content": user_prompt}],
            max_tokens=max_tokens,
            temperature=0,
        )
        return response.choices[0].message.content.strip()
    else:
        client = get_anthropic_client()
        response = client.messages.create(
            model=config["model_id"],
            messages=[{"role": "user", "content": user_prompt}],
            max_tokens=max_tokens,
            temperature=0,
        )
        return response.content[0].text.strip()


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def parse_response_json(response_text):
    """Parse the structured JSON from model response.
    Handles ```json ... ``` blocks and plain JSON.
    Returns dict or None on failure.
    """
    text = response_text.strip()
    if "```json" in text:
        try:
            text = text.split("```json")[1].split("```")[0]
        except IndexError:
            pass
    elif "```" in text:
        try:
            text = text.split("```")[1].split("```")[0]
        except IndexError:
            pass

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object in the response
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return None


def extract_answer_value(answer_data, question):
    """Extract numeric scoring value(s) from a parsed answer.
    Returns a dict of {column_suffix: value} for the question.
    """
    q_type = question.get("QuestionType", "")
    answers = answer_data.get("Answers", {})

    if q_type == "MC":
        pos = answers.get("SelectedByPosition")
        if pos is not None:
            try:
                return {"": int(pos)}
            except (ValueError, TypeError):
                pass
        return {}

    elif q_type == "Matrix":
        positions = answers.get("SelectedByPosition", [])
        if not isinstance(positions, list):
            positions = [positions]
        result = {}
        for i, val in enumerate(positions):
            try:
                result[str(i + 1)] = int(val)
            except (ValueError, TypeError):
                pass
        return result

    elif q_type == "Slider":
        values = answers.get("Values", [])
        if not isinstance(values, list):
            values = [values]
        result = {}
        for i, val in enumerate(values):
            try:
                result[str(i + 1) if len(values) > 1 else "1"] = float(val)
            except (ValueError, TypeError):
                pass
        return result

    elif q_type == "TE":
        text = answers.get("Text", "")
        try:
            return {"": float(text)}
        except (ValueError, TypeError):
            return {"": text}

    return {}


# ---------------------------------------------------------------------------
# QID → scoring column mapping
# ---------------------------------------------------------------------------

def get_qid_to_column_map():
    """Map QuestionID → scoring column name(s).
    Returns dict: {QID: {type, columns_fn}} where columns_fn maps sub-index to column name.
    """
    mapping = {}

    # Matrix: QID287 → FALSE CONS. SELF _{row_id}
    # RowsID: ["1","2","3","4","5","6","7","10","11","12"]
    mapping["QID287"] = {
        "type": "matrix",
        "row_ids": ["1", "2", "3", "4", "5", "6", "7", "10", "11", "12"],
        "col_fn": lambda rid: f"FALSE CONS. SELF _{rid}",
    }

    # Slider: QID290 → FALSE CONS. OTHERS _{stmt_id}
    mapping["QID290"] = {
        "type": "slider_multi",
        "stmt_ids": ["1", "2", "3", "4", "5", "6", "7", "10", "11", "12"],
        "col_fn": lambda sid: f"FALSE CONS. OTHERS _{sid}",
    }

    # Slider single: QID156 → Q156_1
    mapping["QID156"] = {"type": "single", "column": "Q156_1"}

    # MC: framing
    for qid in ("QID157", "QID158"):
        mapping[qid] = {"type": "single", "column": qid.replace("QID", "Q")}

    # Matrix: Linda conjunction (3 rows each)
    for qid_num in ("159", "160"):
        mapping[f"QID{qid_num}"] = {
            "type": "matrix_sequential",
            "n_rows": 3,
            "col_fn": lambda i, q=qid_num: f"Q{q}_{i}",
        }

    # MC: outcome bias
    for qid in ("QID161", "QID162"):
        mapping[qid] = {"type": "single", "column": qid.replace("QID", "Q")}

    # Anchoring: MC anchors are NOT scored (skip QID163, QID165, QID167, QID169)
    for qid in ("QID163", "QID165", "QID167", "QID169"):
        mapping[qid] = {"type": "skip"}

    # Anchoring: TE answers ARE scored
    for qid in ("QID164", "QID166", "QID168", "QID170"):
        mapping[qid] = {"type": "single", "column": qid.replace("QID", "Q")}

    # Less is more / proportion dominance (QID171-179)
    for i in range(171, 180):
        mapping[f"QID{i}"] = {"type": "single", "column": f"Q{i}"}

    # Sunk cost (QID181, QID182)
    for i in (181, 182):
        mapping[f"QID{i}"] = {"type": "single", "column": f"Q{i}"}

    # Absolute vs relative (QID183, QID184)
    for i in (183, 184):
        mapping[f"QID{i}"] = {"type": "single", "column": f"Q{i}"}

    # WTA/WTP Thaler (QID189-191)
    for i in (189, 190, 191):
        mapping[f"QID{i}"] = {"type": "single", "column": f"Q{i}"}

    # Allais (QID192, QID193)
    for i in (192, 193):
        mapping[f"QID{i}"] = {"type": "single", "column": f"Q{i}"}

    # Myside (QID194, QID195)
    for i in (194, 195):
        mapping[f"QID{i}"] = {"type": "single", "column": f"Q{i}"}

    # Prob matching: QID198 (Matrix, 10 rows), QID203 (Matrix, 6 rows)
    mapping["QID198"] = {
        "type": "matrix_sequential",
        "n_rows": 10,
        "col_fn": lambda i: f"Q198_{i}",
    }
    mapping["QID203"] = {
        "type": "matrix_sequential",
        "n_rows": 6,
        "col_fn": lambda i: f"Q203_{i}",
    }

    # Non-separability benefits (QID288, Matrix, 4 rows)
    mapping["QID288"] = {
        "type": "matrix_sequential",
        "n_rows": 4,
        "col_fn": lambda i: f"NONSEPARABILTY BENE _{i}",
    }
    # Non-separability risks (QID289, Matrix, 4 rows)
    mapping["QID289"] = {
        "type": "matrix_sequential",
        "n_rows": 4,
        "col_fn": lambda i: f"NONSEPARABILITY RIS _{i}",
    }

    # Omission bias (QID291)
    mapping["QID291"] = {"type": "single", "column": "OMISSION BIAS "}

    # Denominator neglect (QID196)
    mapping["QID196"] = {"type": "single", "column": "DENOMINATOR NEGLECT "}

    # Pricing: QID9_1 through QID9_40
    for i in range(1, 41):
        mapping[f"QID9_{i}"] = {"type": "single", "column": f"{i}_Q295"}

    # DB (descriptive, skip)
    mapping["QID8"] = {"type": "skip"}

    # Base-rate Form A variant
    mapping["QID155"] = {"type": "single", "column": "FORM A _1"}

    return mapping


def map_predictions_to_columns(parsed_json, question_metadata):
    """Map parsed JSON predictions to scoring column values.
    Returns dict: {COLUMN_NAME: numeric_value}
    """
    qid_map = get_qid_to_column_map()
    column_values = {}

    for q_num, meta in question_metadata.items():
        qid = meta["qid"]
        question = meta["question"]

        if q_num not in parsed_json:
            continue

        answer_data = parsed_json[q_num]
        mapping = qid_map.get(qid)
        if not mapping or mapping["type"] == "skip":
            continue

        answers = answer_data.get("Answers", {})
        m_type = mapping["type"]

        if m_type == "single":
            col = mapping["column"]
            q_type = question.get("QuestionType", "")
            if q_type == "MC":
                val = answers.get("SelectedByPosition")
                if val is not None:
                    try:
                        column_values[col] = int(val)
                    except (ValueError, TypeError):
                        pass
            elif q_type == "Slider":
                vals = answers.get("Values", [])
                if vals:
                    try:
                        column_values[col] = float(vals[0])
                    except (ValueError, TypeError):
                        pass
            elif q_type == "TE":
                text = answers.get("Text", "")
                try:
                    column_values[col] = float(text)
                except (ValueError, TypeError):
                    column_values[col] = text

        elif m_type == "matrix":
            positions = answers.get("SelectedByPosition", [])
            if not isinstance(positions, list):
                positions = [positions]
            row_ids = mapping["row_ids"]
            col_fn = mapping["col_fn"]
            for i, val in enumerate(positions):
                if i < len(row_ids):
                    try:
                        column_values[col_fn(row_ids[i])] = int(val)
                    except (ValueError, TypeError):
                        pass

        elif m_type == "matrix_sequential":
            positions = answers.get("SelectedByPosition", [])
            if not isinstance(positions, list):
                positions = [positions]
            col_fn = mapping["col_fn"]
            for i, val in enumerate(positions):
                try:
                    column_values[col_fn(i + 1)] = int(val)
                except (ValueError, TypeError):
                    pass

        elif m_type == "slider_multi":
            values = answers.get("Values", [])
            if not isinstance(values, list):
                values = [values]
            stmt_ids = mapping["stmt_ids"]
            col_fn = mapping["col_fn"]
            for i, val in enumerate(values):
                if i < len(stmt_ids):
                    try:
                        column_values[col_fn(stmt_ids[i])] = float(val)
                    except (ValueError, TypeError):
                        pass

    return column_values


def extract_ground_truth_columns(wave4_data):
    """Extract ground truth column values from the wave4_Q_w13A.json data.
    Returns dict: {COLUMN_NAME: numeric_value}
    """
    qid_map = get_qid_to_column_map()
    column_values = {}

    for block in wave4_data:
        if block.get("ElementType") != "Block":
            continue
        for question in block.get("Questions", []):
            qid = question.get("QuestionID", "")
            q_type = question.get("QuestionType", "")
            answers = question.get("Answers", {})
            mapping = qid_map.get(qid)

            if not mapping or mapping["type"] == "skip":
                continue

            m_type = mapping["type"]

            if m_type == "single":
                col = mapping["column"]
                if q_type == "MC":
                    val = answers.get("SelectedByPosition")
                    if val is not None:
                        try:
                            column_values[col] = int(val)
                        except (ValueError, TypeError):
                            pass
                elif q_type == "Slider":
                    vals = answers.get("Values", [])
                    if vals:
                        try:
                            column_values[col] = float(vals[0])
                        except (ValueError, TypeError):
                            pass
                elif q_type == "TE":
                    text = answers.get("Text", "")
                    try:
                        column_values[col] = float(text)
                    except (ValueError, TypeError):
                        column_values[col] = text

            elif m_type == "matrix":
                positions = answers.get("SelectedByPosition", [])
                if not isinstance(positions, list):
                    positions = [positions]
                row_ids = mapping["row_ids"]
                col_fn = mapping["col_fn"]
                for i, val in enumerate(positions):
                    if i < len(row_ids):
                        try:
                            column_values[col_fn(row_ids[i])] = int(val)
                        except (ValueError, TypeError):
                            pass

            elif m_type == "matrix_sequential":
                positions = answers.get("SelectedByPosition", [])
                if not isinstance(positions, list):
                    positions = [positions]
                col_fn = mapping["col_fn"]
                for i, val in enumerate(positions):
                    try:
                        column_values[col_fn(i + 1)] = int(val)
                    except (ValueError, TypeError):
                        pass

            elif m_type == "slider_multi":
                values = answers.get("Values", [])
                if not isinstance(values, list):
                    values = [values]
                stmt_ids = mapping["stmt_ids"]
                col_fn = mapping["col_fn"]
                for i, val in enumerate(values):
                    if i < len(stmt_ids):
                        try:
                            column_values[col_fn(stmt_ids[i])] = float(val)
                        except (ValueError, TypeError):
                            pass

    return column_values


# ---------------------------------------------------------------------------
# Main prediction logic
# ---------------------------------------------------------------------------

def predict_participant(participant_id, condition, model_name, subjects_dir,
                        brief_path=None, dry_run=False):
    """Run predictions for one participant under one condition."""
    pdir = subjects_dir / f"participant_{participant_id}"

    # Load wave4_Q_w13A.json (ground truth = wave 1-3 answers)
    gt_file = pdir / "wave4_Q_w13A.json"
    if not gt_file.exists():
        print(f"  ERROR: No wave4_Q_w13A.json for participant {participant_id}")
        return None
    with open(gt_file, 'r', encoding='utf-8') as f:
        wave4_data = json.load(f)

    # Build question prompt (answers masked)
    question_text, question_metadata = build_question_text(wave4_data)
    n_questions = len(question_metadata)
    print(f"  {n_questions} questions formatted")

    # Load context based on condition
    brief_text = None
    full_persona_text = None

    if condition in ("C2", "C4"):
        if brief_path:
            bp = Path(brief_path)
        else:
            bp = pdir / "data" / "identity_layers" / "brief_v4.md"
            if not bp.exists():
                bp = pdir / "brief_v4.md"
            if not bp.exists():
                bp = pdir / "brief.md"
        if not bp.exists():
            print(f"  ERROR: No brief found at {bp}")
            return None
        brief_text = bp.read_text(encoding="utf-8")
        print(f"  Brief: {len(brief_text):,} chars")

    if condition in ("C3", "C4"):
        pt = pdir / "persona_text.txt"
        if not pt.exists():
            print(f"  ERROR: No persona_text.txt for participant {participant_id}")
            return None
        full_persona_text = pt.read_text(encoding="utf-8")
        print(f"  Full persona: {len(full_persona_text):,} chars")

    summary_text = None
    if condition == "C5":
        st = pdir / "persona_summary.txt"
        if not st.exists():
            print(f"  ERROR: No persona_summary.txt for participant {participant_id}")
            return None
        summary_text = st.read_text(encoding="utf-8")
        print(f"  Summary: {len(summary_text):,} chars")

    # Build full prompt
    prompt = build_prompt(condition, question_text,
                          brief_text=brief_text,
                          full_persona_text=full_persona_text,
                          summary_text=summary_text)
    print(f"  Prompt: {len(prompt):,} chars")

    if dry_run:
        print(f"\n--- DRY RUN: Prompt preview (first 2000 chars) ---")
        print(prompt[:2000])
        print(f"--- [truncated, {len(prompt):,} total chars] ---")
        return {"dry_run": True, "n_questions": n_questions,
                "prompt_chars": len(prompt), "metadata": question_metadata}

    # Call API
    print(f"  Calling {model_name}...")
    t0 = time.time()
    max_tok = 16000 if model_name in ("sonnet", "opus") else 8000
    response_text = call_model(prompt, model_name, max_tokens=max_tok)
    elapsed = time.time() - t0
    print(f"  Response: {len(response_text):,} chars in {elapsed:.1f}s")

    # Parse response
    parsed = parse_response_json(response_text)
    if parsed is None:
        print(f"  ERROR: Failed to parse JSON response")
        return {
            "participant_id": participant_id,
            "condition": condition,
            "model": model_name,
            "raw_response": response_text,
            "parse_error": True,
            "n_questions": n_questions,
        }

    n_parsed = sum(1 for k in parsed if k.startswith("Q"))
    print(f"  Parsed {n_parsed}/{n_questions} answers")

    # Map to scoring columns
    pred_columns = map_predictions_to_columns(parsed, question_metadata)
    gt_columns = extract_ground_truth_columns(wave4_data)

    # Also extract wave4 answers (human test-retest)
    wave4_qa_file = pdir / "wave4_QA.json"
    wave4_columns = {}
    if wave4_qa_file.exists():
        with open(wave4_qa_file, 'r', encoding='utf-8') as f:
            wave4_qa_data = json.load(f)
        wave4_columns = extract_ground_truth_columns(wave4_qa_data)

    return {
        "participant_id": participant_id,
        "condition": condition,
        "model": model_name,
        "n_questions": n_questions,
        "n_parsed": n_parsed,
        "raw_response": response_text,
        "parsed_json": parsed,
        "pred_columns": pred_columns,
        "gt_columns": gt_columns,
        "wave4_columns": wave4_columns,
        "question_metadata": {k: {"qid": v["qid"], "q_type": v["q_type"],
                                   "block_name": v["block_name"]}
                              for k, v in question_metadata.items()},
    }


def save_predictions(result, participant_id, condition, model_name):
    """Save prediction results."""
    rdir = RESULTS_DIR / f"participant_{participant_id}"
    rdir.mkdir(parents=True, exist_ok=True)

    filename = f"predictions_{condition}_{model_name}.json"
    out_file = rdir / filename

    # Save everything except the full question objects (too large)
    save_data = {k: v for k, v in result.items() if k != "question_metadata"}
    save_data["question_metadata"] = result.get("question_metadata", {})

    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(save_data, f, indent=2, ensure_ascii=False, default=str)

    print(f"  Saved to {out_file}")
    return out_file


def main():
    parser = argparse.ArgumentParser(description="Twin-2K-500 prediction harness (v2)")
    parser.add_argument("--participant", type=int, help="Participant index")
    parser.add_argument("--all", action="store_true", help="Run all downloaded participants")
    parser.add_argument("--condition", choices=["C1", "C2", "C3", "C4", "C5"],
                        help="Prediction condition")
    parser.add_argument("--all-conditions", action="store_true")
    parser.add_argument("--model", default="gpt-4.1-mini",
                        choices=list(MODELS.keys()))
    parser.add_argument("--brief-path", type=str,
                        help="Path to brief file (for C2)")
    parser.add_argument("--brief-dir", type=str,
                        help="Directory with briefs named participant_N/brief_v4.md")
    parser.add_argument("--subjects-dir", type=str, default=None)
    parser.add_argument("--dry-run", action="store_true",
                        help="Show prompt without calling API")
    args = parser.parse_args()

    subjects_dir = Path(args.subjects_dir) if args.subjects_dir else SUBJECTS_DIR

    # Determine participants
    if args.all:
        indices = sorted([
            int(d.name.split('_')[1])
            for d in subjects_dir.iterdir()
            if d.is_dir() and d.name.startswith('participant_')
            and (d / "wave4_Q_w13A.json").exists()
        ])
    elif args.participant is not None:
        indices = [args.participant]
    else:
        print("ERROR: Specify --participant N or --all")
        sys.exit(1)

    # Determine conditions
    if args.all_conditions:
        conditions = ["C1", "C2", "C3", "C4", "C5"]
    elif args.condition:
        conditions = [args.condition]
    else:
        print("ERROR: Specify --condition C1/C2/C3 or --all-conditions")
        sys.exit(1)

    print(f"Twin-2K-500 Prediction Harness v2")
    print(f"  Methodology: Digital-Twin-Simulation (1 prompt per participant)")
    print(f"  Participants: {len(indices)}")
    print(f"  Conditions: {conditions}")
    print(f"  Model: {args.model}")
    print(f"  Ground truth: wave4_Q_w13A.json (wave 1-3 answers)")
    print()

    for pid in indices:
        for condition in conditions:
            print(f"\n=== Participant {pid}, Condition {condition} ===")

            brief_path = args.brief_path
            if condition == "C2" and args.brief_dir and not brief_path:
                brief_path = Path(args.brief_dir) / f"participant_{pid}" / "brief_v4.md"

            result = predict_participant(
                pid, condition, args.model, subjects_dir,
                brief_path=brief_path, dry_run=args.dry_run,
            )
            if result and not args.dry_run and not result.get("dry_run"):
                save_predictions(result, pid, condition, args.model)

    print("\nDone. Run twin2k_score.py to score predictions.")


if __name__ == "__main__":
    main()
