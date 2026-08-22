#!/usr/bin/env python3
"""
validate_plan.py
check a plan.yaml against the lazycatter schema

    python validate_plan.py plan.yaml

exit code 0 means valid
1 means invalid
it prints every problem it finds not just the first one
just python and pyyaml
no network
no discord
"""

import sys

try:
    import yaml
except ImportError:
    sys.exit("Missing dependency. Run: pip install pyyaml")

VALID_TYPES = {"text", "voice", "forum", "stage", "announcement"}


def validate(plan):
    """hand back a list of error strings
    empty list means its valid"""
    errors = []

    if not isinstance(plan, dict):
        return ["Top level must be a mapping (got %s)." % type(plan).__name__]

    if "categories" not in plan or not isinstance(plan["categories"], list):
        errors.append("Missing or non-list top-level 'categories'.")
        return errors

    seen_names = {}          # (type name) -> location
    seen_matches = {}        # match -> location

    for ci, cat in enumerate(plan["categories"]):
        where_cat = f"categories[{ci}]"
        if not isinstance(cat, dict):
            errors.append(f"{where_cat}: category must be a mapping.")
            continue
        if not cat.get("name"):
            errors.append(f"{where_cat}: category missing 'name'.")

        channels = cat.get("channels", [])
        if channels is None:
            channels = []
        if not isinstance(channels, list):
            errors.append(f"{where_cat}.channels: must be a list.")
            continue

        for chi, ch in enumerate(channels):
            where = f"{where_cat}.channels[{chi}]"
            if not isinstance(ch, dict):
                errors.append(f"{where}: channel must be a mapping.")
                continue

            name = ch.get("name")
            if not name:
                errors.append(f"{where}: channel missing 'name'.")

            if "match" not in ch:
                errors.append(
                    f"{where} ({name!r}): missing 'match' key. Use the current "
                    f"channel name to rename in place, or 'match: null' for a new channel."
                )

            ctype = ch.get("type", "text")
            if ctype not in VALID_TYPES:
                errors.append(
                    f"{where} ({name!r}): invalid type {ctype!r}. "
                    f"Must be one of {sorted(VALID_TYPES)}."
                )

            if name:
                key = (ctype, name)
                if key in seen_names:
                    errors.append(
                        f"{where}: duplicate {ctype} channel name {name!r} "
                        f"(also at {seen_names[key]})."
                    )
                else:
                    seen_names[key] = where

            m = ch.get("match")
            if m is not None:
                if m in seen_matches:
                    errors.append(
                        f"{where}: match {m!r} reused (also at {seen_matches[m]}). "
                        f"Each existing channel can only be claimed once."
                    )
                else:
                    seen_matches[m] = where

    archive = plan.get("archive")
    if archive is not None:
        if not isinstance(archive, list):
            errors.append("'archive' must be a list of channel names.")
        else:
            for i, a in enumerate(archive):
                if not isinstance(a, (str, int)):
                    errors.append(f"archive[{i}]: must be a channel name or ID.")

    roles = plan.get("roles")
    if roles is not None:
        if not isinstance(roles, list):
            errors.append("'roles' must be a list.")
        else:
            seen_role_matches = {}
            for ri, role in enumerate(roles):
                where = f"roles[{ri}]"
                if not isinstance(role, dict):
                    errors.append(f"{where}: role must be a mapping.")
                    continue
                if not role.get("name"):
                    errors.append(f"{where}: role missing 'name'.")
                if "match" not in role:
                    errors.append(
                        f"{where}: missing 'match' key. Use current role name/id, "
                        f"or 'match: null' for a new role."
                    )
                m = role.get("match")
                if m is not None:
                    key = str(m)
                    if key in seen_role_matches:
                        errors.append(
                            f"{where}: match {m!r} reused (also at {seen_role_matches[key]})."
                        )
                    else:
                        seen_role_matches[key] = where
                perms = role.get("permissions")
                if perms is not None and not isinstance(perms, list):
                    errors.append(f"{where}: permissions must be a list of names.")

    return errors


def main():
    if len(sys.argv) != 2:
        sys.exit("Usage: python validate_plan.py plan.yaml")
    path = sys.argv[1]
    try:
        with open(path, "r", encoding="utf-8") as f:
            plan = yaml.safe_load(f)
    except FileNotFoundError:
        sys.exit(f"File not found: {path}")
    except yaml.YAMLError as e:
        sys.exit(f"YAML parse error: {e}")

    errors = validate(plan)
    if errors:
        print(f"INVALID — {len(errors)} problem(s):")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    cats = plan["categories"]
    nchan = sum(len(c.get("channels") or []) for c in cats)
    nroles = len(plan.get("roles") or [])
    extra = f", {nroles} roles" if nroles else ""
    print(f"VALID — {len(cats)} categories, {nchan} channels{extra}.")
    sys.exit(0)


if __name__ == "__main__":
    main()
