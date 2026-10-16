import base64
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

import server


class PollDatabaseApiTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        database_path = Path(self.temporary_directory.name) / "test.sqlite3"
        self.database_path_patch = patch.object(server, "DATABASE_PATH", database_path)
        self.database_path_patch.start()
        server.initialize_database()

        self.http_server = ThreadingHTTPServer(
            ("127.0.0.1", 0), server.PollRequestHandler
        )
        self.server_thread = threading.Thread(
            target=self.http_server.serve_forever, daemon=True
        )
        self.server_thread.start()
        self.base_url = "http://127.0.0.1:" + str(self.http_server.server_port)
        self.image = "data:image/jpeg;base64," + base64.b64encode(
            b"\xff\xd8\xfftest"
        ).decode()

    def tearDown(self):
        self.http_server.shutdown()
        self.http_server.server_close()
        self.server_thread.join()
        self.database_path_patch.stop()
        self.temporary_directory.cleanup()

    def request_json(self, path, method="GET", payload=None):
        body = None
        headers = {}
        if payload is not None:
            body = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"

        request = Request(
            self.base_url + path,
            data=body,
            headers=headers,
            method=method,
        )

        try:
            with urlopen(request) as response:
                return response.status, json.loads(response.read())
        except HTTPError as error:
            return error.code, json.loads(error.read())

    def create_poll(self):
        status, response = self.request_json(
            "/api/polls",
            method="POST",
            payload={
                "ownerId": "owner-1",
                "question": "Coffee or tea?",
                "category": "Food",
                "description": "Choose one.",
                "options": [
                    {"name": "Coffee", "image": self.image},
                    {"name": "Tea", "image": self.image},
                ],
            },
        )
        self.assertEqual(status, 201)
        return response["poll"]["id"]

    def test_poll_creation_voting_and_duplicate_prevention(self):
        poll_id = self.create_poll()
        status, response = self.request_json(
            "/api/polls?voterId=voter-1"
        )
        self.assertEqual(status, 200)
        self.assertEqual(response["polls"][0]["options"][0]["votes"], 0)
        self.assertFalse(response["polls"][0]["hasVoted"])

        status, response = self.request_json(
            f"/api/polls/{poll_id}/votes",
            method="POST",
            payload={"voterId": "voter-1", "optionIndex": 1},
        )
        self.assertEqual(status, 201)
        self.assertTrue(response["poll"]["hasVoted"])
        self.assertEqual(response["poll"]["options"][1]["votes"], 1)

        status, response = self.request_json(
            f"/api/polls/{poll_id}/votes",
            method="POST",
            payload={"voterId": "voter-1", "optionIndex": 0},
        )
        self.assertEqual(status, 409)
        self.assertIn("already voted", response["error"])

    def test_poll_validation_and_owner_only_deletion(self):
        status, response = self.request_json(
            "/api/polls",
            method="POST",
            payload={"ownerId": "owner-1", "options": []},
        )
        self.assertEqual(status, 400)
        self.assertIn("Question is required", response["error"])

        poll_id = self.create_poll()
        status, _ = self.request_json(
            f"/api/polls/{poll_id}?ownerId=owner-2", method="DELETE"
        )
        self.assertEqual(status, 404)

        status, response = self.request_json(
            f"/api/polls/{poll_id}?ownerId=owner-1", method="DELETE"
        )
        self.assertEqual(status, 200)
        self.assertTrue(response["deleted"])

        status, response = self.request_json("/api/polls")
        self.assertEqual(status, 200)
        self.assertEqual(response["polls"], [])

    def test_builtin_votes_are_shared_and_can_be_updated(self):
        status, initial = self.request_json(
            "/api/builtin-polls/1/votes?voterId=voter-1"
        )
        self.assertEqual(status, 200)
        self.assertEqual(initial["optionA"], 78)
        self.assertEqual(initial["optionB"], 42)
        self.assertFalse(initial["hasVoted"])

        status, after_vote = self.request_json(
            "/api/builtin-polls/1/votes",
            method="POST",
            payload={"voterId": "voter-1", "optionIndex": 0},
        )
        self.assertEqual(status, 200)
        self.assertEqual(after_vote["optionA"], 79)

        status, other_browser = self.request_json(
            "/api/builtin-polls/1/votes?voterId=voter-2"
        )
        self.assertEqual(status, 200)
        self.assertEqual(other_browser["optionA"], 79)
        self.assertFalse(other_browser["hasVoted"])

        status, updated_vote = self.request_json(
            "/api/builtin-polls/1/votes",
            method="POST",
            payload={"voterId": "voter-1", "optionIndex": 1},
        )
        self.assertEqual(status, 200)
        self.assertEqual(updated_vote["optionA"], 78)
        self.assertEqual(updated_vote["optionB"], 43)
        self.assertTrue(updated_vote["hasVoted"])

    def test_server_files_are_not_served_as_static_content(self):
        for path in ("/server.py", "/test_server.py"):
            with self.subTest(path=path):
                try:
                    with urlopen(self.base_url + path):
                        self.fail("Server source files must not be served.")
                except HTTPError as error:
                    self.assertEqual(error.code, 404)


if __name__ == "__main__":
    unittest.main()
