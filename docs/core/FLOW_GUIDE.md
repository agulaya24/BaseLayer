# Base Layer — User Flow Guide
## The Interpretive Layer Above Memory

## From Install to Brief Generation

### Step 1: Install
```
pip install git+https://github.com/agulaya24/BaseLayer.git
```
Downloads the package + dependencies (ChromaDB, sentence-transformers, Anthropic SDK). Base Layer is not on PyPI today (the `baselayer` name there is held by an unrelated project), so install from the GitHub source URL or clone the repo and `pip install -e .`.

### Step 2: Initialize
```
baselayer init
```
Creates your data directory (`~/.baselayer/`) with an empty database and vector store. All your data stays local on your machine.

### Step 3: Set Your API Key
```
export ANTHROPIC_API_KEY=sk-ant-...
```
Get your key at [console.anthropic.com](https://console.anthropic.com/). API key is required only for extract, author, and compose; every other step runs locally.

### Step 4: Import Your Data
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

### Step 5: Estimate Cost
```
baselayer estimate
```
Shows how much the pipeline will cost before you spend anything:
```
  Pending extraction:     827
  Estimated cost by model:
    Haiku 4.5    $   1.53 <-- default
    Sonnet 4     $   5.74
  Post-extraction pipeline: ~$0.60
```

### Step 6: Extract Facts
```
baselayer extract
baselayer extract --backend ollama    # use local Qwen instead of API
```
Reads every conversation, pulls out facts about you using AUDN (Add, Update, Delete, Noop) lifecycle operations. Uses 47 constrained predicates. Default uses Haiku API (fast, cheap). Local Ollama available for zero-cost extraction if you have a GPU.

### Step 7: Author Layers + Compose Brief
```
baselayer author --compose          # generate layers + compose specification (recommended)
baselayer author                    # generate layers only
baselayer author --layer core       # regenerate a single layer
baselayer compose                   # compose specification from existing layers
```
Generates three identity layers from your facts:
- **ANCHORS** - Your deepest beliefs and epistemic axioms
- **CORE** - Biographical foundation: who you are, who matters, what you've built
- **PREDICTIONS** - Behavioral patterns: how you'll react, decide, communicate

Then composes a behavioral specification from all three layers. Collective review (a multi-agent adversarial review process) was proven ceremonial in the Session 79 pipeline ablation study and removed from the default pipeline. The author step generates layers directly; the compose step creates the specification.

Pre-authored once, reused across every conversation.

**One-command version:**
```
baselayer run <file>
```
Runs the full pipeline (Import, Extract, Author, Compose) automatically with a cost estimate gate before spending.

### Step 8: Your Brief
```
baselayer brief "Help me write a cover letter"
```
Assembles a behavioral specification (the compressed document that teaches an AI how you think and communicate) tailored to the current message. **Prefers the composed specification** if available, a single compressed document that eval showed outperforms structured layer injection. Falls back to three-layer format if no specification exists:
- **Layer 1: Identity** (~3,500 tokens) - Three pre-authored layers (always present)
- **Layer 2: Themes** (~800 tokens) - Relevant facts retrieved by semantic similarity
- **Layer 3: Episodes** (~600 tokens) - Specific conversation memories

The brief gets injected into the AI's system prompt. The AI now knows you.

### Step 9: Connect to Your AI (MCP Server)
```
baselayer-mcp
```
Starts the MCP (Model Context Protocol) server that connects Base Layer to any MCP-compatible AI client.

**Claude Desktop** -- add to `claude_desktop_config.json`:
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
- **Identity layers** (Resource, always available) -- specification preferred, three-layer fallback (ANCHORS + CORE + PREDICTIONS)
- **recall_memories** (Tool, on-demand) -- AI calls this when it needs specific facts or episodes
- **search_facts** (Tool) -- keyword search across your fact database
- **trace_claim** (Tool) -- provenance trace from any identity layer claim back to source facts
- **get_stats** (Tool) -- database statistics
- **verify_claims** (Tool) -- verify identity layer claims against the fact base

The AI always knows who you are (identity layers). It pulls up specific memories only when the conversation calls for it.

---

## What Happens Under the Hood

```
Your Data ------> Import ------> Extract ------> Author Layers
(chats, notes,                                        |
 journals)                                        Compose Brief
                                                      |
                                                 MCP Server
                                                /          \
                                Specification Resource  recall_memories Tool
                                (always available)       (AI calls on demand)
                                      \                  /
                                       AI System Prompt
                                       (AI knows you)
```

## Cost Summary
| Step | Model | Estimated Cost |
|------|-------|---------------|
| Extract | Haiku (default) | ~$0.002/conversation |
| Author layers | Sonnet | ~$0.10-0.50 |
| Compose brief | Opus | ~$0.10-0.50 |
| Brief assembly | None (local) | Free |
| **Total (1,000 conversations)** | | **~$0.50-2.00** |

## Time Estimates
| Step | First Run | Subsequent |
|------|-----------|------------|
| Install | 2 min | - |
| Import | 30 sec | seconds (incremental) |
| Extract (Haiku) | 10-20 min | minutes (new only) |
| Author + Compose | 5-10 min | on-demand |
| Brief generation | <1 sec | <1 sec |
| **Full pipeline** | **~30 min** | **minutes (incremental)** |

## Requirements
- **Python 3.10+**
- **Anthropic API key** - for extraction, layer authoring, and brief composition (`export ANTHROPIC_API_KEY=sk-...`)
- **Ollama + Qwen 2.5 14B** (optional) - for local extraction without API costs
- **~2GB disk** - for embeddings model + vector store
