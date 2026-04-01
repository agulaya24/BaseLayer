# MCP Registry Submissions — Ready to Submit

**Created:** S101 (2026-03-31)
**Status:** Submission data prepped. Submit manually from browser.

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
  "description": "Personal AI memory — behavioral compression for identity. Serves structured identity models via MCP: epistemic axioms, communication modes, behavioral predictions, and provenance-traced fact retrieval.",
  "vendor": "Base Layer",
  "sourceUrl": "https://github.com/agulaya24/BaseLayer",
  "homepage": "https://base-layer.ai",
  "license": "Apache-2.0",
  "runtime": "python",
  "transport": ["stdio"],
  "install": {
    "pip": "pip install baselayer",
    "command": "baselayer-mcp"
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
- [Base Layer](https://github.com/agulaya24/BaseLayer) - Behavioral compression for AI identity. Extracts patterns from text, compresses into 3-layer identity model (anchors, core, predictions), serves via MCP. 47-predicate grammar, provenance-traced, 44+ subjects validated.
```

**Notes:** Fork branches already exist from S100. Check if PRs were submitted.

---

## Submission Checklist

- [ ] Smithery — submit repo URL
- [ ] Glama — submit repo URL (may auto-discover)
- [ ] Official MCP Registry — open PR
- [ ] awesome-mcp-servers — open PR (check if fork branch exists)
