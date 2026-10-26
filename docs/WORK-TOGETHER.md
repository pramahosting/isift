# Work together on a file in a meeting

## What it does
In a meeting, open **More, Work together**. Pick one of your notes, documents (WordPerfect), spreadsheets (SpreadTable), presentations (PowerPresentation) or whiteboards, or start a blank one. Everyone in the meeting sees it live.

## Who can edit
- The owner (and any host) decides who edits. **Let someone edit…**, pick a person, press **Allow**.
- One person edits at a time, so nobody's changes are overwritten. Everyone else watches the changes appear.
- Anyone can press **Ask to edit**; the owner gets a bar with **Allow / Not now**.
- The owner or a host can **Take editing back** or **Stop sharing** at any time. If the person editing leaves, editing returns to the owner. If the owner leaves, sharing ends and everyone keeps the last version they saw (**Save a copy**).
- Webinar attendees only watch.

## Saving
The owner's saved file is updated automatically while people edit. Anyone signed in can press **Save a copy** to keep their own copy. Guests can take part but have no files to share.

## How it works (for developers)
- Room WebSocket messages: `collab_open`, `collab_edit`, `collab_give`, `collab_take`, `collab_close`, `collab_ask` (server: `routes_rooms.py`, state in `state["collab"]`). The server only accepts edits from the current holder, limits a file to 1,500,000 characters and 12 edits per second, and sends the current file to anyone who joins later.
- Browser: `frontend/src/Collab.tsx` (the panel) and the handlers in `Room.tsx`. The editors are the same ones used in the workspace. Others see changes by the editor re-opening with the latest content.
- Edits are whole-file snapshots (about every 0.25 s), which is why one person edits at a time. Several people typing in the same file at once would need merging (a CRDT), which is not built.
- Tests: `backend/tests/test_collab.py`.
