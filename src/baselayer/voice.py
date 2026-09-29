"""Voice-class detectors for the turn contract (docs/core/TURN_CONTRACT.md, section 2).

Every function here is deterministic: no model call, no network, no file read. Each
detector is named by a stable string that the importer writes to the turn table's
``detector`` column, so an audit can count what each rule removed.

Two kinds of rule live here:

* Record rules decide a whole source record from the source's own fields
  (``isCompactSummary``, ``promptSource``, ``entrypoint``, ``tool_result`` blocks,
  ``queued_command`` attachments). They are exact.
* Text rules split a subject turn into segments and mark pasted segments
  (quote-back overlap with the preceding assistant text, paste tags, structural
  signals). On a long turn a second pass (``document_spans``) reads the whole turn for
  documents the per-segment scores miss. They are heuristics, and every pasted segment
  keeps its own turn id so the subject can allowlist it later.

Subject-specific signals (the subject's name in a greeting, personal misspellings,
typographic habits such as never typing an em-dash) are NOT hard-coded. They come from
the local import config (``baselayer.import_config``), which lives outside the
repository.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

TURN_CONTRACT_VERSION = "turn-contract/1"

SPEAKERS = ("subject", "assistant", "other", "system")

CITABLE_VOICE_CLASSES = ("own_typed", "own_dictated")
CONTEXT_VOICE_CLASSES = (
    "assistant",
    "other_person",
    "pasted",
    "compaction_summary",
    "tool_result",
    "harness_prompt",
    "queued_command",
)
VOICE_CLASSES = CITABLE_VOICE_CLASSES + CONTEXT_VOICE_CLASSES

# Detector names. Stable strings: they are written to the database and counted.
D_COMPACT_FLAG = "source:isCompactSummary"
D_COMPACT_TEXT = "text:compaction_signature"
D_TOOL_RESULT_BLOCK = "source:tool_result_block"
D_TOOL_RESULT_PLACEHOLDER = "text:tool_result_placeholder"
D_SDK_PROMPT = "source:promptSource=sdk"
D_SDK_CLI_NO_HUMAN = "source:entrypoint=sdk-cli,no_human_origin"
D_HARNESS_CWD = "config:harness_cwd"
D_HARNESS_REPLAY = "harness:replay_of_subject_text"
D_SYSTEM_ORIGIN = "source:system_origin"
D_IS_META = "source:isMeta"
D_CROSS_AGENT = "text:cross_agent_relay"
D_CHATGPT_SYSTEM = "source:role=system"
D_CHATGPT_TOOL = "source:role=tool"
D_PASTE_QUOTE_BACK = "paste:quote_back"
D_PASTE_TAG = "paste:tag"
D_PASTE_STRUCTURAL = "paste:structural"
D_PASTE_TEMPLATE = "paste:harness_template"
D_PASTE_TERMINAL = "paste:terminal"
D_PASTE_DOCUMENT = "paste:document"
D_PASTE_QUOTE_BACK_EARLIER = "paste:quote_back_earlier"
D_PASTE_CODE_MACHINE = "paste:code_or_machine"

# Basis names for citable rows (detector stays NULL on those, per the contract).
B_ROLE = "source:role"
B_QUEUED = "recovered:queued_command"
# A queued prompt an older client wrote with no origin at all. Admitted only when the local
# config sets include_originless_queued (off by default: the subject has not decided).
B_QUEUED_NO_ORIGIN = "recovered:queued_no_origin"
B_DICTATION = "text:dictation_score"
B_AUDIO = "source:audio_transcription"
B_MEETING_LABEL = "config:meeting_subject_label"
B_ALLOWLIST = "config:allowlist"

TOOL_RESULT_PLACEHOLDER = "[tool result]"


# --------------------------------------------------------------------------- text utils

def norm_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def norm_hash(s: str) -> str:
    return hashlib.sha256(norm_text(s).encode("utf-8", "surrogatepass")).hexdigest()[:16]


_WORDS_RE = re.compile(r"[a-z0-9']+")


def shingles(text: str, k: int = 6) -> set:
    w = _WORDS_RE.findall((text or "").lower())
    return {" ".join(w[i:i + k]) for i in range(max(0, len(w) - k + 1))}


# --------------------------------------------------------------------------- wrappers

# Harness wrapper blocks, matched anywhere in the body. Superset of the list the live
# install's claude_code_filters carries (adds command-args, local-command-caveat and the
# IDE selection tags, which the transcript-filter prototype found in real transcripts).
BLOCK_RE = re.compile(
    r"<system-reminder>.*?</system-reminder>"
    r"|<teammate-message\b.*?</teammate-message>"
    r"|<command-name>.*?</command-name>"
    r"|<command-message>.*?</command-message>"
    r"|<command-args>.*?</command-args>"
    r"|<local-command-stdout>.*?</local-command-stdout>"
    r"|<local-command-caveat>.*?</local-command-caveat>"
    r"|<task-notification>.*?</task-notification>"
    r"|<ide_(?:opened_file|selection)>.*?</ide_(?:opened_file|selection)>",
    re.S | re.I,
)
LINE_NOISE_RE = re.compile(
    r"^\s*(?:\[Request interrupted[^\]]*\]"
    r"|\[Image:[^\]]*\]"
    r"|Caveat:.*"
    r"|\[SYSTEM NOTIFICATION.*"
    r"|This came from another Claude session.*)$",
    re.M | re.I,
)
CROSS_AGENT_RE = re.compile(r"Another Claude session sent a message:", re.I)
SLASH_CMD_RE = re.compile(r"^\s*/[a-z][\w-]*(\s+\S.*)?\s*$", re.I | re.S)
# Older clients wrote compaction summaries as a plain user record without the flag.
COMPACTION_TEXT_RE = re.compile(
    r"^\s*This session is being continued from a previous conversation that ran out of context",
    re.I,
)


def strip_wrappers(text: str) -> str:
    return LINE_NOISE_RE.sub("", BLOCK_RE.sub("", text or "")).strip()


def is_tool_result_placeholder(text: str) -> bool:
    return (text or "").strip() == TOOL_RESULT_PLACEHOLDER


# --------------------------------------------------------------------------- features

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z']*")
# Generic typing artifacts only. Subject-specific misspellings come from config.
_GENERIC_TYPOS = {
    "hte", "teh", "adn", "taht", "wiht", "waht", "thsi", "tihs", "jsut", "liek", "becuase",
    "becasue", "recieve", "seperate", "definately", "occured", "untill", "wich", "whihc",
    "thier", "tehy", "yuo", "yoru", "cna", "thign", "thigns", "htis", "shoudl", "woudl",
    "coudl", "thna",
}
_APOS_LESS_RE = re.compile(
    r"\b(dont|cant|wont|im|ive|thats|whats|isnt|doesnt|didnt|wouldnt|shouldnt|couldnt|lets|"
    r"youre|theyre|wasnt|arent|havent|hasnt|werent|theres|heres|hows|whos|itll|thatll)\b")
_LOWER_I_RE = re.compile(r"(?:^|\s)i(?=\s|'|$)")
_SPACE_PUNCT_RE = re.compile(r"\w \.(?:\s|$)|\w ,\s|\w \?(?:\s|$)")
_CENSOR_RE = re.compile(r"\*{3,}")
_MIDCAP_RE = re.compile(
    r"[a-z,]\s+(?:If|The|That|This|You|We|It|So|And|But|Right|Yeah|Also|Is|Are|Do|How|What|"
    r"Part|There|Then|Now|Well|Which|When|Where|Why|Because|Maybe|Something|Anyway|Basically|"
    r"Like|Just|Not|Or|Even|Yes|No|Okay|Ok|Would|Could|Should|Does|Did|Can|Hey)\b(?![.,:;!?])",
)
_EMDASH_RE = re.compile("\u2014")
_CURLY_RE = re.compile("[\u201c\u201d\u2018\u2019]")
_TYPOGRAPHIC_RE = re.compile("[\u2022\u2192\u00d7\u2713\u2717\u25b8\u25aa]")
_TERMINAL_RE = re.compile("^\\s*(\u276f|\u23bf|\\$ |> /|PS [A-Z]:\\\\)", re.M)
_CHATUI_RE = re.compile(
    r"^(Viewed \d+ files?|Ran a command|Searched the web|Thought for \d+|ChatGPT said:|"
    r"You said:|Copy code)\b", re.M)
_EMAIL_HDR_RE = re.compile(r"^(From|To|Subject|Sent|Date|Cc|Bcc|Reply-To):\s", re.M | re.I)
_GREETING_RE = re.compile(r"^\s*(Hi|Hello|Hey|Dear)\s+[A-Z][\w.'-]*[,!-]?", re.M)
_CHAT_TS_RE = re.compile(r"\[\d{1,2}:\d{2}\s?(?:AM|PM)\]|\b\d{1,2}:\d{2}\s?(?:AM|PM)\s*(\(|$)",
                         re.I | re.M)
_MD_STRUCT_RE = re.compile(r"^(#{1,6}\s|\s*[-*\u2022]\s|\s*\d+[.)]\s|\|.*\||>\s)", re.M)
_FENCE_RE = re.compile(r"```")
_LOG_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}|Traceback \(most recent|^\s*(ERROR|WARN|INFO|DEBUG)\b"
    r"|^\s*at \w+\.\w+\(|\[SUCCEEDED\]|\[FAILED\]", re.M)
_CODE_RE = re.compile(
    r"^\s*(def |import |from \w+ import|class \w+[:(]|function |const |let |#include|<\?xml"
    r"|<html|\{\s*$|\}\s*$)", re.M)
_SIGNOFF_RE = re.compile(
    r"^\s*(Best|Regards|Best regards|Kind regards|Thanks|Thank you|Cheers|Sincerely|Warmly)[,!]?\s*$",
    re.M | re.I)
# Separators: blank lines, and runs of 3+ hyphens even when typed directly against a word
# ("see this---From: ..."), which is how a pasted block is often introduced.
_SEP_RE = re.compile(r"-{3,}|\n\s*\n")
_QUOTED_BLOCK_RE = re.compile(r'"([^"]{300,})"', re.S)
# ---- pasted terminal sessions -------------------------------------------------------
# A pasted terminal session is mostly box-drawing frames, gutter-numbered source lines,
# prompts and error records. None of those carry the prose signals paste_score counts, so
# a long paste split on blank lines scored segment by segment as the subject's own text.
# These rules classify LINES; a segment is a terminal paste when enough of its lines are
# machine output (see is_terminal_segment). Database copies store box-drawing characters
# as literal escape text (backslash, "u2502"), so both forms are matched.
_BOX_RE = re.compile("[─-╿]" + r"|\\u25[0-7][0-9a-fA-F]")
_ANSI_RE = re.compile("\x1b" + r"\[[0-9;]*[A-Za-z]|\\x1b\[|\\u001b\[|\\033\[")
_MACHINE_LINE_RE = re.compile(
    r"^\s*(?:PS [A-Za-z]:\\[^>\n]*>|[A-Za-z]:\\[^>\s]*>\s|\$ \S|[\w.-]+@[\w.-]+:[^\n$#]{0,200}[$#] "
    "|❯ |➜ |>>> " + r"|\((?:\.?venv|base)\) )"
    r"|^\s*File \"[^\"\n]+\", line \d+"
    r"|Traceback \(most recent call last\)"
    r"|^\s+at [\w$.<>\[\]/]+ ?\([^\n]*:\d+(?::\d+)?\)\s*$"
    r"|^\s*[A-Z]\w*(?:Error|Exception|Warning)(?::|\s*$)"
    r"|^\s*[\^~]{3,}\s*$"
    r"|At line:\d+ char:\d+"
    r"|^\s*\+ (?:CategoryInfo|FullyQualifiedErrorId|~)"
    r"|^\s*\[?\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}"
    r"|^\s*\[?(?:ERROR|WARN(?:ING)?|INFO|DEBUG|CRITICAL|TRACE)\b[\]:\s]"
    r"|^\s*(?:npm|pip|yarn|pnpm) (?:ERR!|WARN|error|notice)"
    r"|^={3,}[^\n]*={3,}\s*$"
    r"|^\s*\d+ (?:passed|failed|errors?|skipped)\b"
    r"|\b(?:PASSED|FAILED|XFAIL|ERROR) *\[ *\d+%\]"
    r"|^\s*(?:modified|new file|deleted|renamed|both modified):\s"
    r"|^(?:On branch |Your branch |Changes (?:not staged|to be committed)|Untracked files:|nothing to commit)"
    r"|^\[[\w/.-]+ [0-9a-f]{7,}\]"
    r"|^\s*\d+ files? changed"
    r"|^\s*(?:create|delete) mode \d{6}"
    r"|^\s*\d{1,5}\s*\|\s"
    r"|^\s*[d-](?=[rwxa-]*-)[rwxa-]{4,9}\s+\d"
    r"|^\s*(?:Directory: |Mode\s+LastWriteTime)"
    r"|^\s*(?:[A-Za-z]:[\\/]|/|~/|\.\.?/)\S*[\\/]\S*\s*$"
)
_PROSE_LINE_RE = re.compile(r"[A-Za-z][A-Za-z']*")


def is_machine_line(line: str) -> bool:
    if _MACHINE_LINE_RE.search(line):
        return True
    if not _BOX_RE.search(line):
        return False
    # A long typed sentence with a terminal frame drawn across its end (a companion's
    # speech-bubble border, say) is still a sentence: box characters make a line machine
    # output only when what is left is not twelve or more words of prose.
    return not _reads_as_prose(_BOX_RE.sub(" ", line), min_words=12)


# Characters that mark a line as code or a path rather than a sentence.
_CODEISH_RE = re.compile(r"[\\/_=(){}<>]|\w\.\w")


def _reads_as_prose(text: str, min_words: int) -> bool:
    t = text.strip()
    if not t or _CODEISH_RE.search(t):
        return False
    words = _PROSE_LINE_RE.findall(t)
    letters = sum(1 for ch in t if ch.isalpha() or ch.isspace())
    return len(words) >= min_words and letters >= 0.8 * len(t)


def _is_prose_line(line: str) -> bool:
    """A line a person typed as a sentence: four or more words, mostly letters, no code.
    A line carrying an ANSI escape is terminal output, never a typed sentence."""
    return (not _ANSI_RE.search(line) and not is_machine_line(line)
            and _reads_as_prose(line, min_words=4))


def is_terminal_segment(seg: str) -> bool:
    """True when a segment reads as pasted terminal output: an ANSI escape anywhere, or
    at least 3 machine lines making up 40% or more of its non-empty lines, or 12 or more
    machine lines whatever the share (a long session with prose-looking code between)."""
    if _ANSI_RE.search(seg):
        return True
    lines = [ln for ln in seg.split("\n") if ln.strip()]
    m = sum(1 for ln in lines if is_machine_line(ln))
    return m >= 12 or (m >= 3 and m >= 0.4 * len(lines))


def terminal_prose_margins(seg: str):
    """-> (lead_end, tail_start) char offsets: prose lines typed directly above or below a
    terminal paste, with no blank line between, stay the subject's own. Only the leading
    and trailing runs are rescued; prose-looking lines inside the paste are part of it."""
    lines = seg.split("\n")
    offs, pos = [], 0
    for ln in lines:
        offs.append(pos)
        pos += len(ln) + 1
    i = 0
    while i < len(lines) and (_is_prose_line(lines[i]) or (not lines[i].strip() and i > 0)):
        i += 1
    lead_end = offs[i] if i < len(lines) else len(seg)
    j = len(lines)
    while j > i and (_is_prose_line(lines[j - 1]) or not lines[j - 1].strip()):
        j -= 1
    tail_start = offs[j] if j < len(lines) else len(seg)
    if not any(_is_prose_line(ln) for ln in lines[:i]):
        lead_end = 0
    if not any(_is_prose_line(ln) for ln in lines[j:]):
        tail_start = len(seg)
    return lead_end, tail_start


# ---- code and machine output ----------------------------------------------------------
# Design decision: code and machine output inside the subject's own turn is not their words.
# The structural score needs several prose signals at once and the terminal rule needs
# three or more terminal lines, so a short code block, a JSON response, a config fragment
# or a single command between typed sentences stayed own. These rules classify LINES as
# code/machine (C), the subject's prose (P) or neutral (N); code_machine_spans turns runs
# of C and N lines that contain a C line into pasted spans, and P lines stay own.

# Terminal-rule lines that are not machine output on their own: a line opening with a date
# and time, a count of passed/failed things, and "$ <digit>" are how people type journal
# and trade notes. They still count toward a terminal paste (three or more lines).
_CM_TERMINAL_AMBIGUOUS_RE = re.compile(
    r"^\s*\[?\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}|^\s*\d+ (?:passed|failed|errors?|skipped)\b"
    r"|^\s*\$ \d")
# Lines that are code or machine output whatever words they carry.
_CM_HARD_RE = re.compile(
    r"^\s*(?:async\s+)?def\s+\w+\s*\("
    r"|^\s*class\s+\w+\s*[(:{]"
    r"|^\s*for\s+\w+(?:\s*,\s*\w+)?\s+in\s+[\w.]+(?:\(.*\))?\s*:\s*$"
    r"|^\s*import\s+[\w.]+(?:\s*,\s*[\w.]+)*(?:\s+as\s+\w+)?\s*;?\s*$"
    r"|^\s*from\s+[\w.]+\s+import\s+[\w*(]"
    r"|^\s*#include\s*[<\"]|^\s*#!/"
    r"|^\s*<\?xml\b|^\s*<!DOCTYPE\b|^\s*<!--"
    r"|^\s*</?[A-Za-z][\w:.-]*(?:\s+[\w:.-]+\s*=\s*(?:\"[^\"]*\"|'[^']*'))*\s*/?>(?:.*>)?\s*$"
    r"|\{\s*\"[^\"\n]+\"\s*:"
    r"|^\s*\"[^\"\n]+\"\s*:\s*(?:\"|-?\d|\[|\{|\(|true\b|false\b|null\b)"
    r"|^\s*[\[{(]\s*$|^\s*[\]})]+\s*[,;)]*\s*$"
    r"|^\s*<?https?://\S+>?\s*$"
    r"|^\s*(?:[\w.-]+[/\\])*[\w.-]+\.(?:py|js|ts|tsx|jsx|json|md|txt|csv|ya?ml|toml|ini|cfg|html|css"
    r"|sh|ps1|bat|ipynb|db|sqlite|log|lock|xml|java|go|rs|rb|c|h|cpp)\s*$"
    r"|\bat [\w$./]+\([\w$.]+\.\w+:\d+(?::\d+)?\)"
    r"|^\s*(?:[a-z_]\w*\.)+[A-Z]\w*(?:Error|Exception)\b"
    r"|\b\d{1,2}:\d{2}:\d{2}(?:[.,]\d+)?\b.*\b(?:ERROR|WARN(?:ING)?|INFO|DEBUG|TRACE|CRITICAL|FATAL)\b"
    r"|\"(?:GET|POST|PUT|DELETE|PATCH|HEAD) /\S* HTTP/\d"
    r"|^\s*HTTP/\d(?:\.\d)? \d{3}\b"
    r"|^\s*\\[A-Za-z]+\{|(?:\\[A-Za-z]+\{.*){2}"
)
_SHELL_CMD_RE = re.compile(
    r"^\s*(?:\$\s+)?(?:sudo\s+)?(?:git|pip3?|npm|npx|yarn|pnpm|python3?|py|node|cd|ls|dir|curl"
    r"|wget|cat|grep|rg|export|echo|mkdir|rm|cp|mv|docker|kubectl|conda|source|chmod|ssh|scp"
    r"|brew|apt(?:-get)?|pytest|make|cargo|go|uv|poetry|gh|tar|unzip|setx|eval|sed|awk|find"
    r"|xargs|tee|head|tail|touch|kill|bash|sh|zsh|pwsh|powershell|winget|choco|ollama"
    r"|[A-Z][a-z]+-[A-Z]\w+)"
    r"\s+\S")
_SHELL_ARG_RE = re.compile(r"\s-{1,2}\w|[/\\]|\||>|\$\{?\w|=\S|\w\.[A-Za-z][A-Za-z0-9]{0,3}\b")
# Code shapes a sentence can also take, so a line full of plain words is exempt from them.
_CM_SOFT_RE = re.compile(
    r"[;{]\s*$|;\s*(?:then|do)\s*$"
    r"|^\s*(?:[,)\]}]|\.\w+\()"
    r"|^\s*[A-Za-z_$][\w.$]*(?:\[[^\]]*\])?(?:\s*,\s*[A-Za-z_$][\w.$]*)*\s*"
    r"(?:[-+*/%|&^]|//|\*\*|:)?=(?!=)\s*\S"
    r"|^\s*(?:for|while|if|elif|else if|let|var|const|set)\s+[\w$.\[\]]+\s*"
    r"(?:=|:=|\bin\b|<|>|!=|==)"
    r"|^\s*(?:if|elif|while|else if)\s+(?=.*(?:\w\.\w+\(|\w_\w|\b[a-z]+[A-Z]))"
    r"(?=.*(?:[<>]=?|==|!=|&&|\|\|))"
    r"|^\s*(?:else|try|finally)\s*[:{]\s*$"
    r"|^\s*\.[A-Za-z_]\w*\s*$|^\s*/?>\s*$"
    r"|^\s*return\b.*[;)\]]\s*$|^\s*return\s+[\w.$\[\]()]+\s*;?\s*$"
    r"|^\s*(?:await\s+)?[A-Za-z_$][\w.$]*\((?:.*\))?\s*[;,]?\s*$"
    r"|^\s*@\w+(?:\.\w+)*\(|^\s*@\w+\.\w+"
    r"|^\s*(?:function\s*\*?\s*\w*\s*\(|(?:export\s+)?(?:const|let|var)\s+\w+\s*="
    r"|(?:public|private|protected|static|internal)\s+\w"
    r"|(?:void|int|uint\d*|bool|string|float|double|char|long|auto)\s+[\w:]+\s*[(=;]"
    r"|fn\s+\w+\s*\(|func\s+\w+\s*\()"
    r"|^\s*[A-Z][A-Z0-9_]+=\S*\s*$"
    r"|^\s*-?\s*[A-Za-z_][\w.-]*[_.][\w.-]*\s*:\s+\S"
    r"|^\s*-?\s*[A-Za-z_][\w-]*\s*:\s+(?:true|false|null|~)\s*,?\s*$"
    r"|(?=.*\$\{?[A-Za-z_])(?=.*(?:\s\|\s|>\s*/|2>&1))"
)
# Recall pass. Shapes of machine output the rules above missed, each anchored on structure
# rather than on a word a person might type:
# - English-worded compiler and runtime messages: a line ending in a line:col position, or
#   opening with an error/warning prefix and a colon, that ALSO carries an identifier
#   (braces, an assignment, a dotted or camelCase name, a quoted token). "i got an error at
#   10:30" has the position and no identifier, so it stays prose.
# - TeX build-log residue: font specs (a backslash, T1, a slash), over/underfull box
#   notices, "(./file.tex" opens, LaTeX and package warnings.
# - Chat-client headers: nothing but a display name or handle, a dash or a wide gap, and a
#   clock time with AM/PM.
# - Coding-agent status lines: spinner glyph + verb + elapsed time, tool-call bullets,
#   "(ctrl+o to expand)", the result gutter glyph.
_CM_POS_RE = re.compile(r"\bat (?:line )?\d+:\d+\s*$")
_CM_ERR_PREFIX_RE = re.compile(
    r"^\s*(?:error|warning|Error|Warning|ERROR|Fatal error|No such [a-z]+(?: [a-z]+)?"
    r"|Undeclared (?:identifier|variable)|Undefined (?:variable|function|reference|symbol)"
    r"|Cannot (?:find|resolve|read|call|use)|Could not (?:find|resolve|load|open|import)"
    r"|Only [a-z]+ (?:expected|allowed)[a-z ]*|Syntax error|Mismatched input|Unexpected token)"
    r"\b[^:\n]{0,40}:\s+(\S.*)$")
_CM_IDENT_RE = re.compile(
    r"[{}=]|\w\.[A-Za-z]|\b[a-z]+[A-Z]\w*|\b[A-Z][a-z]+[A-Z]\w*|'[^'\s]+'|`[^`\s]+'|\w_\w")
_CM_MACHINE_EXTRA_RE = re.compile(
    r"^\s*fatal:\s"
    r"|\\T1/\w+/|^\s*(?:Overfull|Underfull) \\[hv]box\b|^\s*\(\./[\w./-]+"
    r"|^\s*(?:LaTeX|pdfTeX|Package [\w-]+|Class [\w-]+)(?: Font)? (?:Warning|Error|Info)\b"
    r"|^\s*\([\w-]+\.(?:def|sty|cls|cfg|tex)\)\s"
    r"|^(?=.*\w\().*\)\s*;\s*$"
    r"|^\s*-{1,2}[a-z][\w-]*(?:[ =](?:[A-Z][A-Z_]+|<\w+>))(?:,\s*-{1,2}[a-z][\w-]*)*\s*$"
    r"|^\s*\[\](?:\s|\[|\\|$)"
    r"|^\s*(?:[A-Z][\w.'-]*|[\w.'-]*_[\w.'-]*)(?: (?:[A-Z][\w.'-]*|[\w.'-]*_[\w.'-]*)){0,3}"
    "(?:\\s*[\u2014\u2013|-]\\s*|\\s{2,}|\\t)(?:Today at |Yesterday at )?\\d{1,2}:\\d{2}\\s?[AP]M\\s*$"
    "|^\\s*[\u273b\u2736\u2733\u2722\u273d]\\s+\\w+\\b[^\\n]*?"
    "(?:\\bfor \\d+(?:m \\d+)?s\\b|\\besc to\\b|\u2026)"
    r"|\((?:ctrl|shift|alt|esc)(?:\+\w+)? to \w+"
    "|^\\s*\u2026\\s*\\+\\d+ lines\\b|^\\s*\u23bf"
    "|^\\s*[\u23fa\u25cf]\\s+(?:Read|Wrote|Write|Update|Updated|Bash|Edit|Search(?:ed)?|Fetch"
    r"|Task|Agent|Web\w*|List|Grep|Glob|Explore|Skill|Ran)\b")
_CM_KWARG_RE = re.compile(r"\b[A-Za-z_]\w*\s*=(?!=)")
# A comment line. Neutral on its own; it becomes code when a line directly above or below
# it is code, so a markdown heading or a "// my note" typed between sentences stays the
# subject's. "--" is not a comment marker here: people type it as a bullet.
_CM_COMMENT_RE = re.compile(r"^\s*(?://|#(?![#!])\s?\S|/\*|\*/)")
# Menu chrome a web page prints under each post. A line holding only one of these words
# becomes code only when a directly adjacent line is chrome or code too.
_CM_MENU_WORDS = frozenset({
    "reply", "share", "award", "report", "upvote", "downvote", "save", "follow", "copy",
    "copy code", "edit", "like", "retweet", "repost", "quote", "hide", "permalink", "embed",
    "more replies", "view more replies"})


def _is_machine_message(t: str) -> bool:
    if _CM_MACHINE_EXTRA_RE.search(t):
        return True
    if _CM_POS_RE.search(t) and _CM_IDENT_RE.search(t):
        return True
    m = _CM_ERR_PREFIX_RE.match(t)
    if m and (_CM_IDENT_RE.search(m.group(1)) or re.search(r"\bline \d+", t[:m.start(1)])):
        return True
    # A conditional over two or more code identifiers (a call, snake_case, camelCase) and a
    # comparison, even when half its tokens are plain words ("and", "not").
    if re.match(r"^\s*(?:if|elif|while|else if)\s", t) and re.search(r"[<>]=?|==|!=|&&|\|\|", t):
        idents = re.findall(r"\w\(|\b\w+_\w+\b|\b[a-z]+[A-Z]\w*", t)
        return len(idents) >= 2
    return False


_COLON_STMT_RE = re.compile(r"^\s*(?:except|elif|while|if|for|with)\b(.*):\s*$")
_KV_PAIR_RE = re.compile(r"(?:^|\s)[A-Za-z_][\w.-]*=[^\s=]+")
_CODE_TOKEN_RE = re.compile(r"[\w$]+[._][\w$]+|\w\(|[{}\[\]();=<>]")
_TOKEN_PUNCT = "()[]{},.:;!?\"'`"


def _plain_words(line: str) -> tuple:
    """-> (plain, total): whitespace tokens that are plain words once punctuation around
    them is stripped, and all tokens."""
    toks = line.split()
    plain = sum(1 for t in toks if t.strip(_TOKEN_PUNCT).replace("'", "").isalpha())
    return plain, len(toks)


def is_code_or_machine_line(line: str) -> bool:
    """One line of code or machine output (see the section comment)."""
    t = line.rstrip("\r")
    if not t.strip():
        return False
    if t.strip().startswith("```"):
        return True
    if _CM_HARD_RE.search(t):
        return True
    if is_machine_line(t) and not _CM_TERMINAL_AMBIGUOUS_RE.match(t):
        return True
    if _is_machine_message(t):
        return True
    # A call with three or more keyword assignments, whatever words its quoted labels carry.
    if re.search(r"\w\(", t) and len(_CM_KWARG_RE.findall(t)) >= 3:
        return True
    plain, total = _plain_words(t)
    # A sentence: four or more plain words making up 70% of the tokens, or six or more
    # making up half (a sentence that quotes a record or a few identifiers).
    if (plain >= 4 and plain >= 0.7 * total) or (plain >= 6 and plain >= 0.5 * total):
        return False
    if _CM_SOFT_RE.search(t):
        return True
    m = _COLON_STMT_RE.match(t)
    if m and re.search(r"[()\[\]=<>!]|\w\.\w", m.group(1)):
        return True
    if _SHELL_CMD_RE.match(t) and _SHELL_ARG_RE.search(t):
        return True
    if len(_KV_PAIR_RE.findall(t)) >= 2:
        return True
    code_toks = sum(1 for tok in t.split() if _CODE_TOKEN_RE.search(tok))
    return total >= 3 and code_toks >= 3 and code_toks >= 0.5 * total


def _is_prose_for_code(line: str) -> bool:
    """A line of the subject's prose: three or more plain words making up 60% or more of
    its tokens. A '#' line is never prose here (a comment or a heading)."""
    t = line.strip()
    if not t or t.startswith("#"):
        return False
    plain, total = _plain_words(t)
    return plain >= 3 and plain >= 0.6 * total


_FENCE_OPEN_RE = re.compile(r"^\s*```")


def fence_spans(text: str) -> list:
    """Char spans of fenced ``` blocks, opening line to closing line. A line holding two
    or more fences is inline and opens nothing. An unclosed fence ends at the next blank
    line, never at the end of the text."""
    lines, offs, pos = text.split("\n"), [], 0
    for ln in lines:
        offs.append(pos)
        pos += len(ln) + 1
    out, i = [], 0
    while i < len(lines):
        if _FENCE_OPEN_RE.match(lines[i]) and lines[i].count("```") == 1:
            j = i + 1
            while j < len(lines) and not _FENCE_OPEN_RE.match(lines[j]):
                j += 1
            if j == len(lines):   # unclosed: stop at the paragraph's end
                j = i
                while j + 1 < len(lines) and lines[j + 1].strip():
                    j += 1
            out.append((offs[i], offs[j] + len(lines[j])))
            i = j + 1
        else:
            i += 1
    return out


