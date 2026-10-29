"""Deterministic, network-free source-route inventory tests."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from astra_ingestion import bulk_scope as b
from astra_ingestion import bulk_sources as s


class SourceRouteInventoryTests(unittest.TestCase):
    def setUp(self):
        self.rows = []
        for f in b.FAMILIES:
            obj = {
                "dependencies": [] if f == "REF01" else ["REF01"],
                "expected_unit": "original granular atomic unit for " + f,
                "expected_population_definition": "All applicable source records and their vintages",
                "existing_routes": ["reference.equity_resolved_security_v5"]
                 if f != "REF03" else ["market_governance.remediation_*", "market_provenance.*"],
            }
            body = b.canonical(obj)
            self.rows.append({"family_id": f, "contract_text": body,
                              "contract_sha256": b.sha256_text(body)})

    def compile(self):
        digest = b.sha256_text("\n".join(
            f + ":" + next(row["contract_sha256"] for row in self.rows if row["family_id"] == f)
            for f in sorted(b.FAMILIES)))
        with patch.object(b, "CONTRACT_SET_SHA256", digest):
            return s.compile_route_inventory(self.rows)

    def test_complete_pinned_inventory_not_data_acceptance(self):
        inventory = self.compile()
        self.assertEqual(len(inventory), 24)
        self.assertEqual(tuple(i.family for i in inventory), b.FAMILIES)
        ref = next(i for i in inventory if i.family == "REF01")
        self.assertEqual(ref.declarations[0].executable_identifier,
                         "reference.equity_resolved_security_v5")
        self.assertEqual(s.coverage_disposition(ref, {}), "UNVERIFIED_OR_MISSING_RELATION")
        self.assertEqual(
            s.coverage_disposition(ref, {"reference.equity_resolved_security_v5": True}),
            "ROUTES_EXIST_WINDOW_AND_COVERAGE_UNVERIFIED")

    def test_wildcard_does_not_turn_into_executable_relation(self):
        item = next(i for i in self.compile() if i.family == "REF03")
        self.assertEqual(len(item.declarations), 2)
        self.assertTrue(all(x.executable_identifier is None for x in item.declarations))
        self.assertEqual(s.coverage_disposition(item, {}), "UNRESOLVED_ROUTE_PATTERN")

    def test_malformed_and_unknown_sources_fail_closed(self):
        with self.assertRaises(b.ScopeError):
            s.compile_route_inventory(self.rows[:-1])
        for route in ["public.any;DROP TABLE x", "../secret", "public..table", "public.table--",
                      "https://elsewhere.example", "", "public.T*X"]:
            with self.subTest(route=route):
                body = b.canonical({"dependencies":[], "expected_unit":"a",
                                    "expected_population_definition":"all",
                                    "existing_routes":[route]})
                self.rows[0]["contract_text"] = body
                self.rows[0]["contract_sha256"] = b.sha256_text(body)
                with self.assertRaises(b.ScopeError):
                    self.compile()
        with self.assertRaises(b.ScopeError):
            s.coverage_disposition(next(i for i in self.compile() if i.family == "REF01"),
                                   {"reference.equity_resolved_security_v5": "yes"})


if __name__ == "__main__":
    unittest.main()
