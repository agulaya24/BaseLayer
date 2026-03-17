"""
Tests for agent_pipeline.py — composition prompt, store format, artifact I/O,
and prompt construction.

All tests run without API keys or external services.
"""

import pytest
import sys
import json
from pathlib import Path
from unittest.mock import patch, MagicMock