def menu_chrome_spans(text: str) -> list:
    """Char spans of menu-chrome lines (a line holding only a word such as Reply, Share or
    Upvote) whose nearest non-blank neighbour above or below, skipping a bare count such as
    a vote tally, is another menu line. Read over the whole turn because blank lines split
    segments and a page's menu row is usually one word per paragraph. A single menu word
    between sentences stays own."""
    lines, offs, pos = text.split("\n"), [], 0
    for ln in lines:
        offs.append(pos)
        pos += len(ln) + 1
    menu =[ln.strip().lower() in _CM_MENU_WORDS for ln in lines]

    def near(i):
        for step in (-1, 1):
            j = i + step
            while 0 <= j < len(lines) and (not lines[j].strip() or lines[j].strip().isdigit()):
                j += step
            if 0 <= j < len(lines) and menu[j]:
                return True
        return False

    keep = [menu[i] and near(i) for i in range(len(lines))]
    # A bare count (a vote tally) whose nearest non-blank lines on both sides are kept menu
    # lines is part of the same chrome.
    for i, ln in enumerate(lines):
        if ln.strip().isdigit():
            sides = []
            for step in (-1, 1):
                j = i + step
                while 0 <= j < len(lines) and not lines[j].strip():
                    j += step
                sides.append(0 <= j < len(lines) and keep[j])
            keep[i] = all(sides)
    return [(offs[i], offs[i] + len(lines[i])) for i in range(len(lines)) if keep[i]]


