"""Version 3 exports: an Ed25519 signature a consumer in ANOTHER process can verify with a pinned public key.

Shown: a genuine export verifies in a separate process that holds only the public PEM; an alteration, a signature by
another key, a swapped key label, a missing trust set, and a non-Ed25519 key are each refused. The version 2 (HMAC)
export is shown still NOT verifiable in another process, which is its documented limit. The canonical signing bytes
are pinned by a fixed vector that TIE's independent verifier also checks."""

import json
import subprocess
import sys

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from herald import handoff
from herald.errors import SealIntegrityError
from herald.source import STANDING_RECORD, SourceDocument

TEXT = ("The borrower paid $1,250.00 on 2026-03-14. "
        "A reasonable fee of $500 may be assessed unless the waiver applies.")


def doc(text=TEXT):
    return SourceDocument(source_id="loan-8891", text=text, medium="document", standing=STANDING_RECORD)


def signed_export(key=None):
    key = key or Ed25519PrivateKey.generate()
    return handoff.read(doc(), export_signing_key=key), key


def pinned(key):
    return {handoff.export_key_id(key.public_key()): key.public_key()}


def test_a_genuine_v3_export_verifies_with_the_pinned_key():
    package, key = signed_export()
    assert package.export_mac_version == "3" and package.key_id.startswith("ed25519-")
    handoff.verify_export(package.to_dict(), trusted_keys=pinned(key))


def test_a_separate_process_holding_only_the_public_pem_verifies_it(tmp_path):
    package, key = signed_export()
    (tmp_path / "export.json").write_text(json.dumps(package.to_dict()))
    (tmp_path / "public.pem").write_bytes(handoff.export_public_pem(key))
    script = (
        "import json,sys\n"
        "from herald import handoff\n"
        "pem = open(sys.argv[2], 'rb').read()\n"
        "key = handoff.load_export_public_key(pem)\n"
        "handoff.verify_export(json.load(open(sys.argv[1])), trusted_keys={handoff.export_key_id(key): key})\n"
        "print('verified')\n"
    )
    done = subprocess.run([sys.executable, "-c", script, str(tmp_path / "export.json"), str(tmp_path / "public.pem")],
                          capture_output=True, text=True, timeout=60)
    assert done.returncode == 0 and done.stdout.strip() == "verified", done.stderr


def test_an_altered_admitted_value_is_refused_even_with_the_right_key():
    package, key = signed_export()
    exported = package.to_dict()
    exported["admitted"][0]["raw"] = "$9,999.00"
    with pytest.raises(SealIntegrityError, match="altered after it was signed"):
        handoff.verify_export(exported, trusted_keys=pinned(key))


def test_a_signature_by_another_key_is_refused_even_under_the_pinned_key_label():
    package, key = signed_export()
    other = Ed25519PrivateKey.generate()
    forged = handoff.read(doc(), export_signing_key=other).to_dict()
    forged["key_id"] = handoff.export_key_id(key.public_key())    # claim the pinned key's label
    with pytest.raises(SealIntegrityError, match="altered after it was signed"):
        handoff.verify_export(forged, trusted_keys=pinned(key))


def test_an_export_whose_key_is_not_trusted_is_refused_by_name():
    package, key = signed_export()
    with pytest.raises(SealIntegrityError, match="not among the trusted keys"):
        handoff.verify_export(package.to_dict(), trusted_keys=pinned(Ed25519PrivateKey.generate()))


def test_a_v3_export_is_refused_when_no_trust_is_supplied():
    package, _ = signed_export()
    with pytest.raises(SealIntegrityError, match="trusted_keys"):
        handoff.verify_export(package.to_dict())


def test_a_non_ed25519_key_is_refused_for_signing_and_for_verifying(tmp_path):
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = rsa_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption())
    path = tmp_path / "rsa.pem"
    path.write_bytes(pem)
    with pytest.raises(handoff.HandoffError, match="Ed25519"):
        handoff.load_export_signing_key(str(path))
    with pytest.raises(handoff.HandoffError, match="Ed25519"):
        handoff.load_export_public_key(rsa_key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))


def test_the_version_2_export_stays_unverifiable_in_another_process(tmp_path):
    """Documented limit, asserted: the HMAC export still needs this process's key, so a fresh process refuses it."""
    (tmp_path / "hmac.json").write_text(json.dumps(handoff.read(doc()).to_dict()))
    script = ("import json,sys\nfrom herald import handoff\n"
              "from herald.errors import SealIntegrityError\n"
              "try:\n handoff.verify_export(json.load(open(sys.argv[1])))\n"
              "except SealIntegrityError:\n print('refused')\n")
    done = subprocess.run([sys.executable, "-c", script, str(tmp_path / "hmac.json")], capture_output=True, text=True, timeout=60)
    assert done.stdout.strip() == "refused", done.stderr


