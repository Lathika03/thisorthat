# Shared poll database

Community polls, built-in poll votes, and community poll votes are stored in a
SQLite database on the server, not in each visitor's browser. The database
file is created automatically as `thisorthat.sqlite3` the first time the
server starts.

## Run locally on Windows

1. Install Python 3.10 or newer if it is not already installed.
2. Open PowerShell in this folder.
3. Run:

   ```powershell
   python server.py
   ```

4. Open <http://127.0.0.1:8000> in your browser. Do not open the HTML files
   directly with `file://`; the pages need the API served by `server.py`.
5. Stop the server with **Ctrl+C**.

## Publish a free test URL with Render

This project includes a Render Blueprint in `render.yaml`. To create the
public test site:

1. Create a GitHub repository and upload this project's files, including
   `render.yaml` and `server.py`.
2. Sign in to Render and choose **New → Blueprint**.
3. Connect the GitHub repository and deploy the `this-or-that-demo` service.
4. Render will show the public `onrender.com` URL when the deployment succeeds.

The selected free plan stores SQLite in temporary `/tmp` storage. Polls and
votes may be erased when Render restarts or replaces the service. Keep this as
a demo only; persistent hosting requires a durable database or paid persistent
storage. The local database file is not automatically uploaded.

Creating polls, viewing community polls, voting, and deleting your own polls
use this database API. Built-in poll votes are shared too. Profile details,
saved items, and other browser-only features are unchanged.

Polls and votes that were saved in browser storage before this database was
added are not imported automatically.

## API

- `GET /api/health` checks that the server is running.
- `GET /api/polls` lists community polls and vote counts.
- `POST /api/polls` creates a community poll.
- `POST /api/polls/{id}/votes` records a vote.
- `GET /api/builtin-polls/{id}/votes` reads built-in poll results.
- `POST /api/builtin-polls/{id}/votes` records or updates a built-in poll vote.
- `DELETE /api/polls/{id}?ownerId=...` deletes a poll created by this browser.

The API uses a browser-generated ID to limit each browser to one vote per poll.
Built-in poll voters can change their choice, as before. This is a small demo,
not user authentication: visitors can bypass the limit by clearing browser
storage. For a public production site, deploy behind HTTPS, add real user
authentication and rate limiting, and use a managed database or a persistent
server disk for the SQLite file.
