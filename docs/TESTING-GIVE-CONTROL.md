# Testing "Give control" of a shared file

You need two people (or two browsers). Use Chrome or Edge on a laptop for the host. A second laptop, a phone or a private window for the guest.

## Setup
1. **Host:** sign in, press **Start a meeting**, press **Join**. Copy the meeting link.
2. **Guest:** open the link in another browser or a private window, type a name, press **Join**. (Open rooms start with mic and camera off; that is expected.)
3. Have a PDF with at least 3 pages ready on the host's computer (a PowerPoint or Word file must be saved as PDF first).

## Test 1: share a file
1. Host: **More**, **Share a file**, choose the PDF.
2. Expect: the guest sees the first page; the host sees a page bar at the bottom (for example 1 / 5) with up and down arrows.
3. Host: press the down arrow. Expect: the guest's page changes.

## Test 2: give control
1. Host: at the bottom left of the shared file, open **Give control to…** and pick the guest.
2. Expect on the guest: a message "gave you control" and a blue bar **You control …'s file** with **Previous**, **Next**, **▲** and **▼**.
3. Expect on the host: the bar now says "<guest> has control" with **Take back**.
4. Guest: press **Next**. Expect: the host's page bar goes to the next page and everyone sees it.
5. Guest: press **▼** a few times. Expect: the document scrolls on the host and on everyone's screen.
6. Guest: press **▲** and **Previous**. Expect: the view goes back.

## Test 3: limits
1. Add a third person. Expect: they cannot see any control buttons, and cannot move the file.
2. Guest: look for any way to stop the host's sharing. Expect: there is none. Only the host has **Stop sharing**.
3. Host: press **Take back**. Expect: the guest's blue bar disappears and their buttons stop working.
4. Give control again, then host presses **Stop sharing**. Expect: control ends for the guest.
5. Give control again, then the guest leaves the meeting. Expect: the host's bar returns to the **Give control to…** list.

## Test 4: other cases
- Share the **whole screen** instead of a file: **Give control** must not appear (only files shared through iSift can be controlled).
- Webinar attendees (view-only) are not listed in **Give control to…**.
- Share a photo (JPG or PNG): it shows, and there is nothing to page.

## What is not covered
- Giving control of a real PowerPoint, Word or any program on the host's computer. Only files shared through iSift can be controlled.
- Testing was done in Chromium with a fake camera; check once with your own camera on Windows or Mac.

## Automatic tests
`cd backend && python -m pytest tests/test_give_control.py tests/test_webinars.py` (set `AUTH_MODE=local` and a `DATABASE_URL`, for example `sqlite+aiosqlite:///./t.db`).
