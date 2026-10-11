"""With the CNS extra missing, the connector must refuse loudly.

This file runs only when ``cns`` is NOT installed (see ``conftest.py``). The
real connector tests run when it is installed, so neither set skips.
"""

import pytest

from herald.cns_connector import (
    CnsNotInstalled,
    cns_available,
    cns_chain,
    run_governed,
    source_to_cns_result,
    submit_to_cns,
)
from herald.gate import ConfidenceGate
from herald.source import SourceDocument


def test_cns_is_reported_absent():
    assert cns_available() is False


def test_connector_functions_refuse_without_cns():
    doc = SourceDocument(source_id="s", text="Total is 1250 dollars.", standing="record")
    with pytest.raises(CnsNotInstalled, match="herald\\[cns\\]"):
        cns_chain()
    with pytest.raises(CnsNotInstalled):
        source_to_cns_result(doc)
    with pytest.raises(CnsNotInstalled):
        run_governed(doc)
    with pytest.raises(CnsNotInstalled):
        submit_to_cns(ConfidenceGate(), object())
