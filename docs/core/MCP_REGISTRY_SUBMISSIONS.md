# MCP Registry Submissions

Registries where the Base Layer MCP server is listed, with the repo URL and
submission payload for each.

---

## 1. Smithery (smithery.ai)

**URL:** https://smithery.ai/submit
**How:** Submit GitHub repo URL. Smithery auto-indexes from README + package metadata.

**Submit:**
- Repository: `https://github.com/agulaya24/BaseLayer`
- The repo already has AGENTS.md and MCP server docs in README

**Notes:** Smithery has 7,300+ servers. Agents query it at runtime. High priority.

---

## 2. Glama (glama.ai/mcp)

**URL:** https://glama.ai/mcp/submit (or auto-crawls GitHub)
**How:** Submit GitHub repo URL or wait for auto-crawl.

**Submit:**
- Repository: `https://github.com/agulaya24/BaseLayer`
- Glama auto-crawls repos with MCP server implementations
- 19,000+ indexed servers

**Notes:** May auto-discover from GitHub topics (`mcp`, `mcp-server` tags already set).

---

## 3. Official MCP Registry (registry.modelcontextprotocol.io)

**URL:** https://github.com/modelcontextprotocol/servers
**How:** PR to the `servers` repo adding Base Layer.

**PR content for `src/base-layer/`:**

```json
{
  "name": "base-layer",
  "description": "The interpretive layer above memory. Serves a portable behavioral specification via MCP: epistemic axioms, communication modes, behavioral predictions, and provenance-traced fact retrieval.",
  "vendor": "Base Layer",
  "sourceUrl": "https://github.com/agulaya24/BaseLayer",
  "homepage": "https://base-layer.ai",
  "license": "Apache-2.0",
  "runtime": "python",
  "transport": ["stdio"],
  "install": {
    "pip": "pip install git+https://github.com/agulaya24/BaseLayer.git",
    "command": "baselayer-mcp",
    "note": "Base Layer is not on PyPI; the baselayer name is held by an unrelated project. Install from the GitHub URL above."
  },
  "resources": ["memory://identity"],
  "tools": ["recall_memories", "search_facts", "trace_claim", "get_stats"],
  "tags": ["memory", "identity", "personalization", "behavioral-compression"]
}
```

**Notes:** MCP donated to Linux Foundation Dec 2025. IDE integrations (Claude Desktop, Cursor, VS Code) query this registry natively. Highest impact for developer discovery.

---

## 4. awesome-mcp-servers (GitHub)

**URL:** https://github.com/punkpeye/awesome-mcp-servers
**How:** PR adding Base Layer to the list.

**Entry (add under "Memory / Knowledge" or similar section):**
```markdown
- [Base Layer](https://github.com/agulaya24/BaseLayer) - The interpretive layer above memory. Extracts behavioral patterns from text, compresses into a 3-layer specification (anchors, core, predictions), serves via MCP. 46-predicate extraction vocabulary, provenance-traced, 44+ subjects validated.
```

**Notes:** Added under the "Memory / Knowledge" section.

---

## Registry list

- Smithery — https://smithery.ai/submit (repo URL)
- Glama — https://glama.ai/mcp/submit (repo URL; may auto-discover)
- Official MCP Registry — https://github.com/modelcontextprotocol/servers (PR)
- awesome-mcp-servers — https://github.com/punkpeye/awesome-mcp-servers (PR)
