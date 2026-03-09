# Security Audit — Session 41 (2026-02-25)

## Status: ADDRESSED

### HIGH Findings

1. **ZipSlip Vulnerability** — `import_conversations.py` line 467
   - `zf.extractall(tmpdir)` without path validation allowed ZIP entries with `../` to write outside temp directory
   - **FIX APPLIED:** Added path traversal check — each member's resolved path must start with tmpdir

2. **Raw Conversations Sent to API** — `extract_facts.py`
   - Extraction sends conversation text (up to 12K chars per conversation) to Anthropic API
   - This is a design decision (API extraction is faster/cheaper than local)
   - **FIX APPLIED:** Updated privacy claims across 7 docs to accurately describe what data leaves the machine

3. **No Privacy Disclosure Before API Calls** — `cli.py` cmd_extract()
   - Users not informed that conversation text will be sent to the API before extraction starts
   - **STATUS:** Open — add consent prompt in v1.1 (`baselayer extract` should warn first-time users)

### MEDIUM Findings

4. **Unpinned Dependencies** — `pyproject.toml`
   - Dependencies like `anthropic`, `chromadb`, `sentence-transformers` have no version pins
   - Could break on major version changes
   - **STATUS:** Open — pin before public release

5. **Soft-Delete Only** — `baselayer forget` marks facts as superseded, doesn't delete
   - Fact text remains in SQLite and ChromaDB
   - **STATUS:** Open — add hard delete option for v1.1

6. **No Export/Purge Commands** — Missing `baselayer export` and `baselayer purge`
   - Users can't export their data or fully purge it
   - **STATUS:** Open — add for v1.1

7. **Unencrypted Database** — SQLite and ChromaDB stored as plaintext files
   - Anyone with file access can read all personal data
   - **STATUS:** Acceptable for local storage tool — document in privacy section

8. **Entity Map Contains Personal Names** — `scripts/entity_map.json`
   - Name mappings stored in plaintext, not in .gitignore
   - **FIX APPLIED:** Added to .gitignore

9. **No Rate Limiting on MCP Server** — `mcp_server.py`
   - Could be flooded with requests if exposed on network
   - **STATUS:** Acceptable — binds to localhost only

### Changes Made

- `import_conversations.py`: ZipSlip protection added (path traversal check)
- `README.md`: Privacy section rewritten — extraction sends conversation text
- `PROJECT_OVERVIEW.md`: Privacy claim corrected
- `ARCHITECTURE.md`: Local/cloud split description corrected
- `BASE_LAYER_OVERVIEW.md`: Data sovereignty claim corrected
- `SLIDE_DECK.md`: Privacy note corrected
- `FEATURE_LIST.md`: Local-first description corrected
- `.gitignore`: Added `*.egg-info/`, `dist/`, `build/`, `entity_map.json`
