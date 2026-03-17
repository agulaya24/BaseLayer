"""
Temporary utility for blind regeneration with Opus (Claude Code) feedback.
Used when the developer is working in Claude Code and Opus review is done live.
"""
import sys, os, contextlib
sys.path.insert(0, os.path.dirname(__file__))
from author_layers import (
    generate_layer, _predictions_base_prompt,
    _anchors_base_prompt, _core_base_prompt,
    store_layer, ANCHORS_LAYER_FILE, CORE_LAYER_FILE, PREDICTIONS_LAYER_FILE,
)
from config import get_db


def blind_regenerate(layer_name, base_prompt, feedback):
    """Generate layer BLIND -- facts + feedback only, no prior output. D-053."""
    regen_prompt = f"""{base_prompt}

IMPORTANT -- REVIEW FEEDBACK TO ADDRESS:
{feedback}

Generate the layer from the input facts, addressing ALL feedback items above. Generate fresh."""
    return generate_layer(f"{layer_name} (blind regen)", regen_prompt)


if __name__ == "__main__":
    print("Use this module's blind_regenerate() from Claude Code scripts.")
    print("Not intended for standalone CLI use.")