def code_machine_spans(seg: str, fenced=()) -> list:
    """Code and machine-output spans inside one segment, as char offsets into it.

    A span is a run of lines with no prose line in it that contains at least one code or
    machine line; neutral lines at its edges are left out unless they are indented (a
    code block's body). Lines inside ``fenced`` (char spans relative to ``seg``) are code.
    Prose lines typed above, below or between stay the subject's."""
    lines, offs, pos = seg.split("\n"), [], 0
    for ln in lines:
        offs.append(pos)
        pos += len(ln) + 1

    def in_fence(i):
        a, b = offs[i], offs[i] + len(lines[i])
        return any(fa <= a and b <= fb for fa, fb in fenced)

    kinds = []
    for i, ln in enumerate(lines):
        if in_fence(i) and ln.strip():
            kinds.append("C")
        elif is_code_or_machine_line(ln):
            kinds.append("C")
        elif _CM_COMMENT_RE.match(ln):
            # An indented comment sits inside a block of code; a flush one is ambiguous
            # with a heading or a typed note and waits for a code neighbour.
            kinds.append("C" if ln[:1] in (" ", "\t") and ln.lstrip()[:2] in ("//", "/*")
                         else "K")
        elif _is_prose_for_code(ln):
            kinds.append("P")
        else:
            kinds.append("N")
    # A comment line (K) becomes code when the line directly above or below it is code;
    # chains of comment lines resolve by repeating until stable. What is left is read as
    # prose or neutral like any other line.
    changed = True
    while changed:
        changed = False
        for i, k in enumerate(kinds):
            if k == "K" and any(0 <= j < len(kinds) and kinds[j] == "C" for j in (i - 1, i + 1)):
                kinds[i] = "C"
                changed = True
    for i, k in enumerate(kinds):
        if k == "K":
            kinds[i] = "P" if _is_prose_for_code(lines[i]) else "N"
    out, i, n = [], 0, len(lines)
    while i < n:
        if kinds[i] == "P":
            i += 1
            continue
        j = i
        while j < n and kinds[j] != "P":
            j += 1
        run = [k for k in range(i, j) if kinds[k] == "C"]
        if run:
            lo, hi = run[0], run[-1]
            while lo > i and lines[lo - 1][:1] in (" ", "\t") and lines[lo - 1].strip():
                lo -= 1
            while hi < j - 1 and lines[hi + 1][:1] in (" ", "\t") and lines[hi + 1].strip():
                hi += 1
            out.append((offs[lo], offs[hi] + len(lines[hi])))
        i = j
    return out


