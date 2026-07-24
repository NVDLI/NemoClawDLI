#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Read-only audit of irreversible GitLab project controls."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path


def credential(host: str) -> str:
    proc = subprocess.run(
        ["git", "credential", "fill"],
        input=f"protocol=https\nhost={host}\n\n",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    values = dict(line.split("=", 1) for line in proc.stdout.splitlines() if "=" in line)
    if not values.get("password"):
        raise RuntimeError("git credential fill returned no password")
    return values["password"]


def api_get(host: str, project: str, suffix: str, token: str) -> object:
    project_id = urllib.parse.quote(project, safe="")
    url = f"https://{host}/api/v4/projects/{project_id}{suffix}"
    request = urllib.request.Request(url, headers={"PRIVATE-TOKEN": token})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def live_snapshot(host: str, project: str) -> dict[str, object]:
    token = credential(host)
    return {
        "project": api_get(host, project, "", token),
        "protected_branches": api_get(host, project, "/protected_branches", token),
        "protected_tags": api_get(host, project, "/protected_tags", token),
        "approvals": api_get(host, project, "/approvals", token),
        "approval_rules": api_get(host, project, "/approval_rules", token),
        "protected_environments": api_get(host, project, "/protected_environments", token),
    }


def item(code: str, message: str, fix: str) -> dict[str, str]:
    return {"code": code, "message": message, "fix": fix}


def audit(snapshot: dict[str, object]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    project = snapshot.get("project") or {}
    if not project.get("only_allow_merge_if_pipeline_succeeds"):
        out.append(item("pipeline-not-required", "successful pipeline is not required for merge",
                        "enable only_allow_merge_if_pipeline_succeeds"))
    if not project.get("only_allow_merge_if_all_discussions_are_resolved"):
        out.append(item("discussions-not-required", "unresolved discussions do not block merge",
                        "enable only_allow_merge_if_all_discussions_are_resolved"))

    branches = snapshot.get("protected_branches") or []
    main = next((b for b in branches if b.get("name") == "main"), None)
    if not main:
        out.append(item("main-unprotected", "main has no protected-branch rule", "protect main"))
    else:
        if main.get("allow_force_push"):
            out.append(item("main-force-push", "main permits force pushes", "disable force push"))
        push_levels = [x.get("access_level", 0) for x in main.get("push_access_levels", [])]
        if not push_levels or any(level > 0 for level in push_levels):
            out.append(item("main-direct-push", "one or more roles can push directly to main",
                            "set main push access to No access; merge through reviewed MRs"))
        merge_levels = [x.get("access_level", 0) for x in main.get("merge_access_levels", [])]
        if not merge_levels or max(merge_levels) < 40:
            out.append(item("main-merge-owner", "main merge access is not assigned to maintainers",
                            "allow maintainers to merge after gates"))
        if not main.get("code_owner_approval_required"):
            out.append(item("main-code-owner-approval", "main does not require Code Owner approval",
                            "require Code Owner approval so CI and gate owners must accept trust-boundary changes"))

    tags = snapshot.get("protected_tags") or []
    release_tag = next((t for t in tags if t.get("name") in ("v*", "v*.*.*")), None)
    release_tag_users: set[int] = set()
    release_tag_groups: set[int] = set()
    if not release_tag:
        out.append(item("release-tags-unprotected", "semantic release tags have no protected-tag rule",
                        "protect v* creation for maintainers and forbid update/delete"))
    else:
        tag_levels = release_tag.get("create_access_levels", [])
        release_tag_users = {
            level.get("user_id") for level in tag_levels if level.get("user_id")
        }
        release_tag_groups = {
            level.get("group_id") for level in tag_levels if level.get("group_id")
        }
        if not tag_levels or any(not (level.get("user_id") or level.get("group_id")) for level in tag_levels):
            out.append(item("release-tag-role-bypass", "release tags can be created by a broad role or bot",
                            "name eligible human users or a human-owned release group explicitly"))

    approvals = snapshot.get("approvals") or {}
    if not approvals.get("reset_approvals_on_push"):
        out.append(item("approval-not-reset", "new commits do not reset old approvals",
                        "enable reset approvals on push"))
    if approvals.get("merge_requests_author_approval"):
        out.append(item("author-can-approve", "MR authors can approve their own change",
                        "disable author approval"))
    if not approvals.get("merge_requests_disable_committers_approval"):
        out.append(item("committer-can-approve", "a committer can satisfy the review gate",
                        "disable committer approval"))
    environments = snapshot.get("protected_environments") or []
    human_review = next((env for env in environments if env.get("name") == "human-review"), None)
    if not human_review:
        out.append(item("human-review-unprotected", "the blocking human-review action is not protected",
                        "protect human-review and name eligible operators directly"))
    else:
        reviewers = human_review.get("deploy_access_levels", [])
        if not reviewers or any(not (level.get("user_id") or level.get("group_id")) for level in reviewers):
            out.append(item("human-review-role-bypass", "human-review allows a broad role or bot",
                            "name human operators or a human-owned group explicitly"))

    production = next((env for env in environments if env.get("name") == "production"), None)
    if not production:
        out.append(item("production-unprotected", "production deployment environment is not protected",
                        "protect production with explicit human deployers"))
    else:
        deployers = production.get("deploy_access_levels", [])
        if not deployers or any(not (level.get("user_id") or level.get("group_id")) for level in deployers):
            out.append(item("production-role-bypass", "production deployment allows a broad role or bot",
                            "name human deployers or a human-owned release group explicitly"))
        approval_rules = [rule for rule in production.get("approval_rules", [])
                          if rule.get("required_approvals", 0) > 0]
        if any(not (rule.get("user_id") or rule.get("group_id")) for rule in approval_rules):
            out.append(item("production-approval-role-bypass",
                            "production approval allows a broad role instead of a named principal",
                            "name human approvers or a human-owned release group explicitly"))
        deployer_users = {level.get("user_id") for level in deployers if level.get("user_id")}
        approver_users = {rule.get("user_id") for rule in approval_rules if rule.get("user_id")}
        deployer_groups = {level.get("group_id") for level in deployers if level.get("group_id")}
        approver_groups = {rule.get("group_id") for rule in approval_rules if rule.get("group_id")}
        sole_operator_rule = (len(deployer_users) == 1 and approver_users == deployer_users
                              and all(not rule.get("group_id") for rule in approval_rules))
        if (approval_rules and sole_operator_rule
                and not project.get("allow_pipeline_trigger_approve_deployment")):
            out.append(item("production-self-approval-deadlock",
                            "the sole production operator cannot approve a deployment they trigger",
                            "enable pipeline-triggerer deployment approval or assign an independent approver"))
        if (project.get("allow_pipeline_trigger_approve_deployment")
                and (not sole_operator_rule or deployer_groups or approver_groups)):
            out.append(item("production-self-approval-too-broad",
                            "self-approval mode is not limited to one matching named deployer and approver",
                            "keep one explicit operator or disable self-approval and require independent review"))
        if (project.get("allow_pipeline_trigger_approve_deployment") and sole_operator_rule
                and release_tag and (release_tag_users != deployer_users or release_tag_groups)):
            out.append(item("release-tag-operator-drift",
                            "release tag creators do not match the sole production operator",
                            "make the v* creator set exactly match the named production deployer, "
                            "or move all release controls to a reviewed multi-operator model"))
    return out


def good_fixture() -> dict[str, object]:
    return {
        "project": {"only_allow_merge_if_pipeline_succeeds": True,
                    "only_allow_merge_if_all_discussions_are_resolved": True,
                    "allow_pipeline_trigger_approve_deployment": True},
        "protected_branches": [{"name": "main", "allow_force_push": False,
                                "code_owner_approval_required": True,
                                "push_access_levels": [{"access_level": 0}],
                                "merge_access_levels": [{"access_level": 40}]}],
        "protected_tags": [{"name": "v*", "create_access_levels": [{"access_level": 40, "user_id": 10}]}],
        "approvals": {"reset_approvals_on_push": True, "merge_requests_author_approval": False,
                      "merge_requests_disable_committers_approval": True},
        "approval_rules": [],
        "protected_environments": [
            {"name": "human-review", "deploy_access_levels": [{"user_id": 10}]},
            {"name": "production", "deploy_access_levels": [{"user_id": 10}],
             "approval_rules": [{"user_id": 10, "required_approvals": 1}]},
        ],
    }


def self_test() -> list[str]:
    base = good_fixture()
    if audit(base):
        return ["clean governance fixture rejected"]
    mutations = (
        ("pipeline-not-required", lambda x: x["project"].update(only_allow_merge_if_pipeline_succeeds=False)),
        ("discussions-not-required", lambda x: x["project"].update(only_allow_merge_if_all_discussions_are_resolved=False)),
        ("main-direct-push", lambda x: x["protected_branches"][0].update(push_access_levels=[{"access_level": 40}])),
        ("main-force-push", lambda x: x["protected_branches"][0].update(allow_force_push=True)),
        ("main-code-owner-approval", lambda x: x["protected_branches"][0].update(code_owner_approval_required=False)),
        ("release-tags-unprotected", lambda x: x.update(protected_tags=[])),
        ("release-tag-role-bypass", lambda x: x["protected_tags"][0].update(create_access_levels=[{"access_level": 40}])),
        ("release-tag-operator-drift",
         lambda x: x["protected_tags"][0]["create_access_levels"].append(
             {"access_level": 40, "user_id": 11})),
        ("approval-not-reset", lambda x: x["approvals"].update(reset_approvals_on_push=False)),
        ("author-can-approve", lambda x: x["approvals"].update(merge_requests_author_approval=True)),
        ("committer-can-approve", lambda x: x["approvals"].update(merge_requests_disable_committers_approval=False)),
        ("human-review-unprotected", lambda x: x.update(protected_environments=x["protected_environments"][1:])),
        ("human-review-role-bypass", lambda x: x["protected_environments"][0].update(deploy_access_levels=[{"access_level": 40}])),
        ("production-unprotected", lambda x: x.update(protected_environments=x["protected_environments"][:1])),
        ("production-role-bypass", lambda x: x["protected_environments"][1].update(deploy_access_levels=[{"access_level": 40}])),
        ("production-approval-role-bypass", lambda x: x["protected_environments"][1].update(approval_rules=[{"access_level": 40, "required_approvals": 1}])),
        ("production-self-approval-deadlock", lambda x: x["project"].update(allow_pipeline_trigger_approve_deployment=False)),
        ("production-self-approval-too-broad", lambda x: x["protected_environments"][1]["deploy_access_levels"].append({"user_id": 11})),
    )
    failures: list[str] = []
    for expected, mutate in mutations:
        fixture = json.loads(json.dumps(base))
        mutate(fixture)
        if expected not in {x["code"] for x in audit(fixture)}:
            failures.append(f"mutation escaped detector: {expected}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.environ.get("CI_SERVER_HOST", "gitlab.com"))
    parser.add_argument("--project", default=os.environ.get("CI_PROJECT_ID", ""))
    parser.add_argument("--snapshot", help="read a previously captured aggregate JSON instead of GitLab")
    parser.add_argument("--report")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if not args.self_test and not args.snapshot and not args.project:
        parser.error("--project or CI_PROJECT_ID is required without --snapshot")
    if args.self_test:
        failures = self_test()
        findings = [item("self-test", x, "repair the detector") for x in failures]
        label = "mutation self-test"
    else:
        snapshot = json.loads(Path(args.snapshot).read_text()) if args.snapshot else live_snapshot(args.host, args.project)
        findings = audit(snapshot)
        label = f"{args.host}/{args.project}"
    result = {"schema": "nemoclaw-gitlab-governance/1", "ok": not findings,
              "target": label, "findings": findings}
    if args.report:
        path = Path(args.report)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2) + "\n")
    if findings:
        print(f"gitlab governance: FAIL ({len(findings)})")
        for finding in findings:
            print(f"  [{finding['code']}] {finding['message']}")
            print(f"    fix: {finding['fix']}")
        return 1
    print(f"gitlab governance: OK ({label})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
