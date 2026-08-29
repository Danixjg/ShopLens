# Data provenance and integrity

The frozen 50,000-row catalog is derived from the Amazon Reviews 2023
`Clothing_Shoes_and_Jewelry` category and joined on `parent_asin`. It is a
release asset rather than a Git-tracked file.

Setup verifies the organizer-published checksum of `catalog.jsonl.gz` before
decompression. The participant-kit release values verified on 2026-08-29 are:

```text
catalog.jsonl.gz  07fd142631fd6b03e2b4d09988c3eb7d53720e9d57010c79db48eeaada50a8f8
catalog.jsonl     da979b05a68af864cb0dcf9ee6a81c010c7e66a57978ad286c7a2e005fc69a67
rows              50000
```

At runtime, the Agent automatically verifies these decompressed bytes whenever
the official default path is used. `SHOPLENS_CATALOG_SHA256` enables the same
check for a custom path; the official path has no bypass. Loading fails on a checksum mismatch, a missing
identifier, or a duplicate identifier. The loader exposes immutable product
records and the system never writes to the catalog.

The released public set contains 200 labeled development sessions. The local
ablation runner creates its deterministic stratified 120/80 split without
editing that source file. Reportable runs pin its SHA-256 to
`857259f7a438e6188ac63e18995b6ff4489bfcfc4a716a798b9a2aa0ee8f7579`,
evaluate private immutable input snapshots, and rebuild dense vectors from the
verified vendored model in-process.