# Claude Code's prompt-history placeholder for a paste, e.g. "[Pasted text #2 +40 lines]".
PASTE_TAG_RE = re.compile(r"\[Pasted text #\d+(?: \+\d+ lines)?\]", re.I)


@dataclass
class VoiceSettings:
    """Subject-specific settings, loaded from the local import config."""
    subject_names: tuple = ()           # a greeting addressed to one of these reads as pasted
    extra_typos: frozenset = frozenset()
    typography_is_paste: bool = False   # em-dash / curly quotes count as paste signals
    quote_back_threshold: float = 0.5
    quote_back_min_words: int = 10
    paste_score_threshold: int = 2
    dictation_score_threshold: int = 3
    # Within-turn document segmenter (document_spans): runs on subject turns at least this
    # long, and marks a block a document at this score (with at least one hard signal).
    document_split_min_chars: int = 1500
    document_score_threshold: int = 3
    # Code and machine-output lines inside an otherwise-own segment (code_machine_spans).
    detect_code_machine: bool = True

    def greeting_to_subject_re(self):
        if not self.subject_names:
            return None
        alt = "|".join(re.escape(n) for n in self.subject_names if n)
        return re.compile(rf"^\s*(Hi|Hello|Hey|Dear)\s+({alt})\b", re.M | re.I) if alt else None


