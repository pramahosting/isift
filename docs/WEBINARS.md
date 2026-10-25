# Webinars

A webinar is a normal iSift meeting room with an audience layer on top: people register, panelists and the host speak, attendees watch, and the host decides who else may speak.

## For the host (Meetings > Webinars)
1. **Schedule a webinar**: title, description, date and length, panelists, registration (automatic or manual approval, capacity, extra questions), chat mode, Q&A and reminder options.
2. Share the **registration page** (`#/webinar/<id>`). Each registrant gets an email with a personal link; panelists get their own links and a calendar file.
3. Open the room early. With *Practice session* on, attendees wait on a holding screen until you press **Go live**.
4. In the room, the **Q&A** panel has three tabs: Q&A, Polls and People.
5. After it ends: Reports (registered, attended, watch time, questions, poll votes), CSV downloads, and follow-up emails to those who came or missed it.

## Who can do what in the room
| Role | Hears / sees | Speaks | Chat |
|---|---|---|---|
| Host, panelist | everyone | yes | everyone |
| Speaker (attendee the host invited) | everyone | yes, until moved back | as chat mode allows |
| Attendee | the stage only | **never** (server enforces mic, camera and screen off) | per chat mode |

- **Mute and video off**: mute or stop the video of any speaker, or *Mute all speakers* / *Mute and video off*.
- **Let people speak**: tick one or many attendees and press *Let N speak*, or use *Let speak* on one person. They join the stage with the microphone muted and unmute themselves; you can mute them again at any time, and *Back to watching* returns them to view-only.
- **Private questions**: the default chat mode is **Goes to the host only**. Attendee chat messages reach the host (and co-hosts) and are never shown to other attendees. Other modes: host and panelists, everyone, off.
- **Q&A**: attendees ask (optionally anonymous), upvote; staff answer in writing, mark *answered live*, dismiss or reopen. Anonymous names are hidden from attendees.
- **Polls**: prepared on the webinar page, launched and ended from the room, results shared or kept private. Single or multiple choice.
- **Raise hand**: the host sees hands first in the People list and can lower them.

## Setup and limits
- Module **Webinars** (Admin Console, Modules) and the plan entitlement **Allow webinars** (off on Basic, on for paid plans and admins; per user in Admin).
- Admin Console, Meeting platforms, *Webinars*: `webinar_max_attendees` (default 500) and `webinar_mesh_max` (default 40).
- Emails use the system mail sender. Reminders run from the background worker every minute (day before, hour before, optional automatic follow-up).
- Large audiences need the Cloudflare Realtime video server (SFU) configured. Webinars use it automatically. Without it, video is peer to peer and the number of watchers is capped by `webinar_mesh_max`.

## Not tested here
- Delivery to hundreds of simultaneous viewers through the real Cloudflare server.
- Real email delivery (tests capture the emails).
- Browser behaviour beyond Chromium with fake camera and microphone.
