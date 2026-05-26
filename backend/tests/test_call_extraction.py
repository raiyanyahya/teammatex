"""Regression guard for CALLS extraction.

Two bugs made the graph have zero CALLS edges: Python calls were never detected
(the walker only looked for `call_expression`, but Python uses `call`), and the
caller was recorded as the file path instead of the enclosing function (so the
graph builder couldn't match it to a Function node).
"""

import pytest

from app.services.onboarding.code_parser import CodeParser

PY = """
def helper(x):
    return x + 1

def main():
    y = helper(5)
    print(y)
"""

JS = """
function helper(x){ return x + 1; }
function main(){ var y = helper(5); console.log(y); }
"""


def _calls(parser, path, code):
    a = parser.parse_file(path, code)
    if a is None:
        pytest.skip("language parser not available")
    return [d for d in a.dependencies if d.kind == "calls"]


def test_python_calls_are_detected():
    calls = _calls(CodeParser(), "s.py", PY)
    assert any(c.target == "helper" for c in calls)


def test_caller_is_the_enclosing_function_not_the_file():
    calls = _calls(CodeParser(), "s.py", PY)
    helper_call = next(c for c in calls if c.target == "helper")
    assert helper_call.source == "main"  # not "s.py"


def test_javascript_calls_attributed_to_caller():
    calls = _calls(CodeParser(), "s.js", JS)
    helper_call = next(c for c in calls if c.target == "helper")
    assert helper_call.source == "main"
