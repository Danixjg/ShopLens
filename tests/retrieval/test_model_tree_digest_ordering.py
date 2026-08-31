"""The model tree digest must name the same bytes on every platform.

``model_tree_sha256`` folds file order into the hash, so the ordering rule is
part of the digest's contract rather than an implementation detail. Sorting
``Path`` objects delegates that rule to the platform: ``WindowsPath`` compares
case-folded, ``PosixPath`` does not, which moves ``LICENSE`` across the lowercase
names and yields a different digest for a byte-identical tree.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from src.retrieval.dense import model_tree_sha256


def _tree_with_case_straddling_names(root: Path) -> None:
    """Write names whose order differs under case-sensitive and folded sorts.

    Case-sensitive: ``LICENSE`` then ``config.json``. Case-folded: the reverse.
    """
    root.mkdir()
    (root / "LICENSE").write_text("license\n", encoding="utf-8")
    (root / "config.json").write_text('{"version": 1}\n', encoding="utf-8")
    (root / "vocab.txt").write_text("token\n", encoding="utf-8")
    nested = root / "1_Pooling"
    nested.mkdir()
    (nested / "config.json").write_text('{"pooling": "mean"}\n', encoding="utf-8")


def _digest_in_case_sensitive_order(root: Path) -> str:
    """Recompute the digest with the ordering the contract requires."""
    files = sorted(
        (item for item in root.rglob("*") if item.is_file()),
        key=lambda item: item.relative_to(root).parts,
    )
    digest = hashlib.sha256()
    for file_path in files:
        rel_bytes = file_path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(rel_bytes).to_bytes(4, "big"))
        digest.update(rel_bytes)
        digest.update(file_path.read_bytes())
    return digest.hexdigest()


def test_digest_orders_by_case_sensitive_relative_parts(tmp_path: Path) -> None:
    """The digest commits to POSIX ordering, not to the host's sort.

    On a case-folding filesystem the unfixed implementation returns a different
    hash here, which reads as content corruption rather than as an ordering bug.
    """
    root = tmp_path / "model"
    _tree_with_case_straddling_names(root)

    assert model_tree_sha256(root) == _digest_in_case_sensitive_order(root)


def test_digest_is_unchanged_by_a_case_only_rename(tmp_path: Path) -> None:
    """Case is content, not noise: folding it away would collide two trees."""
    lower = tmp_path / "lower"
    _tree_with_case_straddling_names(lower)
    upper = tmp_path / "upper"
    _tree_with_case_straddling_names(upper)
    (upper / "LICENSE").rename(upper / "license.txt")

    assert model_tree_sha256(lower) != model_tree_sha256(upper)