def features(t: str, settings: VoiceSettings) -> dict:
    words = _WORD_RE.findall(t)
    nw = max(1, len(words))
    typo_words = _GENERIC_TYPOS | set(settings.extra_typos)
    typos = sum(1 for w in re.findall(r"[A-Za-z]+", t) if w.lower() in typo_words)
    sents = [s for s in re.split(r"[.!?]+\s+", t.strip()) if s]
    return {
        "words": len(words),
        "ppw": round(len(re.findall(r"[.,;:!?]", t)) * 100 / nw, 1),
        "newlines": t.count("\n"),
        "typos": typos + len(_APOS_LESS_RE.findall(t.lower())) + len(_LOWER_I_RE.findall(t)),
        "space_punct": len(_SPACE_PUNCT_RE.findall(t)),
        "censor": len(_CENSOR_RE.findall(t)),
        "midcap": len(_MIDCAP_RE.findall(t)),
        "emdash": len(_EMDASH_RE.findall(t)),
        "curly": len(_CURLY_RE.findall(t)),
        "lower_start": round(sum(1 for s in sents if s[0].islower()) / max(1, len(sents)), 2),
    }


def dictation_score(f: dict, settings: VoiceSettings) -> int:
    s = 0
    if f["space_punct"] >= 2:
        s += 2
    if f["censor"] >= 1:
        s += 2
    if f["words"] >= 25 and f["newlines"] == 0 and f["ppw"] <= 6:
        s += 2
    elif f["words"] >= 40 and f["newlines"] == 0 and f["ppw"] <= 9:
        s += 1
    if f["midcap"] >= 3:
        s += 2
    elif f["midcap"] >= 2:
        s += 1
    if f["words"] >= 25 and f["typos"] == 0:
        s += 1
    if f["typos"] >= 2:
        s -= 2
    if f["words"] < 20:
        s -= 2
    if settings.typography_is_paste and (f["emdash"] or f["curly"]):
        s -= 2
    return s


def paste_score(seg: str, f: dict, settings: VoiceSettings) -> int:
    s = 0
    if len(_EMAIL_HDR_RE.findall(seg)) >= 2:
        s += 3
    gs = settings.greeting_to_subject_re()
    if gs is not None and gs.search(seg):
        s += 3
    elif _GREETING_RE.search(seg):
        s += 1
    if _CHAT_TS_RE.search(seg):
        s += 2
    if len(_MD_STRUCT_RE.findall(seg)) >= 3:
        s += 2
    if _FENCE_RE.search(seg):
        s += 2
    if len(_LOG_RE.findall(seg)) >= 2:
        s += 3
    if len(_CODE_RE.findall(seg)) >= 2:
        s += 3
    if _SIGNOFF_RE.search(seg):
        s += 1
    if settings.typography_is_paste:
        if f["emdash"] >= 2 or (f["emdash"] >= 1 and f["words"] < 120):
            s += 3
        if f["curly"] >= 2:
            s += 2
    if _TYPOGRAPHIC_RE.search(seg):
        s += 2
    if _TERMINAL_RE.search(seg):
        s += 3
    if _CHATUI_RE.search(seg):
        s += 3
    # Long, formal, cleanly punctuated prose with no typing or dictation artifacts reads
    # as a document or an assistant, not as a person typing into a chat box.
    if (f["words"] >= 120 and f["ppw"] >= 12 and f["lower_start"] < 0.1 and f["typos"] == 0
            and f["space_punct"] == 0 and f["censor"] == 0):
        s += 2
    if f["typos"] >= 2:
        s -= 3
    if f["space_punct"] >= 2 or f["censor"] >= 1:
        s -= 3
    if f["words"] < 25 and s < 3:
        s -= 2
    return s


def segment_spans(text: str, forced=()) -> list:
    """Split on `---` separators, blank lines, long quoted blocks, paste tags and any
    forced spans. Char spans."""
    cuts = {0, len(text)}
    for a, b in forced:
        cuts.add(a)
        cuts.add(b)
    for m in _SEP_RE.finditer(text):
        cuts.add(m.start())
        cuts.add(m.end())
    for m in _QUOTED_BLOCK_RE.finditer(text):
        cuts.add(m.start(1))
        cuts.add(m.end(1))
    for m in PASTE_TAG_RE.finditer(text):
        cuts.add(m.start())
        cuts.add(m.end())
    pts = sorted(cuts)
    return [(a, b) for a, b in zip(pts, pts[1:]) if text[a:b].strip()]


def quote_back_fraction(seg: str, prior_assistant_text: str, k: int = 6) -> float:
    sh = shingles(seg, k)
    if not sh or not prior_assistant_text:
        return 0.0
    return len(sh & shingles(prior_assistant_text, k)) / len(sh)


# --------------------------------------------------------------------------- documents

