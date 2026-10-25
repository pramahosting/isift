# What the iSift assistant reads

The assistant answers from `backend/app/knowledge/kb.json`: pieces of the user manuals, the website, the workspace tiles, meeting tools, module list, and the Webinars / isiftmail guides.
Each question retrieves the best pieces (`app/services/kb.py`) and passes them to the model; without a model it replies with the best matching piece.

- Regenerate after changing manuals, landing page or docs: `AUTH_MODE=local DATABASE_URL=sqlite+aiosqlite:////tmp/kb.db python backend/tools/build_knowledge.py`
- Pieces marked `admin` (administration, server setup) are given only to a signed-in administrator.
- Operator docs (deployment, secrets) are never included.
- The Administration manual is not on the website: it is served only at `GET /api/v1/admin/manual` to administrators (Admin Console button).
