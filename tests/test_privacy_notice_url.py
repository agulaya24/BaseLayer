"""The privacy notice `init` prints links Anthropic's privacy policy at its live URL. The old
/policies/privacy address returns 404. No network: the source is read, not fetched.
"""
import inspect

from baselayer import cli


def test_init_privacy_notice_links_the_live_page():
    src = inspect.getsource(cli)
    assert "anthropic.com/policies/privacy" not in src
    assert "https://www.anthropic.com/legal/privacy" in src