def test_from_dict_reconstructs_a_genuine_v3_export_given_the_trusted_key():
    """The ordinary reconstruction path, not just the private verify_export() helper.

    Before this test could pass, Handoff.from_dict(payload) called verify_export(payload) with no way for a caller
    to pass trusted_keys through at all -- every v3 export failed reconstruction here, including a genuine one,
    because _verify_signature refuses outright when trusted_keys is empty. The public API gap, not a weakened
    check: this is the method every other from_dict regression test in this suite already uses for v1/v2 payloads."""
    package, key = signed_export()
    reloaded = handoff.Handoff.from_dict(package.to_dict(), trusted_keys=pinned(key))
    assert reloaded.export_mac_version == "3"
    assert [e.claim_id for e in reloaded.admitted] == [e.claim_id for e in package.admitted]


def test_from_dict_still_fails_closed_on_a_v3_export_with_no_trusted_keys():
    package, _ = signed_export()
    with pytest.raises(SealIntegrityError, match="trusted_keys"):
        handoff.Handoff.from_dict(package.to_dict())


def test_from_dict_still_fails_closed_on_a_v3_export_with_the_wrong_key():
    package, _ = signed_export()
    with pytest.raises(SealIntegrityError, match="not among the trusted keys"):
        handoff.Handoff.from_dict(package.to_dict(), trusted_keys=pinned(Ed25519PrivateKey.generate()))


def test_from_dict_still_fails_closed_on_a_tampered_v3_export_even_with_the_right_key():
    package, key = signed_export()
    exported = package.to_dict()
    exported["admitted"][0]["raw"] = "$9,999,999.00"
    with pytest.raises(SealIntegrityError, match="altered after it was signed"):
        handoff.Handoff.from_dict(exported, trusted_keys=pinned(key))


def test_from_dict_cannot_be_made_to_trust_a_key_the_export_itself_supplies():
    """The export names its own key_id, but that is a label, not a grant: from_dict() still only trusts whatever
    public key OBJECT the caller's own trusted_keys mapping holds under that id, never a key read from the
    payload. A key_id that happens to match trusted_keys' own key but whose signature is from a different
    private key is refused on the signature, not accepted on the label."""
    package, key = signed_export()
    other = Ed25519PrivateKey.generate()
    forged = handoff.read(doc(), export_signing_key=other).to_dict()
    forged["key_id"] = package.key_id  # claims the pinned key's label, signed by a different key
    with pytest.raises(SealIntegrityError, match="altered after it was signed"):
        handoff.Handoff.from_dict(forged, trusted_keys=pinned(key))


def test_from_dict_v1_and_v2_payloads_are_unaffected_by_the_new_parameter():
    """v1/v2 reconstruction must keep working exactly as before, whether trusted_keys is omitted or supplied."""
    v2_exported = handoff.read(doc()).to_dict()
    assert handoff.Handoff.from_dict(v2_exported).export_mac_version == "2"
    assert handoff.Handoff.from_dict(v2_exported, trusted_keys={}).export_mac_version == "2"

    legacy = dict(v2_exported)
    legacy["export_mac_version"] = "1"
    legacy.pop("key_id", None)
    legacy["export_mac"] = handoff._sign_export(
        "1", legacy["document"], legacy["herald"], legacy["admitted"], legacy["refused"]
    )
    assert handoff.Handoff.from_dict(legacy).export_mac_version == "1"


def test_from_dict_reconstructs_a_v3_export_in_a_separate_process_holding_only_the_public_pem(tmp_path):
    """Cross-process reconstruction through the public from_dict() API, mirroring
    test_a_separate_process_holding_only_the_public_pem_verifies_it, which only exercised verify_export()
    directly. The receiving process below never sees the private signing key -- only the exported JSON and a
    public PEM file -- and gets back a real, usable Handoff object, not just a passed check."""
    package, key = signed_export()
    (tmp_path / "export.json").write_text(json.dumps(package.to_dict()))
    (tmp_path / "public.pem").write_bytes(handoff.export_public_pem(key))
    script = (
        "import json,sys\n"
        "from herald import handoff\n"
        "pem = open(sys.argv[2], 'rb').read()\n"
        "key = handoff.load_export_public_key(pem)\n"
        "reloaded = handoff.Handoff.from_dict(json.load(open(sys.argv[1])), trusted_keys={handoff.export_key_id(key): key})\n"
        "print(f'reconstructed version={reloaded.export_mac_version} admitted={len(reloaded.admitted)}')\n"
    )
    done = subprocess.run([sys.executable, "-c", script, str(tmp_path / "export.json"), str(tmp_path / "public.pem")],
                          capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == f"reconstructed version=3 admitted={len(package.admitted)}", done.stderr


def test_the_signing_bytes_are_pinned_by_a_vector_tie_also_checks():
    payload = {"document": {"source_id": "d"}, "herald": {"version": "v"}, "admitted": [], "refused": [],
               "key_id": "ed25519-0000000000000000"}
    vector = handoff._signature_input({**payload, "export_mac_version": "3"})
    assert vector == (b'{"admitted":[],"document":{"source_id":"d"},"export_mac_version":"3",'
                      b'"herald":{"version":"v"},"key_id":"ed25519-0000000000000000","refused":[]}')
