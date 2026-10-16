import base64
import json
import os
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parent
DATABASE_PATH = Path(
    os.environ.get("THISORTHAT_DATABASE", ROOT / "thisorthat.sqlite3")
)
MAX_REQUEST_SIZE = 10 * 1024 * 1024
MAX_IMAGE_SIZE = 2 * 1024 * 1024
IMAGE_PATTERN = re.compile(r"^data:image/jpeg;base64,([A-Za-z0-9+/=]+)$")
BUILTIN_BASELINE_VOTES = {
    1: (78, 42),
    2: (65, 35),
    3: (55, 45),
    4: (40, 60),
    5: (45, 55),
    6: (52, 48),
    7: (48, 52),
    8: (60, 40),
    9: (58, 42),
    10: (62, 38),
}


def connect_database():
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def database():
    connection = connect_database()
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize_database():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with database() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS polls (
                id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                question TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS poll_options (
                poll_id TEXT NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
                position INTEGER NOT NULL,
                name TEXT NOT NULL,
                image TEXT NOT NULL,
                PRIMARY KEY (poll_id, position)
            );

            CREATE TABLE IF NOT EXISTS votes (
                poll_id TEXT NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
                voter_id TEXT NOT NULL,
                option_index INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (poll_id, voter_id)
            );

            CREATE TABLE IF NOT EXISTS builtin_votes (
                poll_id INTEGER NOT NULL,
                voter_id TEXT NOT NULL,
                option_index INTEGER NOT NULL CHECK (option_index IN (0, 1)),
                created_at TEXT NOT NULL,
                PRIMARY KEY (poll_id, voter_id)
            );

            CREATE INDEX IF NOT EXISTS polls_created_at
                ON polls(created_at);
            """
        )


def poll_from_row(connection, poll_row, voter_id=None):
    options = connection.execute(
        """
        SELECT poll_options.name, poll_options.image,
               COUNT(votes.voter_id) AS vote_count
        FROM poll_options
        LEFT JOIN votes
            ON votes.poll_id = poll_options.poll_id
            AND votes.option_index = poll_options.position
        WHERE poll_options.poll_id = ?
        GROUP BY poll_options.position
        ORDER BY poll_options.position
        """,
        (poll_row["id"],),
    ).fetchall()

    has_voted = False
    if voter_id:
        has_voted = connection.execute(
            "SELECT 1 FROM votes WHERE poll_id = ? AND voter_id = ?",
            (poll_row["id"], voter_id),
        ).fetchone() is not None

    return {
        "id": poll_row["id"],
        "question": poll_row["question"],
        "category": poll_row["category"],
        "description": poll_row["description"],
        "createdAt": poll_row["created_at"],
        "options": [
            {
                "name": option["name"],
                "image": option["image"],
                "votes": option["vote_count"],
            }
            for option in options
        ],
        "hasVoted": has_voted,
    }


class PollRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def translate_path(self, path):
        translated = Path(super().translate_path(path)).resolve()
        try:
            relative = translated.relative_to(ROOT)
        except ValueError:
            return str(ROOT / "__not_found__")

        private_files = {
            DATABASE_PATH.resolve(),
            Path(str(DATABASE_PATH.resolve()) + "-shm"),
            Path(str(DATABASE_PATH.resolve()) + "-wal"),
        }
        if (
            translated in private_files
            or translated.name.endswith((".sqlite3", ".db", ".py", ".pyc"))
            or any(part.startswith(".") for part in relative.parts)
        ):
            return str(ROOT / "__not_found__")
        return str(translated)

    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ValueError("Invalid request length.") from error

        if length <= 0 or length > MAX_REQUEST_SIZE:
            raise ValueError("Request must contain JSON under 10 MB.")

        try:
            payload = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("Request body must be valid JSON.") from error

        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object.")

        return payload

    @staticmethod
    def required_text(value, name, maximum):
        if value is None:
            raise ValueError(f"{name} is required.")
        if not isinstance(value, str):
            raise ValueError(f"{name} must be text.")
        value = value.strip()
        if not value:
            raise ValueError(f"{name} is required.")
        if len(value) > maximum:
            raise ValueError(f"{name} must be {maximum} characters or fewer.")
        return value

    @staticmethod
    def validate_image(value):
        if not isinstance(value, str) or len(value) > MAX_IMAGE_SIZE * 2:
            raise ValueError("Each poll image must be a JPEG under 2 MB.")

        match = IMAGE_PATTERN.fullmatch(value)
        if not match:
            raise ValueError("Poll images must be uploaded as JPEG images.")

        try:
            image_bytes = base64.b64decode(match.group(1), validate=True)
        except ValueError as error:
            raise ValueError("A poll image is not valid base64 data.") from error

        if len(image_bytes) > MAX_IMAGE_SIZE:
            raise ValueError("Each poll image must be under 2 MB.")
        if not image_bytes.startswith(b"\xff\xd8\xff"):
            raise ValueError("Poll images must contain valid JPEG data.")

        return value

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self.send_json(200, {"status": "ok"})
            return

        builtin_match = re.fullmatch(
            r"/api/builtin-polls/(\d+)/votes", parsed.path
        )
        if builtin_match:
            self.get_builtin_votes(int(builtin_match.group(1)), parsed.query)
            return

        if parsed.path != "/api/polls":
            super().do_GET()
            return

        query = parse_qs(parsed.query)
        owner_id = query.get("ownerId", [None])[0]
        voter_id = query.get("voterId", [None])[0]

        try:
            with database() as connection:
                if owner_id:
                    rows = connection.execute(
                        "SELECT * FROM polls WHERE owner_id = ? ORDER BY created_at DESC",
                        (owner_id,),
                    ).fetchall()
                else:
                    rows = connection.execute(
                        "SELECT * FROM polls ORDER BY created_at DESC"
                    ).fetchall()

                polls = [
                    poll_from_row(connection, row, voter_id)
                    for row in rows
                ]
            self.send_json(200, {"polls": polls})
        except sqlite3.Error:
            self.log_error("Database error while loading polls")
            self.send_json(500, {"error": "Unable to load polls from the database."})

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            payload = self.read_json()
            if parsed.path == "/api/polls":
                self.create_poll(payload)
                return

            builtin_match = re.fullmatch(
                r"/api/builtin-polls/(\d+)/votes", parsed.path
            )
            if builtin_match:
                self.cast_builtin_vote(int(builtin_match.group(1)), payload)
                return

            match = re.fullmatch(r"/api/polls/([^/]+)/votes", parsed.path)
            if match:
                self.cast_vote(match.group(1), payload)
                return

            self.send_json(404, {"error": "API endpoint not found."})
        except ValueError as error:
            self.send_json(400, {"error": str(error)})
        except sqlite3.Error:
            self.log_error("Database error while saving poll data")
            self.send_json(500, {"error": "Unable to save poll data to the database."})

    def do_DELETE(self):
        parsed = urlparse(self.path)
        match = re.fullmatch(r"/api/polls/([^/]+)", parsed.path)
        if not match:
            self.send_json(404, {"error": "API endpoint not found."})
            return

        owner_id = parse_qs(parsed.query).get("ownerId", [""])[0]
        if not owner_id:
            self.send_json(400, {"error": "Poll owner is required."})
            return

        try:
            with database() as connection:
                result = connection.execute(
                    "DELETE FROM polls WHERE id = ? AND owner_id = ?",
                    (match.group(1), owner_id),
                )
                if result.rowcount == 0:
                    self.send_json(404, {"error": "Poll not found or not owned by you."})
                    return
            deleted = result.rowcount > 0
            if deleted:
                self.send_json(200, {"deleted": True})
        except sqlite3.Error:
            self.log_error("Database error while deleting a poll")
            self.send_json(500, {"error": "Unable to delete the poll from the database."})

    def create_poll(self, payload):
        owner_id = self.required_text(payload.get("ownerId"), "Poll owner", 100)
        question = self.required_text(payload.get("question"), "Question", 120)
        category = self.required_text(payload.get("category"), "Category", 40)
        description = payload.get("description", "")
        if not isinstance(description, str) or len(description) > 250:
            raise ValueError("Description must be 250 characters or fewer.")

        options = payload.get("options")
        if not isinstance(options, list) or len(options) not in (2, 3):
            raise ValueError("A poll must have two or three options.")

        validated_options = []
        for option in options:
            if not isinstance(option, dict):
                raise ValueError("Each poll option must be an object.")
            name = self.required_text(option.get("name"), "Option name", 70)
            image = self.validate_image(option.get("image"))
            validated_options.append((name, image))

        poll_id = "community_" + uuid.uuid4().hex
        created_at = datetime.now(timezone.utc).isoformat()

        with database() as connection:
            connection.execute(
                """
                INSERT INTO polls
                    (id, owner_id, question, category, description, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (poll_id, owner_id, question, category, description.strip(), created_at),
            )
            connection.executemany(
                """
                INSERT INTO poll_options (poll_id, position, name, image)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (poll_id, index, name, image)
                    for index, (name, image) in enumerate(validated_options)
                ],
            )
            row = connection.execute(
                "SELECT * FROM polls WHERE id = ?", (poll_id,)
            ).fetchone()
            poll = poll_from_row(connection, row, owner_id)

        self.send_json(201, {"poll": poll})

    @staticmethod
    def builtin_vote_counts(connection, poll_id, voter_id):
        counts = connection.execute(
            """
            SELECT option_index, COUNT(*) AS vote_count
            FROM builtin_votes
            WHERE poll_id = ?
            GROUP BY option_index
            """,
            (poll_id,),
        ).fetchall()
        baseline_a, baseline_b = BUILTIN_BASELINE_VOTES.get(poll_id, (0, 0))
        vote_counts = [baseline_a, baseline_b]
        for row in counts:
            vote_counts[row["option_index"]] += row["vote_count"]

        previous_vote = connection.execute(
            """
            SELECT option_index FROM builtin_votes
            WHERE poll_id = ? AND voter_id = ?
            """,
            (poll_id, voter_id),
        ).fetchone()

        return {
            "optionA": vote_counts[0],
            "optionB": vote_counts[1],
            "hasVoted": previous_vote is not None,
            "optionIndex": previous_vote["option_index"] if previous_vote else None,
        }

    @staticmethod
    def validate_builtin_poll_id(poll_id):
        if not 1 <= poll_id <= 26:
            raise ValueError("Built-in poll not found.")

    def get_builtin_votes(self, poll_id, query_string):
        try:
            self.validate_builtin_poll_id(poll_id)
            query = parse_qs(query_string)
            voter_id = self.required_text(
                query.get("voterId", [None])[0], "Voter", 100
            )
            with database() as connection:
                votes = self.builtin_vote_counts(connection, poll_id, voter_id)
            self.send_json(200, votes)
        except ValueError as error:
            self.send_json(400, {"error": str(error)})
        except sqlite3.Error:
            self.log_error("Database error while loading built-in poll votes")
            self.send_json(500, {"error": "Unable to load poll votes from the database."})

    def cast_builtin_vote(self, poll_id, payload):
        self.validate_builtin_poll_id(poll_id)
        voter_id = self.required_text(payload.get("voterId"), "Voter", 100)
        option_index = payload.get("optionIndex")
        if type(option_index) is not int or option_index not in (0, 1):
            raise ValueError("Choose a valid poll option.")

        with database() as connection:
            connection.execute(
                """
                INSERT INTO builtin_votes
                    (poll_id, voter_id, option_index, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (poll_id, voter_id) DO UPDATE SET
                    option_index = excluded.option_index,
                    created_at = excluded.created_at
                """,
                (
                    poll_id,
                    voter_id,
                    option_index,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            votes = self.builtin_vote_counts(connection, poll_id, voter_id)
        self.send_json(200, votes)

    def cast_vote(self, poll_id, payload):
        voter_id = self.required_text(payload.get("voterId"), "Voter", 100)
        option_index = payload.get("optionIndex")
        if type(option_index) is not int or not 0 <= option_index < 3:
            raise ValueError("Choose a valid poll option.")

        with database() as connection:
            poll_row = connection.execute(
                "SELECT * FROM polls WHERE id = ?", (poll_id,)
            ).fetchone()
            if poll_row is None:
                self.send_json(404, {"error": "Poll not found."})
                return

            option_count = connection.execute(
                "SELECT COUNT(*) FROM poll_options WHERE poll_id = ?",
                (poll_id,),
            ).fetchone()[0]
            if option_index >= option_count:
                self.send_json(400, {"error": "That poll option does not exist."})
                return

            already_voted = connection.execute(
                "SELECT 1 FROM votes WHERE poll_id = ? AND voter_id = ?",
                (poll_id, voter_id),
            ).fetchone()
            if already_voted:
                self.send_json(409, {"error": "You have already voted on this poll."})
                return

            try:
                connection.execute(
                    """
                    INSERT INTO votes (poll_id, voter_id, option_index, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        poll_id,
                        voter_id,
                        option_index,
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
            except sqlite3.IntegrityError:
                self.send_json(409, {"error": "You have already voted on this poll."})
                return
            poll = poll_from_row(connection, poll_row, voter_id)

        self.send_json(201, {"poll": poll})


def main():
    initialize_database()
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), PollRequestHandler)
    display_host = "127.0.0.1" if host == "0.0.0.0" else host
    print(f"This or That is running at http://{display_host}:{port}")
    print(f"SQLite database: {DATABASE_PATH}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping This or That server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
