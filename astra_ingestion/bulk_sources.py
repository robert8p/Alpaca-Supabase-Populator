"""Original-contract source-route inventory for the 24-family Top-3,000 target.

This module is READ-ONLY staging metadata, not a source adapter, authorization,
source-completeness certificate, or an instruction to acquire data. All route
literals originate in the pinned original contracts. A wildcard declaration is
never turned into executable SQL, and physical relation existence alone does
not establish point-in-time coverage for August–September 2026.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping

from .bulk_scope import FAMILIES, ScopeError, read_contracts, sha256_text

EXACT_ROUTE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*\Z")
PATTERN_ROUTE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*\*?\Z|[A-Za-z_][A-Za-z0-9_]*\.\*\Z")
MAX_DECLARED_ROUTES = 32


@dataclass(frozen=True)
class RouteDeclaration:
    family: str
    route: str
    executable_identifier: str | None
    status: str


@dataclass(frozen=True)
class FamilyRouteInventory:
    family: str
    expected_unit_literal: str
    expected_population_definition: str
    declarations: tuple[RouteDeclaration, ...]
    status: str = "DECLARED_ROUTES_NOT_COVERAGE_CERTIFIED"


def compile_route_inventory(contract_rows: list[Mapping[str, object]]) -> tuple[FamilyRouteInventory, ...]:
    """Reconcile all 24 ORIGINAL contracts and expose only safe exact route names.

    No network request, DB access, provider call, admission or migration.
    All actual original family contracts use descriptive expected_unit literals;
    none has an explicit generic company/session enumeration authorization.
    """
    contracts = read_contracts(contract_rows)
    inventory: list[FamilyRouteInventory] = []
    for family in FAMILIES:
        contract = contracts[family]
        unit = contract.get("expected_unit")
        population = contract.get("expected_population_definition")
        routes = contract.get("existing_routes")
        if (not isinstance(unit, str) or not unit.strip() or len(unit) > 1000
                or not isinstance(population, str) or not population.strip()
                or len(population) > 4000
                or not isinstance(routes, list) or len(routes) > MAX_DECLARED_ROUTES
                or any(not isinstance(x, str) or len(x) > 200 for x in routes)
                or len(set(routes)) != len(routes)):
            raise ScopeError("original family route/expected-unit declaration malformed")
        declarations = []
        for route in routes:
            if EXACT_ROUTE.fullmatch(route):
                declarations.append(RouteDeclaration(family, route, route,
                                                     "EXACT_DECLARATION_UNVERIFIED"))
            elif PATTERN_ROUTE.fullmatch(route) and "*" in route:
                declarations.append(RouteDeclaration(family, route, None,
                                                     "WILDCARD_REQUIRES_EXPLICIT_RESOLUTION"))
            else:
                raise ScopeError("unsafe or ambiguous source declaration")
        inventory.append(FamilyRouteInventory(
            family, unit, population, tuple(declarations),
            "NO_DECLARED_ROUTE" if not declarations else "DECLARED_ROUTES_NOT_COVERAGE_CERTIFIED",
        ))
    if len(inventory) != 24 or tuple(x.family for x in inventory) != FAMILIES:
        raise ScopeError("24-family declaration inventory incomplete")
    return tuple(inventory)


def coverage_disposition(item: FamilyRouteInventory, relation_observations: Mapping[str, bool]) -> str:
    """Relation existence is only an engineering preflight; never DATA_ACCEPTED.

    Wildcards and missing or unobserved relations remain outstanding.
    A true observation cannot imply the required source window, lifecycle,
    timestamps, per-family denominators, or permissible provider entitlement.
    """
    if item.family not in FAMILIES or not isinstance(relation_observations, Mapping):
        raise ScopeError("unbound relation-observation inventory")
    if any(type(v) is not bool for v in relation_observations.values()):
        raise ScopeError("relation observations must have explicit boolean evidence")
    if not item.declarations:
        return "NO_DECLARED_ROUTE"
    if any(x.executable_identifier is None for x in item.declarations):
        return "UNRESOLVED_ROUTE_PATTERN"
    if any(relation_observations.get(x.route) is not True for x in item.declarations):
        return "UNVERIFIED_OR_MISSING_RELATION"
    return "ROUTES_EXIST_WINDOW_AND_COVERAGE_UNVERIFIED"
