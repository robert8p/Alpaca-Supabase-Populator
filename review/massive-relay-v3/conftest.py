"""Keep frozen pre-installation qualification outside active-release discovery.

These unchanged tests qualify the pinned v3 proposal against its original
pre-installation snapshot. Their recorded PostgreSQL/security results remain
historical evidence. Active relay, integration, PostgreSQL and diagnostic tests
under tests/ingestion retain normal collection and test the promoted release.
Explicit historical reproduction uses the documented original snapshot.
"""

collect_ignore = ["tests"]
