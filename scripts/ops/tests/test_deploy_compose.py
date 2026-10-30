from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[3]
MOCK_COMMAND = r"""#!/usr/bin/env python3
import json
import os
from pathlib import Path
import subprocess
import sys

command = Path(sys.argv[0]).name
arguments = sys.argv[1:]


def record(value):
    with open(os.environ["DEPLOY_TEST_RECORD"], "a") as stream:
        stream.write(json.dumps(value) + "\n")


if command == "git":
    if "rev-parse" in arguments:
        print("a" * 40)
    elif "archive" in arguments:
        sys.stdout.buffer.write(b"test archive")
elif command == "ssh":
    if len(arguments) > 1 and arguments[1] == "bash":
        result = subprocess.run(
            ["/bin/bash", "-s", "--", *arguments[4:]],
            input=sys.stdin.buffer.read(),
            env=os.environ,
        )
        sys.exit(result.returncode)
    sys.stdin.buffer.read()
    record({"action": "upload"})
elif command == "sudo":
    if arguments[0] == "test":
        sys.exit(0)
    if arguments[0] == "docker":
        operation = next(
            item for item in arguments if item in {"config", "pull", "up", "ps"}
        )
        options = arguments[arguments.index(operation) + 1:]
        services = []
        index = 0
        while index < len(options):
            value = options[index]
            if value in {"--wait-timeout", "--status"}:
                index += 2
                continue
            if not value.startswith("-"):
                services.append(value)
            index += 1
        record({
            "action": operation,
            "services": services,
            "dependencies": "--no-deps" not in options,
            "remove_orphans": "--remove-orphans" in options,
            "wait": "--wait" in options,
        })
        if operation == "config":
            print("caddy\ngrafana\nfrontend\npostgres\ndb-migrate")
        if operation == "up" and os.environ.get("DEPLOY_TEST_FAIL_WAIT") == "1":
            sys.exit(1)
    elif arguments[0] == "ln":
        record({"action": "release_selected"})
    elif arguments[0] == "tee":
        data = sys.stdin.read()
        record({"action": "state_written", "commit": data.splitlines()[0]})
"""


class DeployComposeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="deploy-compose-test-")
        self.root = Path(self.temporary.name)
        self.script = self.root / "scripts" / "ops" / "deploy_compose.sh"
        self.script.parent.mkdir(parents=True)
        shutil.copy2(REPO_ROOT / "scripts" / "ops" / "deploy_compose.sh", self.script)
        command_dir = self.root / "bin"
        command_dir.mkdir()
        recorder = command_dir / "recorder"
        recorder.write_text(MOCK_COMMAND)
        recorder.chmod(0o755)
        for command in ("git", "ssh", "sudo"):
            (command_dir / command).symlink_to(recorder.name)
        self.record = self.root / "events.jsonl"
        self.environment = {
            **os.environ,
            "PATH": str(command_dir) + os.pathsep + os.environ["PATH"],
            "WEB_SEARCH_PRD_SERVER": "deployment.example.invalid",
            "DEPLOY_TEST_RECORD": str(self.record),
        }

    def tearDown(self):
        self.temporary.cleanup()

    def deploy(self, *services: str, fail_wait: bool = False):
        environment = self.environment.copy()
        if fail_wait:
            environment["DEPLOY_TEST_FAIL_WAIT"] = "1"
        result = subprocess.run(
            [str(self.script), "prd", "main", *services],
            capture_output=True,
            text=True,
            env=environment,
            check=False,
        )
        events = (
            [json.loads(line) for line in self.record.read_text().splitlines()]
            if self.record.exists()
            else []
        )
        return result, events

    def test_deploys_selected_services_without_starting_dependencies(self):
        result, events = self.deploy("caddy", "grafana")
        self.assertEqual(result.returncode, 0, result.stderr)
        pull = next(event for event in events if event["action"] == "pull")
        update = next(event for event in events if event["action"] == "up")
        self.assertEqual(pull["services"], ["caddy", "grafana"])
        self.assertEqual(update["services"], ["caddy", "grafana"])
        self.assertFalse(update["dependencies"])
        self.assertFalse(update["remove_orphans"])
        self.assertTrue(update["wait"])
        self.assertEqual(events[-1]["action"], "state_written")

    def test_deploys_the_complete_stack_when_services_are_unspecified(self):
        result, events = self.deploy()
        self.assertEqual(result.returncode, 0, result.stderr)
        update = next(event for event in events if event["action"] == "up")
        self.assertEqual(update["services"], [])
        self.assertTrue(update["dependencies"])
        self.assertTrue(update["remove_orphans"])

    def test_rejects_an_unknown_service_before_pulling_or_updating(self):
        result, events = self.deploy("unknown")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unknown service", result.stderr)
        self.assertEqual([event["action"] for event in events], ["upload", "config"])

    def test_rejects_option_arguments_before_connecting_to_the_host(self):
        result, events = self.deploy("--force-recreate")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Invalid service name", result.stderr)
        self.assertEqual(events, [])

    def test_keeps_release_state_unchanged_when_service_readiness_fails(self):
        result, events = self.deploy("caddy", "grafana", fail_wait=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(events[-1]["action"], "up")


if __name__ == "__main__":
    unittest.main()