class AssistantShingles:
    """6-shingles of every assistant turn so far in a conversation, built incrementally.

    ``add`` only queues the text; shingling happens on the first query after it, so a
    conversation with no long subject turn never pays for it, and one that has several
    shingles each assistant turn once rather than once per subject turn."""

    def __init__(self, texts=(), k: int = 6):
        self.k = k
        self._set: set = set()
        self._pending: list = list(texts)

    def add(self, text: str) -> None:
        if text:
            self._pending.append(text)

    def _flush(self) -> set:
        for t in self._pending:
            self._set |= shingles(t, self.k)
        self._pending = []
        return self._set

    def fraction(self, seg: str) -> float:
        sh = shingles(seg, self.k)
        if not sh:
            return 0.0
        pool = self._flush()
        return len(sh & pool) / len(sh) if pool else 0.0


# Legal and formal-boilerplate register: words people rarely type into a chat box but that
# fill contracts, bylaws, policies and the fixed sections of postings. Counted as DISTINCT
# terms per block so one repeated word cannot carry the signal.
_LEGAL_TERMS_RE = re.compile(
    r"\b(shall|hereby|herein|hereof|hereto|hereunder|thereof|therein|thereto|whereas|"
    r"pursuant to|notwithstanding|in accordance with|indemnif\w*|provided that|"
    r"article [ivxlc\d]+|section \d+(?:\.\d+)*|the corporation|the company|"
    r"board of directors|bylaws|stockholders?|shareholders?|equal opportunity employer|"
    r"reasonable accommodations?|without regard to|applicants?|preferred qualifications|"
    r"minimum qualifications|salary range|compensation and benefits|we are looking for|"
    r"you will|the ideal candidate|about the (?:role|team|company))\b", re.I)
_DATED_LINE_RE = re.compile(
    r"^\s*\[?(?:\d{1,4}[/-]\d{1,2}(?:[/-]\d{2,4})?|\d{1,2}:\d{2}(?::\d{2})?\s?(?:[AP]M)?)\b",
    re.I)
_CODE_LINE_RE = re.compile(r"[;{}]\s*$|^\s*(?:return |if .*:\s*$|for .* in .*:\s*$|@\w+)")
_MOJIBAKE_RE = re.compile("\ufffd|\u00e2\u20ac")
_LIST_LINE_RE = re.compile("^\\s*(?:[-*\u2022]\\s|\\d+[.)]\\s|[a-z][.)]\\s)")
_FIRST_PERSON_RE = re.compile(r"\b(?:I|I'm|I've|I'd|Im|Ive|me|my)\b")
_DOC_VOICE_RE = re.compile(r"\b(?:we|our|us|they|their|the company|the team)\b", re.I)
# A short typed lead-in, then the pasted material on the same line: one ending in a colon
# ('summarise this: <document...'), or one followed directly by an opening quote
# ('here is the context "<document...').
QUOTES = ('"', "\u201c")
_LEAD_IN_RE = re.compile(r'^(\s*[^\n:"\u201c]{3,150}?:)[ \t]*(?=["\u201c]|\S)')
_HYPHEN_RUN_RE = re.compile(r"-{3,}")
_SEPARATOR_CHARS = frozenset(" \t\r\n-")
_QUOTE_LEAD_IN_RE = re.compile(r'^(\s*[^\n:"\u201c]{3,100}?)[ \t]*(?=["\u201c][ \t]*\S)')


def _typing_traits(line: str, settings: VoiceSettings) -> int:
    """Marks of hurried typing on one line: typos (generic and configured), contractions
    typed without the apostrophe, a lowercase 'i', a space before punctuation."""
    low = line.lower()
    typo_words = _GENERIC_TYPOS | set(settings.extra_typos)
    n = sum(1 for w in re.findall(r"[A-Za-z]+", line) if w.lower() in typo_words)
    n += len(_APOS_LESS_RE.findall(low)) + len(_LOWER_I_RE.findall(line))
    n += len(_SPACE_PUNCT_RE.findall(line))
    return n


def _typed_looking(line: str, settings: VoiceSettings) -> bool:
    """A line that reads as the subject typing to the assistant rather than a line of a
    document: prose with typing traits, a lowercase start or a closing question mark."""
    t = line.strip()
    words = _PROSE_LINE_RE.findall(t)
    if len(words) < 2 or is_machine_line(line) or _DATED_LINE_RE.match(t) or "\t" in t:
        return False
    if _typing_traits(t, settings) > 0:
        return True
    # A CRLF line came from another application: only a typing trait marks it as typed
    # (a paste can end mid-line, leaving the subject's words on a CRLF line).
    if line.endswith("\r"):
        return False
    if t.endswith("?"):
        return True
    # A lowercase first character marks typing only on a prose line: code starts lowercase
    # too, and a line opening with a number ("5+ years of ...") is not a lowercase start.
    # A closing quote typed right after a paste ('" what would you change') is skipped.
    head = t.lstrip("\"'”’) ")
    return (head[:1].islower() and not _CODEISH_RE.search(t)
            and not _CODE_LINE_RE.search(t))


def _heading_line(line: str) -> bool:
    t = line.strip()
    words = t.split()
    return (0 < len(words) <= 6 and len(t) <= 60 and t[0].isupper()
            and not t.endswith((".", "?", "!", ",")) and "\t" not in t)


def _block_doc_score(lines: list, settings: VoiceSettings) -> tuple:
    """-> (hard, score). ``hard`` counts only signals a person typing into a chat box does
    not produce (carriage returns, tab tables, dated lines, code, legal register, headings
    over a list, mangled encoding). Soft signals (long clean lines, document voice) add to
    the score but cannot move a block on their own."""
    body = [ln for ln in lines if ln.strip()]
    if not body:
        return 0, 0
    text = "\n".join(body)
    n = len(body)
    hard = 0
    cr = sum(1 for ln in body if ln.endswith("\r"))
    if cr and cr >= 0.5 * n:
        hard += 3
    if sum(1 for ln in body if ln.count("\t") >= 1 and len(ln.split("\t")) >= 2) >= 2:
        hard += 3
    if sum(1 for ln in body if _DATED_LINE_RE.match(ln)) >= 2:
        hard += 3
    if len(_CODE_RE.findall(text)) + sum(1 for ln in body if _CODE_LINE_RE.search(ln)) >= 3:
        hard += 3
    legal = {m.group(0).lower() for m in _LEGAL_TERMS_RE.finditer(text)}
    if len(legal) >= 3:
        hard += 3
    elif len(legal) == 2:
        hard += 2
    if _MOJIBAKE_RE.search(text):
        hard += 2
    if sum(1 for ln in body if _heading_line(ln)) >= 2 and \
            sum(1 for ln in body if _LIST_LINE_RE.match(ln)) >= 3:
        hard += 2
    score = hard
    long_clean = sum(1 for ln in body if len(ln) >= 200 and _typing_traits(ln, settings) == 0
                     and ln.strip()[:1].isupper())
    score += min(2, long_clean)
    words = len(_WORD_RE.findall(text))
    if words >= 60 and not _FIRST_PERSON_RE.search(text) and len(_DOC_VOICE_RE.findall(text)) >= 3:
        score += 1
    traits = sum(_typing_traits(ln, settings) for ln in body)
    if traits >= 2 and traits * 40 >= words:
        score -= 3
    elif traits:
        score -= 1
    return hard, score


