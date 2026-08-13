from pathlib import Path

runtime_path = Path("app/e003c_runtime.py")
runtime = runtime_path.read_text()

old = '''    deployment_id_ok = bool(identity.deployment_id and identity.deployment_id.startswith("dep-"))
    repo_ok = identity.repo_slug == "robert8p/Alpaca-Supabase-Populator"
'''
new = '''    instance_id_ok = bool(
        identity.service_id.startswith("srv-")
        and identity.instance_id.startswith(f"{identity.service_id}-")
        and len(identity.instance_id) > len(identity.service_id) + 1
    )
    repo_ok = identity.repo_slug == "robert8p/Alpaca-Supabase-Populator"
    independent_render_identity_ok = bool(
        git_matches_release
        and branch_matches
        and service_type_ok
        and service_name_ok
        and service_id_ok
        and instance_id_ok
        and repo_ok
    )
    deployment_id_present = bool(identity.deployment_id)
    deployment_id_format_ok = bool(
        deployment_id_present
        and identity.deployment_id is not None
        and identity.deployment_id.startswith("dep-")
    )
    deployment_id_ok = deployment_id_format_ok if deployment_id_present else independent_render_identity_ok
    deployment_identity_source = "render_deployment_id" if deployment_id_present else "independent_render_identity"
'''
assert old in runtime
runtime = runtime.replace(old, new, 1)

old_ok = '''            git_matches_release
            and branch_matches
            and service_type_ok
            and service_name_ok
            and service_id_ok
            and deployment_id_ok
            and repo_ok
'''
assert old_ok in runtime
runtime = runtime.replace(old_ok, '''            independent_render_identity_ok
            and deployment_id_ok
''', 1)

old_fields = '''        "deployment_id": identity.deployment_id,
        "deployment_id_ok": deployment_id_ok,
        "repo_slug": identity.repo_slug,
'''
new_fields = '''        "instance_id": identity.instance_id,
        "instance_id_ok": instance_id_ok,
        "deployment_id": identity.deployment_id,
        "deployment_id_present": deployment_id_present,
        "deployment_id_format_ok": deployment_id_format_ok,
        "deployment_id_ok": deployment_id_ok,
        "deployment_identity_source": deployment_identity_source,
        "independent_render_identity_ok": independent_render_identity_ok,
        "repo_slug": identity.repo_slug,
'''
assert old_fields in runtime
runtime_path.write_text(runtime.replace(old_fields, new_fields, 1))

tests_path = Path("tests/test_e003c_runtime.py")
tests = tests_path.read_text().replace('instance_id="instance"', 'instance_id="srv-test-instance"')
tests += Path("tests/e003c_release_pin_render_cases.txt").read_text()
tests_path.write_text(tests)

Path("tests/e003c_release_pin_render_cases.txt").unlink()
Path("scripts/repair_e003c_release_pin.py").unlink()
Path(".github/workflows/e003c-release-pin-fallback.yml").unlink()
