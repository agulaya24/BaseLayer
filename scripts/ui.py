#!/usr/bin/env python3
"""
Base Layer Local UI — Drag-and-drop interface for running the pipeline.

Usage:
    baselayer ui              # Opens browser at http://localhost:3141
    baselayer ui --port 8080  # Custom port
"""

import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs

sys.path.insert(0, str(Path(__file__).parent))

PORT = 3141
pipeline_status = {
    "state": "idle",  # idle, running, done, error
    "step": "",
    "steps_done": 0,
    "steps_total": 6,
    "log": [],
    "brief": None,
    "error": None,
    "stats": None,
}


def get_html():
    """Return the single-page UI."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Base Layer</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif; background: #0a0a0f; color: #e0e0e8; min-height: 100vh; display: flex; flex-direction: column; align-items: center; padding: 3rem 1rem; }
h1 { font-size: 1.8rem; font-weight: 700; margin-bottom: 0.25rem; }
.subtitle { color: #888; font-size: 0.9rem; margin-bottom: 2rem; }
.container { width: 100%; max-width: 640px; }

.drop-zone {
    border: 2px dashed #333;
    border-radius: 12px;
    padding: 3rem 2rem;
    text-align: center;
    cursor: pointer;
    transition: all 0.2s;
    margin-bottom: 1.5rem;
}
.drop-zone:hover, .drop-zone.dragover { border-color: #60a5fa; background: #60a5fa10; }
.drop-zone.has-file { border-color: #4ade80; border-style: solid; }
.drop-zone h2 { font-size: 1.1rem; font-weight: 600; margin-bottom: 0.5rem; }
.drop-zone p { color: #888; font-size: 0.85rem; }
.drop-zone .filename { color: #4ade80; font-size: 1rem; font-weight: 600; }
input[type="file"] { display: none; }

.options { display: flex; gap: 0.75rem; margin-bottom: 1.5rem; flex-wrap: wrap; }
.option { display: flex; align-items: center; gap: 0.4rem; font-size: 0.85rem; color: #aaa; }
.option input { accent-color: #60a5fa; }
.option input[type="text"] { background: #13131a; border: 1px solid #333; border-radius: 4px; padding: 2px 8px; color: #e0e0e8; width: 140px; font-size: 0.85rem; }

.btn {
    width: 100%; padding: 0.85rem; border: none; border-radius: 8px;
    font-size: 1rem; font-weight: 600; cursor: pointer; transition: all 0.2s;
    background: #2563eb; color: #fff;
}
.btn:hover { background: #3b82f6; }
.btn:disabled { background: #333; color: #666; cursor: not-allowed; }

.progress { margin-top: 1.5rem; display: none; }
.progress.visible { display: block; }
.progress-bar { height: 6px; background: #1e1e2a; border-radius: 3px; overflow: hidden; margin-bottom: 0.75rem; }
.progress-fill { height: 100%; background: #60a5fa; transition: width 0.3s; border-radius: 3px; }
.progress-label { font-size: 0.85rem; color: #aaa; margin-bottom: 0.5rem; }

.log { background: #0d0d14; border: 1px solid #1e1e2a; border-radius: 8px; padding: 1rem; max-height: 200px; overflow-y: auto; font-family: 'SF Mono', 'Consolas', monospace; font-size: 0.78rem; line-height: 1.6; color: #888; margin-top: 0.75rem; }
.log .step { color: #60a5fa; }
.log .done { color: #4ade80; }
.log .err { color: #f87171; }

.result { margin-top: 1.5rem; display: none; }
.result.visible { display: block; }
.result-header { font-size: 1rem; font-weight: 600; color: #4ade80; margin-bottom: 0.75rem; }
.result-stats { display: flex; gap: 1rem; margin-bottom: 1rem; flex-wrap: wrap; }
.result-stat { background: #13131a; border: 1px solid #1e1e2a; border-radius: 8px; padding: 0.6rem 1rem; }
.result-stat .num { font-size: 1.2rem; font-weight: 700; color: #fff; }
.result-stat .label { font-size: 0.7rem; color: #888; text-transform: uppercase; }
.brief-preview { background: #0d0d14; border: 1px solid #1e1e2a; border-radius: 8px; padding: 1rem; font-size: 0.85rem; line-height: 1.7; color: #ccc; max-height: 300px; overflow-y: auto; white-space: pre-wrap; }

.next-steps { margin-top: 1.5rem; background: #13131a; border: 1px solid #1e1e2a; border-radius: 8px; padding: 1rem; }
.next-steps h3 { font-size: 0.9rem; font-weight: 600; margin-bottom: 0.5rem; }
.next-steps code { background: #1e1e2a; padding: 2px 6px; border-radius: 3px; font-size: 0.82rem; color: #60a5fa; }
.next-steps p { font-size: 0.85rem; color: #aaa; margin-bottom: 0.4rem; }
</style>
</head>
<body>
<div class="container">
<h1>Base Layer</h1>
<p class="subtitle">Drop your data. Get your identity brief.</p>

<div class="drop-zone" id="dropZone" onclick="document.getElementById('fileInput').click()">
    <h2 id="dropLabel">Drop file here or click to browse</h2>
    <p id="dropHint">ChatGPT export (.zip), text files (.txt, .md), or a folder</p>
</div>
<input type="file" id="fileInput" accept=".zip,.json,.txt,.md,.docx" onchange="fileSelected(this)">

<div class="options">
    <label class="option"><input type="checkbox" id="docMode"> Document mode</label>
    <label class="option" id="subjectWrap" style="display:none">Subject: <input type="text" id="subjectName" placeholder="Author name"></label>
</div>

<button class="btn" id="runBtn" onclick="startPipeline()" disabled>Run Pipeline</button>

<div class="progress" id="progress">
    <div class="progress-label" id="progressLabel">Starting...</div>
    <div class="progress-bar"><div class="progress-fill" id="progressFill" style="width:0%"></div></div>
    <div class="log" id="log"></div>
</div>

<div class="result" id="result">
    <div class="result-header">Your identity brief is ready.</div>
    <div class="result-stats" id="resultStats"></div>
    <div class="brief-preview" id="briefPreview"></div>
    <div class="next-steps">
        <h3>Next steps</h3>
        <p>Connect to Claude Code: <code>claude mcp add --transport stdio base-layer -- baselayer-mcp</code></p>
        <p>Interactive chat: <code>baselayer chat</code></p>
        <p>Review your facts: <code>baselayer review</code></p>
    </div>
</div>
</div>

<script>
let selectedFile = null;
const dropZone = document.getElementById('dropZone');
const runBtn = document.getElementById('runBtn');

document.getElementById('docMode').addEventListener('change', (e) => {
    document.getElementById('subjectWrap').style.display = e.target.checked ? '' : 'none';
});

['dragenter','dragover'].forEach(e => dropZone.addEventListener(e, (ev) => { ev.preventDefault(); dropZone.classList.add('dragover'); }));
['dragleave','drop'].forEach(e => dropZone.addEventListener(e, (ev) => { ev.preventDefault(); dropZone.classList.remove('dragover'); }));
dropZone.addEventListener('drop', (ev) => { if(ev.dataTransfer.files.length) fileSelected({files: ev.dataTransfer.files}); });

function fileSelected(input) {
    const file = input.files[0];
    if (!file) return;
    selectedFile = file;
    document.getElementById('dropLabel').innerHTML = '<span class="filename">' + file.name + '</span>';
    document.getElementById('dropHint').textContent = (file.size / 1024 / 1024).toFixed(1) + ' MB';
    dropZone.classList.add('has-file');
    runBtn.disabled = false;
}

function addLog(msg, cls) {
    const log = document.getElementById('log');
    const line = document.createElement('div');
    line.className = cls || '';
    line.textContent = msg;
    log.appendChild(line);
    log.scrollTop = log.scrollHeight;
}

async function startPipeline() {
    if (!selectedFile) return;
    runBtn.disabled = true;
    document.getElementById('progress').classList.add('visible');
    document.getElementById('result').classList.remove('visible');
    document.getElementById('log').innerHTML = '';

    const formData = new FormData();
    formData.append('file', selectedFile);
    formData.append('document_mode', document.getElementById('docMode').checked ? '1' : '0');
    formData.append('subject', document.getElementById('subjectName').value);

    addLog('Uploading ' + selectedFile.name + '...', 'step');

    try {
        const resp = await fetch('/upload', { method: 'POST', body: formData });
        const data = await resp.json();
        if (!data.ok) { addLog('Upload failed: ' + data.error, 'err'); return; }
        addLog('Uploaded. Starting pipeline...', 'done');
        pollStatus();
    } catch(e) {
        addLog('Error: ' + e.message, 'err');
    }
}

async function pollStatus() {
    const resp = await fetch('/status');
    const s = await resp.json();
    const pct = Math.round((s.steps_done / s.steps_total) * 100);
    document.getElementById('progressFill').style.width = pct + '%';
    document.getElementById('progressLabel').textContent = s.step || 'Working...';

    // Append new log lines
    const log = document.getElementById('log');
    const current = log.children.length;
    for (let i = current; i < s.log.length; i++) {
        const entry = s.log[i];
        addLog(entry[1], entry[0]);
    }

    if (s.state === 'done') {
        document.getElementById('progressFill').style.width = '100%';
        document.getElementById('progressFill').style.background = '#4ade80';
        document.getElementById('progressLabel').textContent = 'Complete!';
        showResult(s);
        runBtn.disabled = false;
    } else if (s.state === 'error') {
        document.getElementById('progressFill').style.background = '#f87171';
        document.getElementById('progressLabel').textContent = 'Error: ' + (s.error || 'Unknown');
        runBtn.disabled = false;
    } else {
        setTimeout(pollStatus, 1500);
    }
}

function showResult(s) {
    document.getElementById('result').classList.add('visible');
    if (s.stats) {
        const statsEl = document.getElementById('resultStats');
        statsEl.innerHTML = '';
        for (const [label, val] of Object.entries(s.stats)) {
            statsEl.innerHTML += '<div class="result-stat"><div class="num">' + val + '</div><div class="label">' + label + '</div></div>';
        }
    }
    if (s.brief) {
        document.getElementById('briefPreview').textContent = s.brief;
    }
}
</script>
</body>
</html>"""


class PipelineHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler for the local UI."""

    def log_message(self, format, *args):
        pass  # Suppress default logging

    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(get_html().encode())
        elif self.path == "/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(pipeline_status).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/upload":
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > 500 * 1024 * 1024:  # 500MB limit
                self._json_response({"ok": False, "error": "File too large (max 500MB)"})
                return

            # Parse multipart form data
            content_type = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in content_type:
                self._json_response({"ok": False, "error": "Expected multipart/form-data"})
                return

            import cgi
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": content_type},
            )

            if "file" not in form:
                self._json_response({"ok": False, "error": "No file uploaded"})
                return

            file_item = form["file"]
            doc_mode = form.getvalue("document_mode", "0") == "1"
            subject = form.getvalue("subject", "")

            # Save uploaded file to temp location
            upload_dir = Path(tempfile.mkdtemp(prefix="baselayer_"))
            # Sanitize filename — only keep alphanumeric, dots, hyphens, underscores
            safe_name = "".join(
                c for c in Path(file_item.filename).name
                if c.isalnum() or c in ".-_"
            ) or "upload.zip"
            upload_path = upload_dir / safe_name
            with open(upload_path, "wb") as f:
                f.write(file_item.file.read())

            # Start pipeline in background
            thread = threading.Thread(
                target=run_pipeline_thread,
                args=(str(upload_path), doc_mode, subject),
                daemon=True,
            )
            thread.start()

            self._json_response({"ok": True, "file": str(upload_path)})
        else:
            self.send_response(404)
            self.end_headers()

    def _json_response(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())


def log_step(cls, msg):
    """Add a log entry to the pipeline status."""
    pipeline_status["log"].append((cls, msg))


def run_pipeline_thread(file_path, document_mode, subject):
    """Run the full pipeline in a background thread."""
    global pipeline_status
    pipeline_status = {
        "state": "running",
        "step": "Initializing...",
        "steps_done": 0,
        "steps_total": 6,
        "log": [],
        "brief": None,
        "error": None,
        "stats": None,
    }

    try:
        # Build the baselayer run command
        cmd = [sys.executable, "-m", "cli", "run", file_path, "-y"]
        if document_mode:
            cmd.append("--document-mode")
            if subject:
                cmd.extend(["--subject", subject])

        scripts_dir = str(Path(__file__).parent)
        env = os.environ.copy()
        env["PYTHONPATH"] = scripts_dir

        process = subprocess.Popen(
            cmd,
            cwd=scripts_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )

        step_markers = {
            "Step 1/6": ("Initializing...", 0),
            "Step 2/6": ("Importing data...", 1),
            "Step 3/6": ("Estimating cost...", 2),
            "Step 4/6": ("Extracting facts...", 3),
            "Step 5/6": ("Processing pipeline...", 4),
            "Step 6/6": ("Authoring brief...", 5),
            "Done!": ("Complete!", 6),
        }

        for line in process.stdout:
            line = line.rstrip()
            if not line:
                continue

            # Check for step markers
            for marker, (label, n) in step_markers.items():
                if marker in line:
                    pipeline_status["step"] = label
                    pipeline_status["steps_done"] = n
                    log_step("step", label)
                    break
            else:
                # Regular log line
                if "Error" in line or "ERROR" in line:
                    log_step("err", line.strip())
                elif any(w in line for w in ["complete", "Stored", "Saved", "Generated", "Done"]):
                    log_step("done", line.strip())
                elif line.strip() and not line.strip().startswith("="):
                    log_step("", line.strip())

        process.wait()

        if process.returncode != 0:
            pipeline_status["state"] = "error"
            pipeline_status["error"] = "Pipeline exited with code %d" % process.returncode
            return

        # Read the brief
        from config import PROJECT_ROOT
        brief_path = PROJECT_ROOT / "data" / "identity_layers" / "brief_v4.md"
        if brief_path.exists():
            brief_text = brief_path.read_text(encoding="utf-8")
            if brief_text.startswith("---"):
                end = brief_text.find("---", 3)
                if end > 0:
                    brief_text = brief_text[end + 3:].strip()
            if brief_text.startswith("## Injectable Block"):
                brief_text = brief_text[len("## Injectable Block"):].strip()
            pipeline_status["brief"] = brief_text[:3000]

        # Get stats
        from config import DATABASE_FILE, get_db
        import contextlib
        if DATABASE_FILE.exists():
            with contextlib.closing(get_db()) as conn:
                facts = conn.execute("SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL").fetchone()[0]
                identity = conn.execute("SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL AND knowledge_tier='identity'").fetchone()[0]
                convos = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
            pipeline_status["stats"] = {
                "conversations": convos,
                "facts": facts,
                "identity": identity,
                "brief": "%d chars" % len(pipeline_status.get("brief") or ""),
            }

        pipeline_status["state"] = "done"
        pipeline_status["steps_done"] = 6
        pipeline_status["step"] = "Complete!"
        log_step("done", "Pipeline complete! Your identity brief is ready.")

    except Exception as e:
        pipeline_status["state"] = "error"
        pipeline_status["error"] = str(e)
        log_step("err", "Pipeline error: %s" % e)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Base Layer Local UI")
    parser.add_argument("--port", type=int, default=PORT, help="Port (default: %d)" % PORT)
    parser.add_argument("--no-browser", action="store_true", help="Don't auto-open browser")
    args = parser.parse_args()

    port = args.port
    server = http.server.HTTPServer(("127.0.0.1", port), PipelineHandler)
    url = "http://localhost:%d" % port

    print(f"\n  Base Layer UI running at {url}")
    print(f"  Press Ctrl+C to stop.\n")

    if not args.no_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Shutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