def document_spans(text: str, settings: VoiceSettings | None = None,
                   earlier_assistant: "AssistantShingles | None" = None) -> list:
    """Pasted-document regions inside one long subject turn. -> [(start, end, detector)].

    The per-segment rules score each blank-line paragraph alone, so a pasted document cut
    into short paragraphs, or glued to the typed instruction with no blank line between,
    reads as the subject's own text. This pass sees the whole turn:

    1. Lines are grouped into blocks at blank lines, at runs of three or more hyphens
       (the same separators the per-segment rules cut at, including one typed against a
       word), and wherever the line ending changes between CRLF and LF (text pasted from
       another application often keeps CRLF; text typed into the box does not). A single
       LF line directly after a CRLF run, with no blank line between, is the paste's last
       line and joins it unless it reads as typed.
    2. A block is a document when it carries a hard signal and scores at least
       ``document_score_threshold``, or when 50% or more of its 6-shingles appear in ANY
       earlier assistant turn of the conversation (``paste:quote_back_earlier``).
    3. Typed lines at the edges of a document block (typing traits, a lowercase start, a
       question) are peeled off and stay the subject's; a typed lead-in ending in a colon
       on the document's first line is cut at the colon.
    4. A block with no typing traits that sits between two document blocks found by this
       pass is part of the document. A segment the per-segment rules marked pasted is not
       such a neighbour: a sentence typed between two pastes has nothing else to protect
       it. A trailing block is never absorbed this way.
    5. Separator characters (whitespace and hyphen runs) touching a document span join it,
       so no separator is left behind as a fragment of the subject's own text.
    """
    settings = settings or VoiceSettings()
    lines, pos, brk = [], 0, set()   # units: lines, cut again at hyphen runs
    for ln in text.split("\n"):
        cut = pos
        for m in _HYPHEN_RUN_RE.finditer(ln):
            a = pos + m.start()
            if text[cut:a].strip():
                lines.append((cut, a, text[cut:a]))
            brk.add(len(lines))
            cut = pos + m.end()
        lines.append((cut, pos + len(ln), text[cut:pos + len(ln)]))
        pos += len(ln) + 1

    # 1. blocks of unit indexes
    blocks, cur = [], []
    for i, (_, _, ln) in enumerate(lines):
        if i in brk and cur:
            blocks.append(cur)
            cur = []
        if not ln.strip():
            if cur:
                blocks.append(cur)
                cur = []
            continue
        if cur:
            prev = lines[cur[-1]][2]
            if prev.endswith("\r") != ln.endswith("\r"):
                tail_of_paste = (prev.endswith("\r") and not ln.endswith("\r")
                                 and not _typed_looking(ln, settings))
                if not tail_of_paste:
                    blocks.append(cur)
                    cur = []
        cur.append(i)
    if cur:
        blocks.append(cur)

    def span(idxs):
        return lines[idxs[0]][0], lines[idxs[-1]][1]

    # 2-3. peel typed edges, then classify what is left
    marked = []   # (start, end, detector or None, has_traits)
    for b in blocks:
        blines = [lines[i][2] for i in b]
        s, e = span(b)
        traits = sum(_typing_traits(ln, settings) for ln in blines)
        lo, hi = 0, len(b)
        lead_cut = None
        m = _LEAD_IN_RE.match(blines[0])
        if m and blines[0][m.end():].strip() and (
                _typed_looking(m.group(1), settings) or blines[0][m.end():m.end() + 1] in QUOTES):
            lead_cut = m.end()
        elif (q := _QUOTE_LEAD_IN_RE.match(blines[0])) and len(q.group(1).split()) <= 15:
            lead_cut = q.end()
        else:
            while lo < hi - 1 and _typed_looking(blines[lo], settings):
                lo += 1
        while hi - 1 > lo and _typed_looking(blines[hi - 1], settings):
            hi -= 1
        cs = lines[b[lo]][0] + (lead_cut or 0)
        ce = lines[b[hi - 1]][1]
        core_text = text[cs:ce]
        det = None
        if (earlier_assistant is not None
                and len(_WORD_RE.findall(core_text)) >= settings.quote_back_min_words
                and earlier_assistant.fraction(core_text) >= settings.quote_back_threshold):
            det = D_PASTE_QUOTE_BACK_EARLIER
        else:
            hard, score = _block_doc_score(core_text.split("\n"), settings)
            if hard and score >= settings.document_score_threshold:
                det = D_PASTE_DOCUMENT
        if det is None:
            marked.append((s, e, None, traits > 0))
            continue
        if cs > s:
            marked.append((s, cs, None, True))
        marked.append((cs, ce, det, False))
        if ce < e:
            marked.append((ce, e, None, True))

    # 4. sandwiched untyped blocks join the document around them
    out = list(marked)
    for k in range(1, len(marked) - 1):
        s, e, det, traits = marked[k]
        if det is None and not traits and marked[k - 1][2] and marked[k + 1][2] \
                and not _typed_looking(text[s:e].strip().split("\n")[0], settings):
            out[k] = (s, e, D_PASTE_DOCUMENT, False)

    # 5. separators touching a document span join it
    spans = []
    for s, e, d, _ in out:
        if d is None:
            continue
        while s > 0 and text[s - 1] in _SEPARATOR_CHARS:
            s -= 1
        while e < len(text) and text[e] in _SEPARATOR_CHARS:
            e += 1
        if spans and s <= spans[-1][1] and spans[-1][2] == d:
            spans[-1] = (spans[-1][0], max(e, spans[-1][1]), d)
        elif spans and s < spans[-1][1]:
            spans.append((spans[-1][1], e, d))
        else:
            spans.append((s, e, d))
    return spans


# --------------------------------------------------------------------------- segment

@dataclass
class Segment:
    start: int
    end: int
    voice_class: str
    detector: str | None = None
    basis: str | None = None
    score: float = 0.0


@dataclass
class SubjectTurnClassification:
    segments: list = field(default_factory=list)   # [Segment], contiguous same-class merged

    @property
    def has_paste(self) -> bool:
        return any(s.voice_class == "pasted" for s in self.segments)


def classify_subject_text(text: str, prior_assistant_text: str = "",
                          settings: VoiceSettings | None = None,
                          own_class: str = "own_typed", own_basis: str = B_ROLE,
                          template_scorer=None, detect_dictation: bool = True,
                          forced_paste_spans=(), earlier_assistant=None,
                          ) -> SubjectTurnClassification:
    """Segment a subject turn and mark pasted segments.

    ``own_class`` is the class for non-pasted segments (``own_dictated`` for sources
    that are speech by construction). When ``detect_dictation`` is set, a typed-source
    turn whose own text carries dictation artifacts is re-classed ``own_dictated``.
    ``template_scorer(text) -> int`` returns harness-template shingle hits (config).
    ``earlier_assistant`` (an ``AssistantShingles``, or a callable returning one, called
    only when needed) holds every earlier assistant turn of the conversation; on a turn of
    ``document_split_min_chars`` or more, ``document_spans`` then re-splits the segments
    the per-segment rules left as the subject's own.
    """
    settings = settings or VoiceSettings()
    raw_segments = []
    forced = list(forced_paste_spans)
    scan_code = settings.detect_code_machine and own_class == "own_typed"
    fences = fence_spans(text) + menu_chrome_spans(text) if scan_code else []
    # Fences are read only inside segments the other rules leave own (code_machine_spans);
    # they are not cuts, so no other rule sees a segment split differently.
    for a, b in segment_spans(text, forced):
        seg = text[a:b]
        if any(fa <= a and b <= fb for fa, fb in forced) or PASTE_TAG_RE.fullmatch(seg.strip()):
            raw_segments.append(Segment(a, b, "pasted", D_PASTE_TAG))
            continue
        f = features(seg, settings)
        if f["words"] >= settings.quote_back_min_words:
            qb = quote_back_fraction(seg, prior_assistant_text)
            if qb >= settings.quote_back_threshold:
                raw_segments.append(Segment(a, b, "pasted", D_PASTE_QUOTE_BACK, score=round(qb, 3)))
                continue
        if template_scorer is not None and template_scorer(seg) >= 3:
            raw_segments.append(Segment(a, b, "pasted", D_PASTE_TEMPLATE))
            continue
        if is_terminal_segment(seg):
            lead, tail = terminal_prose_margins(seg)
            if lead:
                raw_segments.append(Segment(a, a + lead, own_class, None, own_basis))
            if tail > lead:
                raw_segments.append(Segment(a + lead, a + tail, "pasted", D_PASTE_TERMINAL))
            if tail < len(seg):
                raw_segments.append(Segment(a + tail, b, own_class, None, own_basis))
            continue
        ps = paste_score(seg, f, settings)
        if ps >= settings.paste_score_threshold:
            raw_segments.append(Segment(a, b, "pasted", D_PASTE_STRUCTURAL, score=ps))
            continue
        raw_segments.append(Segment(a, b, own_class, None, own_basis, score=ps))

    # Pasted documents the per-segment rules could not see. Runs on typed-source turns
    # only (speech sources carry no pastes), and before the dictation score, so a
    # document cannot pull the subject's own text into or out of the dictated class.
    if own_class == "own_typed" and len(text) >= settings.document_split_min_chars:
        earlier = earlier_assistant() if callable(earlier_assistant) else earlier_assistant
        docs = document_spans(text, settings, earlier)
        if docs:
            raw_segments = _cut_own_segments(raw_segments, docs, text, own_class)

    # Code and machine output left inside the subject's own segments. Runs after every
    # other rule, so it only ever reads text they left own.
    if scan_code:
        raw_segments = _cut_code_machine(raw_segments, text, own_class, fences)

    # Dictation is a property of the subject's own text as a whole, not of a fragment.
    if detect_dictation and own_class == "own_typed":
        own_text = "\n".join(text[s.start:s.end] for s in raw_segments if s.voice_class == own_class)
        if own_text and dictation_score(features(own_text, settings), settings) >= settings.dictation_score_threshold:
            for s in raw_segments:
                if s.voice_class == own_class:
                    s.voice_class, s.basis = "own_dictated", B_DICTATION

    # Merge contiguous segments of the same class and detector; spans stay exact slices.
    merged = []
    for s in raw_segments:
        if merged and merged[-1].voice_class == s.voice_class and merged[-1].detector == s.detector:
            merged[-1].end = s.end
        else:
            merged.append(s)
    if not merged and text.strip():
        merged = [Segment(0, len(text), own_class, None, own_basis)]
    return SubjectTurnClassification(merged)


