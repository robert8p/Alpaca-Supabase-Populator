"""Keep frozen review candidates outside the executable pytest suite.

These byte-preserved tests document a held security review. They import relay
modules that are intentionally absent from the production release. Active tests
under the repository's tests/ directory retain their normal collection rules.
"""

collect_ignore = ["candidates/tests"]
