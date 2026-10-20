# MCP registry and directory listings

Where the Base Layer MCP server is listed, what each registry requires, and what is still
open. Checked 2026-10-19 and 2026-10-20 against each registry's API or page and against
GitHub. Re-check before relying on any line: registries change their rules often.

The server is the stdio command `baselayer-mcp`. It serves a `baselayer run` build: eight
tools (`recall_memories`, `search_facts`, `trace_claim`, `verify_claims`, `get_brief`,
`get_stats`, `get_call_log`, `get_help`) and two resources (`memory://specification`,
`memory://identity`). A cited build is not served by it.

## Status

| registry | listed | how listing works | what is needed |
|---|---|---|---|
| Official MCP Registry (registry.modelcontextprotocol.io) | No. The registry API returned 0 servers for `agulaya24`. | A `server.json` published with the `mcp-publisher` CLI under the `io.github.agulaya24/` namespace (GitHub login) or a DNS-verified namespace. Every entry must point at a package in a supported registry (npm, PyPI, NuGet, Cargo, OCI image or an MCPB bundle). There is no git-URL package type. | A package. Base Layer is not on PyPI, and the `baselayer` name there belongs to another project, so this needs a decision: PyPI under another name, an OCI image, or an MCPB bundle. |
| Glama (glama.ai/mcp) | Crawled from GitHub, unclaimed, and marked as unable to deploy. Its text comes from an old README. | Glama builds the server from a Dockerfile in the repository, introspects it over MCP and scores it. A listing becomes discoverable only after a reproducible build succeeds. The owner claims it with a `glama.json` file or a GitHub login. | The `Dockerfile`, `.dockerignore` and `glama.json` in this repository. Then the owner claims the listing and starts a build on Glama. |
| Smithery (smithery.ai) | No. | A hosted Streamable HTTP server, or a stdio server packaged as an MCPB bundle. | An MCPB bundle (it would also serve the official registry). |
| PulseMCP | No. | Not accepting direct submissions. It picks up servers from the official registry. | An official registry entry. |
| GitHub MCP registry | No. | Follows official registry entries. | An official registry entry. |
| mcp.so | No. | A submission form for the repository URL. | The form, if wanted. |

## Lists

| list | status |
|---|---|
| punkpeye/awesome-mcp-servers | PR #4402 was closed unmerged on 2026-05-27. Entries there carry a Glama score badge, so a new PR needs the Glama listing first. |
| e2b-dev/awesome-ai-agents | PR #730 is open under the retired title "behavioral compression for AI agents". Update or close it. |
| steven2358/awesome-generative-ai | PR #581 is open under the same retired title. Update or close it. |

## Earlier versions of this file

Earlier versions described every registry above as listing Base Layer, gave the official
registry route as a pull request to `modelcontextprotocol/servers`, said the punkpeye entry
had been added, and repeated registry sizes and a "46-predicate extraction vocabulary"
without sources. None of that is current.