def _cut_code_machine(raw_segments, text, own_class, fences):
    """Re-split own segments at code/machine spans; other segments are left as they are."""
    out = []
    for seg in raw_segments:
        if seg.voice_class != own_class:
            out.append(seg)
            continue
        a, b = seg.start, seg.end
        rel = [(fa - a, fb - a) for fa, fb in fences if fa < b and a < fb]
        cursor = a
        for ca, cb in code_machine_spans(text[a:b], rel):
            if text[cursor:a + ca].strip():
                out.append(Segment(cursor, a + ca, own_class, None, seg.basis, score=seg.score))
            out.append(Segment(a + ca, a + cb, "pasted", D_PASTE_CODE_MACHINE))
            cursor = a + cb
        if text[cursor:b].strip():
            out.append(Segment(cursor, b, own_class, None, seg.basis, score=seg.score))
    return out


def _cut_own_segments(raw_segments, docs, text, own_class):
    """Re-split own segments at document spans; pasted segments are left as they are."""
    out = []
    for seg in raw_segments:
        if seg.voice_class != own_class:
            out.append(seg)
            continue
        cursor = seg.start
        for a, b, det in docs:
            if b <= seg.start or a >= seg.end:
                continue
            a, b = max(a, seg.start), min(b, seg.end)
            if text[cursor:a].strip():
                out.append(Segment(cursor, a, own_class, None, seg.basis))
            if text[a:b].strip():
                out.append(Segment(a, b, "pasted", det))
            cursor = b
        if text[cursor:seg.end].strip():
            out.append(Segment(cursor, seg.end, own_class, None, seg.basis, score=seg.score))
    return out


# --------------------------------------------------------------------------- own writing

# A pasted document can be the subject's own writing: a journal or log kept in another
# application and pasted into the chat. The document segmenter marks it pasted from its
# layout, but its lines carry the subject's typing traits. With the local config switch
# `allowlist_own_writing_pasted` on, such a segment is re-classed own_typed with this basis
# and a practice tag (see OwnWritingRule). Off by default.
B_OWN_WRITING = "allowlist:own_writing_pasted"
OWN_WRITING_MIN_TRAITS = 3
# Only segments the document segmenter moved are eligible. Quote-back detectors match
# assistant text by construction, and the other paste detectors also catch third-party
# material (articles, forum posts, other people's chat lines) that carries typing traits.
OWN_WRITING_DETECTORS = (D_PASTE_DOCUMENT,)

PRACTICE_TRADING_JOURNAL = "trading_journal"
PRACTICE_OWN_DOCUMENT = "own_document"

# Generic trade-record vocabulary (no subject-specific terms).
_TRADE_TERM_RE = re.compile(
    r"\b(?:calls?|puts?|strikes?|shares|contracts?|entry|entries|exit|stop[- ]?loss|sl|"
    r"p/l|pnl|profit|loss(?:es)?|long|short|bought|sold|buy|sell|position|premium|expiry|"
    r"options?|trades?|traded|trading|bull(?:ish)?|bear(?:ish)?|candle|breakout|"
    r"vwap|ema|sma|rsi|macd|scalp(?:ed|ing)?|overtrad(?:ed|ing)|capital)\b", re.I)
_MONEY_RE = re.compile(r"-?\$\s?\d[\d,]*(?:\.\d+)?")
_OPTION_CONTRACT_RE = re.compile(r"\b\d{2,5}(?:\.\d+)?[CP]\b")
_TIMEFRAME_RE = re.compile(r"\b\d{1,2}m\b")


def typing_trait_score(text: str, settings: VoiceSettings | None = None) -> int:
    """The typing-trait count of a segment: the sum of per-line typing traits (typos,
    configured misspellings, apostrophe-less contractions, a lowercase 'i', a space before
    punctuation) over its non-blank lines. The same count the segmenter uses per block."""
    settings = settings or VoiceSettings()
    return sum(_typing_traits(ln, settings) for ln in (text or "").split("\n") if ln.strip())


def practice_of_pasted(text: str) -> str:
    """Practice tag for a re-classed own-writing segment. `trading_journal` when the
    segment is a trade record: trade vocabulary (terms, money amounts, option contracts,
    chart timeframes) at least 5 times, and either laid out as a record (two or more tab
    rows or dated/timed lines) or dense in that vocabulary (one hit per 40 words or more).
    Anything else is `own_document`: still bounded to the document it came from."""
    t = text or ""
    body = [ln for ln in t.split("\n") if ln.strip()]
    hits = (len(_TRADE_TERM_RE.findall(t)) + len(_MONEY_RE.findall(t))
            + len(_OPTION_CONTRACT_RE.findall(t)) + len(_TIMEFRAME_RE.findall(t)))
    words = len(_WORD_RE.findall(t))
    record = (sum(1 for ln in body if "\t" in ln.strip("\r")) >= 2
              or sum(1 for ln in body if _DATED_LINE_RE.match(ln)) >= 2)
    if hits >= 5 and (record or hits * 40 >= words):
        return PRACTICE_TRADING_JOURNAL
    return PRACTICE_OWN_DOCUMENT


@dataclass
class OwnWritingRule:
    """Re-class eligible pasted segments whose typing-trait score reaches `min_traits`."""
    settings: VoiceSettings = field(default_factory=VoiceSettings)
    min_traits: int = OWN_WRITING_MIN_TRAITS
    detectors: tuple = OWN_WRITING_DETECTORS

    def decide(self, text: str, detector: str | None) -> str | None:
        """-> the practice tag when the segment is re-classed, else None."""
        if detector not in self.detectors:
            return None
        if typing_trait_score(text, self.settings) < self.min_traits:
            return None
        return practice_of_pasted(text)


# --------------------------------------------------------------------------- templates

class TemplateIndex:
    """Harness template fingerprints: 7-word shingles of long string literals in the
    scripts that build prompts for programmatic children. Roots come from config."""

    def __init__(self, roots=(), min_len: int = 60, exclude_dirs=()):
        import ast
        from pathlib import Path
        self.shingle_set: set = set()
        self.heads: set = set()
        self.files = 0
        for root in roots:
            root = Path(root)
            if not root.exists():
                continue
            for p in root.rglob("*.py"):
                if "__pycache__" in p.parts or set(exclude_dirs) & set(p.parts):
                    continue
                try:
                    tree = ast.parse(p.read_text(encoding="utf-8"))
                except Exception:
                    continue
                self.files += 1
                for node in ast.walk(tree):
                    vals = []
                    if isinstance(node, ast.Constant) and isinstance(node.value, str):
                        vals = [node.value]
                    elif isinstance(node, ast.JoinedStr):
                        vals = [v.value for v in node.values
                                if isinstance(v, ast.Constant) and isinstance(v.value, str)]
                    for lit in vals:
                        if len(lit) < min_len:
                            continue
                        for piece in re.split(r"\{[^{}]*\}", lit):
                            self.shingle_set |= shingles(piece, 7)
                            w = _WORDS_RE.findall(piece.lower())
                            if len(w) >= 5:
                                self.heads.add(" ".join(w[:5]))

    def __bool__(self):
        return bool(self.shingle_set)

    def hits(self, text: str) -> int:
        return len(shingles(text, 7) & self.shingle_set)

    def head_match(self, text: str) -> bool:
        w = _WORDS_RE.findall((text or "").lower())
        return len(w) >= 5 and " ".join(w[:5]) in self.heads

    def is_template(self, text: str) -> bool:
        if not self.shingle_set:
            return False
        sh = shingles(text, 7)
        h = len(sh & self.shingle_set)
        return self.head_match(text) or h >= 3 or (bool(sh) and h / len(sh) >= 0.2)
