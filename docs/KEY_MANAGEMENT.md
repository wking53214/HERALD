# Signing-key management

This page covers the keys HERALD uses to sign exports, what HERALD does and does not do with them, and what an operator and a consumer must arrange themselves.

## Two kinds of key

**1. The process-local issuer key (version 2 exports and decision MACs).** HERALD generates 32 random bytes when the process starts. The key is never written to disk, never exported, and is lost when the process exits. It can only verify records made by the same process. There is nothing to rotate, store, or revoke, and nothing a consumer can pin.

**2. The export signing key (version 3 exports).** This is an Ed25519 private key that the operator creates outside HERALD and provides as a PKCS#8 PEM file. HERALD reads it with `load_export_signing_key` and refuses any other key type. HERALD does not generate, store, rotate, or revoke this key. Those duties belong to the operator.

## What HERALD provides

- **Key identifier.** Each version 3 export names its key with a label: `ed25519-` followed by the first 16 hexadecimal characters of the SHA-256 hash of the public key. The label is derived from the public key and contains no secret. It is a label, not proof that the key is trusted.
- **Public key export.** `export_public_pem` produces the public key in PEM form for a consumer to pin.
- **Trusted-key verification.** `verify_export` checks a signature only against keys in the mapping the caller supplies. A signature from any other key is refused, including one whose label matches a trusted key.

## What HERALD does not provide

- No key generation, key storage, or permission checks on the private key file.
- No key registry, no rotation schedule, and no revocation list.
- No way for a consumer to learn from the export alone whether a key is current, retired, or compromised.

## Operator responsibilities

- **Generate** the Ed25519 key in an environment you control, separate from the systems that submit documents.
- **Store** the private key where only the signing service can read it. Restrict the file to that service's account. This is a recommendation, since HERALD does not enforce it.
- **Publish** the public PEM through a channel the consumer already trusts, not through the export itself.
- **Record** which key ID was in use over which period, so an export can be matched to the key that signed it.

## Consumer responsibilities

- **Pin** the public key and its key ID from an independent source. Never take the key from the export it is meant to check.
- **Hold more than one key** during a transition. `verify_export` accepts a mapping of several keys, so a new key can be added before the old one is removed.
- **Remove** a pin when its key is retired or compromised. From that point, exports signed by that key are refused.

## Rotation (operator procedure, not built into HERALD)

1. Generate a new key and publish its public PEM to consumers through a trusted channel.
2. Consumers add the new pin alongside the old one.
3. Switch the signing service to the new key.
4. After the last export signed by the old key has been verified, consumers remove the old pin.

## Compromise response

1. Stop signing with the affected key.
2. Consumers remove its pin immediately. Exports signed by it are then refused.
3. Note that removing a pin does not make an old export invalid in a record system that stored it. Exports signed before the compromise remain a question for the consumer's own review. HERALD cannot say which of them were made after the key was compromised.
4. Rotate to a new key following the procedure above.

## Limits

A valid signature shows that a trusted key signed the content and that the content was not altered afterward. It does not show that a claim is true, that the source's author had authority, or that a named person was entitled to confirm a claim. See `README.md`, section 5.
