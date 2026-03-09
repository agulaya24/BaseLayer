# Base Layer - User Flow Guide

## From Install to Brief Generation

### Step 1: Install
```
pip install baselayer
```
Downloads the package + dependencies (ChromaDB, sentence-transformers, Anthropic SDK).

### Step 2: Initialize
```
baselayer init
```
Creates your data directory (`~/.baselayer/`) with an empty database and vector store. All your data stays local on your machine.

### Step 3: Set Your API Key
```
export ANTHROPIC_API_KEY=sk-ant-...
```
Required for extraction (Step 5), processing (Step 6), and layer authoring (Step 7). Get your key at [console.anthropic.com](https://console.anthropic.com/). Steps 1-4 and 8-9 work without it.

### Step 4: Import Your Data (no API key needed)
```
baselayer import chatgpt-export.zip
baselayer import claude-export.json
baselayer import ~/Documents/personal-notes/
baselayer import my-journal.txt
```
Supports multiple input types:
- **ChatGPT exports** (.zip or conversations.json)
- **Claude exports** (.json from claude.ai)
- **Text files** (.txt, .md, .docx) - personal notes, journals, reflections
- **Directories** - bulk import all text files in a folder

Personal notes and journals tend to produce the highest quality identity data because they're self-reflective by nature.

### Step 5: Estimate Cost (no API key needed)
```
baselayer estimate
```
Shows how much extraction will cost before you spend anything:
```
  Pending extraction:     827
  Estimated cost by model:
    Haiku 4.5    $   1.53 <-- default
    Sonnet 4     $   5.74
  Post-extraction pipeline: ~$2.10
```

### Step 6: Extract Facts
```
baselayer extract
baselayer extract --backend ollama    # use local Qwen instead of API
```
Reads every conversation, pulls out facts about you (Add, Update, Delete, Noop operations). Default uses Haiku API (fast, cheap). Local Ollama available for zero-cost extraction if you have a GPU.

### Step 7: Process
```
baselayer process
```
Runs the full pipeline:
1. **Embed** - Vector embeddings for semantic search (local, free)
2. **Score** - Novelty + significance scoring
3. **Classify** - Tags facts by type and commitment depth (Haiku API)
4. **Tier** - Assigns knowledge tier: context, situational, or identity (Sonnet API)

### Step 8: Build Identity Layers
```
baselayer author                    # generate + automated review (default)
baselayer author --no-review        # generate only, skip review
baselayer author --layer core       # regenerate a single layer
baselayer author --compose          # generate layers + compose unified brief
baselayer compose                   # compose unified brief from existing layers
```
Generates three identity layers from your facts with automated quality review:
- **ANCHORS** - Your deepest beliefs and epistemic axioms
- **CORE** - Biographical foundation: who you are, who matters, what you've built
- **PREDICTIONS** - Behavioral patterns: how you'll react, decide, communicate

Review pipeline adapts to data density: self-review only for thin data (<100 facts), single Opus pass for moderate (100-500), iterative Opus review for dense (500+). Always deploys the best version generated.

Pre-authored once, reused across every conversation.

### Step 9: Generate a Brief (no API key needed)
```
baselayer brief "Help me write a cover letter"
```
Assembles a behavioral brief tailored to the current message. **Prefers the unified narrative brief** (`brief_v4.md`, ~3,723 tokens) if available — a single compressed document that eval proved dramatically outperforms structured layer injection (+0.40 vs baseline). Falls back to three-layer format if no unified brief exists:
- **Layer 1: Identity** (~3,500 tokens) - Three pre-authored layers (always present)
- **Layer 2: Themes** (~800 tokens) - Relevant facts retrieved by semantic similarity
- **Layer 3: Episodes** (~600 tokens) - Specific conversation memories

The brief gets injected into the AI's system prompt. The AI now knows you.

### Step 10: Connect to Your AI (MCP Server, no API key needed)
```
baselayer-mcp
```
Starts the MCP server that connects Base Layer to any MCP-compatible AI client.

**Claude Desktop** — add to `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "base-layer": {
      "command": "baselayer-mcp"
    }
  }
}
```

**Claude Code:**
```
claude mcp add --transport stdio base-layer -- baselayer-mcp
```

**What the AI gets:**
- **Identity layers** (Resource, always available) — unified brief preferred, three-layer fallback (ANCHORS + CORE + PREDICTIONS)
- **recall_memories** (Tool, on-demand) — AI calls this when it needs specific facts or episodes
- **search_facts** (Tool) — keyword search across your fact database
- **trace_claim** (Tool) — provenance trace from any identity layer claim back to source facts
- **get_stats** (Tool) — database statistics
- **verify_claims** (Tool) — verify identity layer claims against the fact base

The AI always knows who you are (identity layers). It pulls up specific memories only when the conversation calls for it.

---

## What Happens Under the Hood

```
Your Data ------> Import ------> Extract ------> Score + Classify + Tier
(chats, notes,                                          |
 journals)                               Contradictions <
                                                |
                                          Consolidate
                                                |
                                    Author Layers (+ review)
                                                |
                                          MCP Server
                                         /          \
                          Identity Resource       recall_memories Tool
                          (always available)       (AI calls on demand)
                                \                  /
                                 AI System Prompt
                                 (AI knows you)
```

## Cost Summary
| Step | Model | Estimated Cost |
|------|-------|---------------|
| Extract | Haiku (default) | ~$0.002/conversation |
| Classify | Haiku | ~$1 total |
| Tier | Sonnet | ~$1 total |
| Author layers | Sonnet + review | ~$0.15 (thin) to ~$3-5 (dense) |
| Brief assembly | None (local) | Free |
| **Total (1,000 conversations)** | | **~$5-8** |

## Time Estimates
| Step | First Run | Subsequent |
|------|-----------|------------|
| Install | 2 min | - |
| Import | 30 sec | seconds (incremental) |
| Extract (Haiku) | 10-20 min | minutes (new only) |
| Process | 10-30 min | minutes |
| Author layers | 1 min | on-demand |
| Brief generation | <1 sec | <1 sec |

## Requirements
- **Python 3.10+**
- **Anthropic API key** - for extraction, classification, tier assignment, and layer authoring (`export ANTHROPIC_API_KEY=sk-...`)
- **Ollama + Qwen 2.5 14B** (optional) - for local extraction without API costs
- **~2GB disk** - for embeddings model + vector store
