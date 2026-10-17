# Settings needed to run iSift

Everything below can be set in **Admin settings**, which has three tabs: **Run the app** (AI, sample data, defaults), **Email and calendar**, and **Meeting platforms** (Teams, Zoom, Google Meet, built-in video). No restart is needed except the items marked *.env*, which are read at start-up. The top of Admin settings shows a live **Setup checklist** of what is still missing.

## 1. Minimum to start (nothing to configure)
Windows: double-click `app.cmd` (or the compiled `iSift.exe`). It opens in your browser at http://localhost:8000. Sample data loads on first start. Sign in as `admin` / `Meeting$1`.

## 2. Do these before real use
| Setting | Where | Why |
|---|---|---|
| Administrator password | *.env* `LOCAL_ADMIN_PASSWORD=...` | The sample password is public. In network mode a random one is created in `docs/data/admin-password.txt`. |
| Groq API key and model | Admin settings > Groq AI | Needed for minutes, action items, briefings and booking-link emails. |
| Groq transcription model | same group | Optional. Defaults to whisper-large-v3-turbo; transcribes recordings up to 25 MB. |
| Mock data off | Admin settings > Mock data | Hides sample data and CSV loading in production. |

## 3. Calendars and mail (per person, under Connections)
- **Gmail**: Google Calendar > Settings > your calendar > *Secret address in iCal format*, paste as a calendar link. For mail/invites use an *app password* (needs 2-step verification).
- **Yahoo / iCloud / Fastmail**: choose CalDAV and enter an *app password* from the provider's security page.
- **Outlook.com / Microsoft 365**: publish the calendar and paste the ICS link, or an administrator sets up Microsoft Graph (Admin settings > Microsoft Entra and Graph).
- **Classic Outlook on Windows** is read automatically after the person allows it. The *new* Outlook cannot be read by any program; use the calendar link or the Add-by-email helper for its accounts.
- Anyone can also drop `.ics` files into `docs/calendar` or upload one.

## 4. Zoom (optional)
Zoom Marketplace > Develop > Build App > **Server-to-Server OAuth**. Add scopes `meeting:read:admin`, `meeting:write:admin`, `cloud_recording:read:admin`, `user:read:admin`. Copy Account ID, Client ID and Secret into Admin settings > Zoom, then press Test on the Connections page.

## 5. Built-in video meetings
- Camera/microphone only work on `https://` or `localhost`. For other computers set in *.env*: `MI_LISTEN=lan` (https + reachable on the network). Browsers show a certificate warning once for the self-signed certificate; use a real certificate behind a reverse proxy for a clean experience.
- Open the app port (default 8000) in Windows Firewall for LAN use.
- Add a **TURN server** (Admin settings > Video meetings) for people on strict networks or mobile data.
- **Who can join** (set per meeting when scheduling, changeable by the host in the room under *Security*; the defaults are in Admin settings > Video meetings): anyone with the link, link plus passcode, or signed-in people only. A **waiting room** (host admits people) is on by default. People can also type a meeting ID or paste a link into the **Join** box on the home page or Meetings page.
- **Scheduling and sharing works like Zoom.** *Meetings > Schedule meeting* asks for Topic, Description, When, Duration, Security (tick boxes: require passcode, signed-in only, waiting room) and options (mute on entry, cameras off, record automatically). Afterwards the meeting page opens with the invite link, meeting ID, passcode and ready-to-paste invitation text. Click any meeting title in the list to open it again; Recurring meetings: under *Recurring meeting* choose daily, weekly or monthly and either *Ends after N meetings* or a *Last day* chosen on a calendar. In the Meetings list tick the box in front of a meeting, and **Modify** (opens a popup; one meeting at a time) and **Delete** (one or several) appear. Modify can email an updated invitation. Delete closes the room and, for a recurring series, can remove just that meeting or the whole series. Meetings that already have a transcript or minutes are kept as Cancelled. Transcripts, Minutes, Action items and Briefings are tabs inside Meetings.
- **Zoom-style extras:** the schedule form also has a time zone picker, recurring meetings (one link, up to 52 occurrences, ending after N meetings or on a last day), Personal Meeting ID (permanent link and passcode, shown on the home page) and host/participant video defaults. **Host** on the home page starts with video off or screen-share only. **Contacts** hold people and groups; **Chat** works with contacts who have signed in to iSift once (same email) and can start a video call that posts the link into the chat. **Docs** and **Whiteboard** are private notes and drawings that save automatically. Chat updates every few seconds (it does not push instantly).
- **Booking on other platforms:** the Platform list on the schedule form offers iSift, Zoom, Microsoft Teams and Google Meet. The app checks Admin settings first; if the platform has no account details a popup explains what is missing (close it with the X). Zoom uses a Server-to-Server OAuth app; Teams uses the Microsoft app registration (needs the *Calendars.ReadWrite* application permission with admin consent) and books on the calendar user's mailbox; Google Meet uses a service account with domain-wide delegation (Calendar API on) and a calendar user. These use API credentials, not a person's personal password. After booking, a window for the platform opens with the meeting link.
- **Outlook / Microsoft 365 sign-in popup:** *Connections > Outlook / Microsoft 365 > Sign in with Microsoft* opens Microsoft's own sign-in window and then pulls that person's calendar (next 30 days) and their 50 most recent email subjects, senders and previews. The password is typed only into Microsoft. The short-lived token is used once and not stored; only the email summaries are kept until the person presses *Remove email summaries*. One-time setup by an administrator: in Microsoft Entra ID > App registrations create (or reuse) an app, add a *Single-page application* redirect URI equal to this app's address (for example `http://localhost:8000`), add delegated permissions *User.Read, Calendars.Read, Mail.Read*, then paste its Application (client) ID in Admin settings > Meeting platforms > Microsoft sign-in popup. Reading the Outlook desktop app on a Windows laptop without signing in is separate (see *Outlook on this computer*).
- Room size defaults to 25 people (maximum 100). Video quality is best up to about 8 cameras because each browser connects to every other; larger meetings should keep most cameras off.
- Recording: the host's browser records, and may stay in the background but must not be closed (a warning appears).

## 6. Optional
Failure emails (SMTP), Power Automate token, retention periods, automatic calendar refresh interval, `DATABASE_URL` for PostgreSQL instead of the local SQLite file, and regular copies of `docs/data` (database and recordings) as a backup.

## Not included
Google and Microsoft "Sign in" buttons (OAuth) are not built; they need an app registered in your own Google/Microsoft account. The links/app-password methods above cover the same calendars.

## Troubleshooting
- **"No time zone found" / ZoneInfoNotFoundError on Windows:** Windows has no built-in time zone database. The app now falls back to the computer's own time zone, and `tzdata` is in the requirements so `app.cmd` installs it on the next start (it re-installs automatically when the requirements change). Times are then correct for your zone including daylight saving.

## Time zone
Each person's time zone is taken automatically from the device they open the app on (laptop or phone), so meeting times, "today" and scheduling follow them when they travel. The globe button at the top lets someone choose a different zone for themselves. The administrator's *Default time zone* (Admin settings > Run the app) is used for scheduled briefings and for devices that don't report a zone. The app does not use GPS: the place name shown comes from the time zone.
- **A recording shows "file missing" or won't download:** recordings are saved in `docs/data/audio/recordings` next to the app. If you moved, renamed or re-extracted the app folder, copy the old `docs/data` folder (database and recordings together) into the new folder. The app now finds recordings by name in that folder even if the folder's location changed.

Meetings imported from a calendar app can also be ticked. **Delete** removes them from iSift only (they stay in the calendar app and may return when you sync again); **Modify** offers *Create an editable iSift copy*.

### Calendar and Mail pages
The left menu has **Calendar** (month grid of all meetings, including those pulled from Outlook, ICS/CalDAV links and Zoom/Teams/Meet) and **Mail** (see below).

### Pulling Outlook email, calendar and contacts from this laptop
Three ways, all on the **Contacts** page (and two on **Email**):
1. **Sign in to Outlook** (popup) – works for any Outlook.com / Microsoft 365 account, on any computer. Needs the administrator setting *Microsoft sign-in client ID* (Admin settings → Microsoft); in the Entra app registration add the *Mobile and desktop / SPA* redirect for this app's address and the delegated permissions `User.Read`, `Calendars.Read`, `Mail.Read` and `Contacts.Read`. Pulls the next 30 days of calendar, the 50 latest emails and all contacts. Passwords and tokens are never stored.
2. **Read Outlook on this computer** – Windows with classic Outlook installed and signed in (not the new Outlook). iSift reads the same three things through Outlook itself; no sign-in or setup. (Not available on Mac/Linux or with new Outlook.)
3. **Import Outlook CSV** – in Outlook: File → Open & Export → Import/Export → Export to a file → Comma Separated Values → Contacts. Upload that file. Works for any Outlook, including PST-only profiles.
Pulling again never duplicates meetings or contacts.

### Mail (Outlook-style, several accounts)
**Mail** in the left menu looks and works like Outlook: a folder pane (Favorites, each account with its folders and unread counts, Add account), a message list with search, and a reading pane. Toolbar: New mail, Delete, Archive, Junk, Move to, Mark read/unread, Flag, Reply, Reply all, Forward, Sync. View tab: reading pane on/off.
- **Add account**: Gmail, Yahoo, iCloud, Outlook.com or any IMAP/SMTP server, using an **app password** (never your main password). Up to 10 accounts. Passwords are stored encrypted. Mail is read live from the provider and is not stored in iSift.
- **Microsoft 365 / work accounts** do not allow app passwords. Use *Sign in with Microsoft (popup)* or *Read Outlook on this computer* in the Add account window: you get a read-only inbox of the latest 50 messages, and the calendar and contacts are pulled too.
- Delete moves a message to Deleted Items (deleting there is permanent). Archive and Junk use the account's own folders (they are created if missing).
- Attachments are listed but not downloaded; mail is shown as plain text.

### Adding mailboxes with a sign-in window (Google, Microsoft, Yahoo)
**For users:** open Commbox > Mail > Add account, type your email address and press **Continue**. A sign-in window from Google, Microsoft or Yahoo opens; sign in and approve. No password is typed into iSift and nothing in Admin settings is involved. iSift keeps only an encrypted refresh token (OAuth, XOAUTH2).

**For whoever installs iSift (once):** Outlook works out of the box because Microsoft registered Outlook with every provider. iSift is your own app, so it has to be registered once per provider (about 10 minutes each). Put the IDs in the `.env` file in the iSift folder (see `.env.example`), then restart. Users never see them.
The **redirect address** to register everywhere is your app's address + `/api/v1/oauth/callback`, for example `http://localhost:5173/api/v1/oauth/callback` (exactly what people type in the browser).
- **Google** (mail, calendar, contacts), variables `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET`: console.cloud.google.com > new project > enable *Gmail API*, *Google Calendar API*, *People API* > OAuth consent screen (External, add your people as *Test users*) > Credentials > *OAuth client ID* > Web application > add the redirect address.
- **Microsoft** (mail, calendar, contacts), variables `MS_OAUTH_CLIENT_ID` / `MS_OAUTH_CLIENT_SECRET` (and `MS_OAUTH_TENANT`, see below): Entra ID > App registrations > New (any organizational directory and personal accounts) > Web redirect address > API permissions (delegated): *Office 365 Exchange Online* `IMAP.AccessAsUser.All`, `SMTP.Send`; *Microsoft Graph* `Calendars.Read`, `Contacts.Read`, `User.Read`, `offline_access` > Certificates and secrets > new client secret. Some tenants need an administrator to grant consent or switch IMAP/SMTP sign-in on.
  **Which account types?** Either register the app for *Accounts in any organizational directory and personal Microsoft accounts* and leave `MS_OAUTH_TENANT` empty, or register it for *this organizational directory only* (single tenant) and set `MS_OAUTH_TENANT` to the Directory (tenant) ID. A single-tenant app with the default setting fails with a message like *"Selected user account does not exist in tenant 'Microsoft Services'"*; that means the sign-in used a personal Microsoft account (or the wrong endpoint). In that case use the tenant ID and choose *Work or school account* in the window.
- **Yahoo** (mail only), variables `YAHOO_OAUTH_CLIENT_ID` / `YAHOO_OAUTH_CLIENT_SECRET`: developer.yahoo.com > My Apps > Create an App > Mail read/write and the redirect address (Yahoo may insist on https and may need to approve the app).
Until a provider is registered, people who pick it are offered an app password instead (also the route for iCloud and other providers). Each person can remove iSift later from their Google, Microsoft or Yahoo list of connected apps.

### Scheduling: booking pages like Calendly and Cal.com
The **Scheduling** tab (next to Meetings, Transcripts, Minutes, Action items and Briefings) lets you publish a link such as `http://your-app/#/book/intro-call`. Nothing needs to be configured for it to work.
- **Who sends the confirmation:** the app email account in *Admin settings > Email sent by the app* (SMTP host, user, password and From address). Guest replies go to the person who owns the booking page. If that is not filled in, the first working mailbox in Commbox is used.
- **Pre-filled email:** each person you email gets their own copy of the link with their address in it (`#/book/page?email=name@example.com`), so the Email box on the booking form is already filled in and they only type their name. A link copied with *Copy link* is generic.
- **Share a link:** press *Share* (at the top, or on a booking page). The email is written for you by the Groq AI model: it opens with a subject and message that already contain the booking link. Type the recipients, optionally say what the meeting is about and press *Write again*, change anything you like and press *Send email*. It is sent from the app email account (Admin settings, Email sent by the app), and replies go to you. Add the Groq key in Admin settings under *AI for sharing booking links* (or `GROQ_API_KEY` in `.env`); without it a standard message is used. *Use my email app* opens your own mail program instead.
- **Create a page:** *Meetings > Scheduling > New booking page*. Choose the title, length (15 to 120 minutes), gap between meetings, minimum notice, how many days ahead people can book, your time zone, and the weekly hours (several time ranges per day are allowed).
- **Free times** are your weekly hours minus everything already in your iSift calendar, including meetings pulled in from Outlook, Google and other calendars, minus the gap you chose. All-day events do not block a day. Two people can never get the same time.
- **Guests need no account.** They pick a day and time (shown in their own time zone, which they can change), enter name and email, and get a video link. Each booking creates a built-in video room and a meeting in your *Meetings* list.
- **Cancel or reschedule:** the guest keeps a private link (`#/booking/...`) to move or cancel; you can cancel from the *Bookings* list. The same video link keeps working after a reschedule.
- **Emails:** confirmations, reschedules and cancellations, each with a calendar file, are sent from the mailbox you connected under *Connections* (the single mailbox form). If none is connected the booking still works and the guest sees the links on screen; you see the booking in iSift.
- **Sharing:** the link works anywhere iSift can be reached, so for outside guests iSift must be reachable from the internet (a server or a tunnel), not only `localhost`. Pause or delete a page to stop new bookings; existing meetings stay.
- Cal.com video links (`app.cal.com/video/...`) in imported meetings are recognised and get a Join button.

### Commbox: Mail, Calendar and Contacts in one place
**Commbox** in the left menu has three tabs, built like Outlook:
- **Mail** – folders per account, plus **All inboxes**, one combined list of every account's inbox (newest first, each row tagged with its account). Click an account's Inbox for a separate box.
- **Calendar** – a month picker and a list of calendars (**All calendars** combined, plus one per account, each with its own colour). Tick or untick calendars to combine them as you like, or click a calendar's name to see only that one. Views: Day, Work week, Week, Month. Events from Google, Microsoft, Outlook on this computer and your calendar links are tagged with the account they came from.
- **Contacts** – **All contacts (merged view)** shows each person once (same email), with tags for the accounts they are in; click an account for its own list; **iSift contacts** is your own list. **Merge all into iSift list** copies everyone into the iSift list once so chat, meetings and invitations can use them.
Upgrade note: this release adds an `account` column to meetings and contacts (migration `0008_accounts`, run automatically by `app.cmd` / `start-local.ps1`). Meetings and contacts that were pulled before the upgrade show under "iSift and other calendars" / "iSift contacts" until you press Sync / pull again.

### If the Share window says the email could not be sent, or Groq was not accepted
- **Gmail as the app email account:** the SMTP password in *Admin settings > Email sent by the app* must be a 16-letter **app password** (Google Account > Security > 2-Step Verification > App passwords), not the normal Gmail password. The sign-in is refused otherwise. The From address (for example `info@isift.au`) only shows to recipients if it is added in Gmail under *Settings > Accounts > Send mail as*.
- **Groq says the key was not accepted:** (the *Connection tests* button in Admin settings now checks the saved Groq key and the model name)  create a new key at console.groq.com (API Keys), paste it in *Admin settings > AI for sharing booking links* with no spaces or quotes, save, and press *Write again*. The window shows Groq's own message. Sharing still works without Groq, using a standard message.

### Who gets the host's copy of a booking notice
The built-in local administrator has the placeholder address `admin@example.test`, which no mail server accepts. iSift therefore sends the host copy (and sets Reply-To) to the first real address it finds: *Admin settings > Send failures to*, then the app email login, then the From address. If none is real, only the guest is emailed. A bounce from `example.test` no longer happens.


## Choosing which parts of the app are on (Modules)

Admin settings has a **Modules** tab. Each module is a row with a tick box: Meetings, Transcripts, Minutes, Action items, Briefings, Scheduling, Commbox (Mail, Calendar, Contacts), Chat, Docs, Whiteboard, Connections and Load mock data (the Dashboard button and the Data import page). A module that is not ticked is hidden for everyone: it disappears from the left menu, the dashboard tiles, the Meetings and Commbox tabs, and from the capabilities and How it works sections of the home page (the home page list is public, so it works before sign-in). Press *Save modules* to apply; no restart is needed. This hides the parts from people; it does not delete any data, and ticking the box again brings everything back.

## Repeating on chosen days, host controls and the Join window

- **Repeat on chosen days:** in *Schedule a meeting* choose *Weekly*, tick the days (Mon … Sun, or press *Week days*) and enter *For the next N weeks* (or a last day). Every chosen day in those weeks becomes a meeting that shares one link. Example: Monday, Thursday and Friday for 10 weeks.
- **Host controls (in the meeting):** the meeting name and host are at the top; the host is always listed first. *People* opens the participants list on the right (press it again to hide it). The host can mute someone or ask them to unmute, stop their video or ask them to start it, remove them, make them *co-host* (all host powers except ending the meeting, recording and security) or hand over the *host* role (to a signed-in person). *Mute all* mutes everyone at once.
- **Who may unmute or start video:** the two tick boxes at the bottom of the participants list (and the same two options in *Schedule a meeting*) decide whether participants can unmute themselves and start their own video. With *unmute* off, participants join muted and cannot unmute; with *video* off they cannot start video; you can allow one and not the other. These rules are applied by the iSift meeting screen: someone who joins through a modified client could still send audio.
- **Join window:** *Join* on the Dashboard (and *Join with an ID* on Meetings) opens a Zoom-style window: the meeting ID box has a drop-down of your past meetings (rooms you hosted plus ones you joined on this computer), your name, *Don’t connect to audio* and *Turn off my video*.

## My account, company, pricing and invitation alerts

- **My account** (press your name or initial at the bottom left; it is no longer in the menu): *Profile* (name, phone, job title, department, language, about me), *Time and location* (time zone, city, country, working days and hours), *Password* (needs the current password; for the built-in administrator it replaces `LOCAL_ADMIN_PASSWORD` from then on) and *Company*.
- **Company account:** any person can create one and becomes its owner. Owners and administrators add people (name, email, role and, for a new person, a starting password that is shown once; leave it empty to have one made), change roles and remove people. Only the owner changes the plan or deletes the company. A person can belong to one company. People who sign in with Microsoft are recorded by email and show as *Invited* until their first sign-in.
- **Plans and pricing:** *Pricing* on the home page (and *Compare plans* inside the app). Three plans: **Basic** (free), **Individual** (highlighted, "Most popular") and **Business**. Prices are in Australian dollars (A$), set at Zoom's list prices less 20%: Individual A$13.59 a month or A$11.33 a month billed yearly (A$135.96); Business A$17.59 a month or A$14.66 a month billed yearly (A$175.92). They live in `PLANS` in `backend/app/services/billing.py` and `PLAN_PRICES` in `frontend/src/Pricing.tsx`; change both together. Older accounts saved as Free/Popular/Enterprise are read as Basic/Individual/Business.
- **Current plan and Upgrade:** the top right of the Dashboard shows the current plan and an *Upgrade* button (*Manage plan* on Business). It opens **Plan and billing**: pick a plan and Monthly/Yearly, enter the card in Square's secure form and press *Pay and upgrade*. A company account pays as one (one plan, one card); only the owner or an administrator can change it.
- **Square setup (Admin settings > Payments):** enter *Square environment* (sandbox while testing), *Application ID*, *Access token* (stored encrypted, never sent to browsers), *Location ID* and *Billing currency* (must equal the Square location's currency), save, then run **Connection test** on the Run the app tab: it asks Square for the location and reports the name or the problem. In sandbox use Square's test card 4111 1111 1111 1111. No real money moves until you switch to production keys.
- **How billing works (same design as AccFino):** iSift keeps only Square's customer and card ids plus the last 4 digits. A charge record with a unique idempotency key is written before Square is called, so a restart cannot charge twice. Renewals run hourly in the worker (`POST /api/v1/admin/billing/run` runs them now). A declined card is retried on day 3 and day 6; the plan keeps working for a 7-day grace period, then falls back to Basic. Choosing Basic stops renewal and keeps the paid plan to the end of the period. Switching plans charges the new plan immediately (no proration); if the payment fails the old plan stays.
- **Invite in a meeting:** *Invite* opens a box for email addresses (with your company people and contacts to pick from) and an optional message. People with an iSift account get an alert (the bell at the top and a pop-up with *Join now*, within about 10 seconds); everyone gets the link by email when an email account is set up under Admin settings, *Email sent by the app*. Only the host and signed-in people in the meeting can invite.
- **Chat in a meeting:** under the message box, *To:* lists Everyone and each person; choose a person for a private chat. *People* also has a *Chat* button on each name.

## Sign-up with a verified email

Sign-up asks for first name, last name, email, password (twice), country or region, phone number (the country code, such as +61, is filled from the country and checked against the number) and agreement to the terms. All are required. Pressing *Continue* emails a 6-digit code (valid 15 minutes, 5 tries, a new code at most every 30 seconds). **The account is created only when the right code is entered**, so an unverified email can never log in. People added by an administrator or a company owner are not affected.

The code is sent from the app's own email account: Admin settings > Email and calendar > *Email sent by the app* (SMTP host, user, password, From). If that is not set up, nobody can receive the code; in this local demo it is then written to the server log line `Sign-up code for <email> is 123456` so you can still test. Set up the email account before inviting real people.

## Where your accounts and data are kept (updates do not remove them)

Accounts, sign-in details, meetings, contacts, settings and recordings are stored in one data folder **outside the app folder**: `%LOCALAPPDATA%\iSift\data` on Windows (`~/.isift/data` elsewhere), or the folder named by the `ISIFT_DATA_DIR` environment variable. Unzipping a new version, or deleting the old app folder, no longer affects them. The first time a new version starts it copies any database it finds in its own `docs/data` or in a neighbouring iSift folder into the data folder (it never deletes the old one), and each start keeps the five latest copies `isift.db.bak-<date>`. Start-up prints `Your data folder: ...`. If data was lost before this version because the old folder had already been deleted, it cannot be recovered; accounts have to be created again once. Back up by copying the data folder.

### If the verification email does not arrive

1. Open **Admin settings > Email and calendar** and fill in **Email sent by the app**: SMTP host, port, user, password and From address. Gmail: `smtp.gmail.com`, port 587, your full address and a 16-letter *app password* (a normal Gmail password is refused). Save.
2. Type your own address under **Send a test email** and press the button. It reports success or exactly what the mail server answered (for example "authentication refused" or "relay denied").
3. Check the spam folder. Until the account is set up, the sign-up screen says the code could not be emailed and the code is written to the server log (`docs/logs`).

## Everything configured is stored in the database

- **Database:** if `.env` has a PostgreSQL `DATABASE_URL` (for example Neon: `postgresql://user:pass@host/db?sslmode=require`), `app.cmd` now uses it instead of the local SQLite file. The Neon form is converted automatically. Your accounts, meetings and Admin settings are then stored there, whatever happens to the app folder. Without a PostgreSQL address the local data folder is used (see above).
- **Admin settings:** everything saved in Admin settings (email account, Groq/Azure keys, Square, Zoom, Google/Microsoft/Yahoo sign-in, defaults...) is a row in the database, secrets encrypted. On the first start of this version, values found in `.env` are **copied into the database once** (look for "Copied N settings from the environment" in `docs/logs`). After that the database value is used; edit it in Admin settings. Keep `LOCAL_AUTH_SECRET` (or `SETTINGS_ENCRYPTION_KEY`) the same from then on: saved secrets are encrypted with it, and if it changes they cannot be read and must be typed in again.
- `.env` still needs `DATABASE_URL` (the app must know where the database is before it can read anything from it) and `LOCAL_AUTH_SECRET`. Do not share a `.env` that contains real passwords.

The verification email is sent in the background: the sign-up screen moves to the code box after at most 4 seconds, says "Sending the code…" if the mail server is slow, and updates itself to "We sent a 6-digit code" or shows the mail server's error (then press *Send a new code*).

### Repeat options when scheduling

The *Repeat* drop-down offers: Does not repeat, Daily, Every weekday (Monday to Friday), Weekends (Saturday and Sunday), Weekly, Weekly on chosen days and Monthly. The weekday options show Monday to Sunday tick boxes that you can adjust (they switch to "chosen days"). End with: a number of weeks or meetings (up to 52 weeks or 365 meetings), a last day, or **No end date**, which creates a year of meetings (52 weeks; 365 days when daily; 24 months when monthly). Repeats are for iSift video meetings and your own link; Zoom, Teams and Google Meet bookings are single meetings.

## Using iSift scheduling inside other applications (embed, Outlook, access keys)

Open **My account > Add-ins and embedding**.

**1. Embed a booking page on any website (like Calendly).** Choose a booking page and a style (inline or pop-up). Copy the two lines of code into your site. Optional attributes on the element: `data-name`, `data-email` (pre-fill the visitor), `data-height` (fixed height). The page tells the host when someone books: `window.addEventListener('isift:booked', e => console.log(e.detail))`. From your own script you can also call `iSift.open({slug:'my-page', name:'Pat'})`. The address `/embed/` is the only part of iSift that other websites may frame; the rest of the app refuses to be framed. If you use your own reverse proxy, keep the `/embed/` location from `frontend/nginx.conf`.

**2. Outlook add-in.** Create an access key (name it "Outlook"), download the add-in file from the same tab, then in Outlook choose Get Add-ins > My add-ins > Custom add-ins > Add from file. Your Microsoft 365 administrator can deploy the same file to everyone (Microsoft 365 admin centre > Settings > Integrated apps > Upload custom apps). In a new email or meeting click **iSift meeting**, paste the key once, then use **Add an iSift video meeting** or **Insert link** next to a booking page. Outlook requires iSift to be served over **https://** with a valid certificate (put it behind your normal HTTPS front door); http://localhost will not load.

**3. Access keys.** A key (`isift_pat_...`) is shown once and stored only as a hash. It can list your booking pages and bookings, list and create meetings and rooms, and read your plan. It cannot read mail, change your account or password, or touch billing or admin. Remove a key and it stops working immediately. Use the same key for scripts, Zapier or Power Automate (send it as `Authorization: Bearer <key>`).

Not yet included: Microsoft Teams, Google Workspace and Slack add-ons. They would reuse the same keys and embed page.

## Where meeting recordings are kept (Cloudflare R2)

Open **Admin settings > Recording storage (Cloudflare R2)** and fill in four things, then press **Connection test** on Run the app (it writes and removes a small test file):

1. In Cloudflare, R2 > Create bucket (leave it private).
2. R2 > Manage API tokens > Create API token, permission **Object Read & Write**, limited to that bucket.
3. Endpoint address: the S3 API address on the bucket's Settings page, `https://<account id>.r2.cloudflarestorage.com` (no bucket name on the end).
4. Paste the Access key ID and Secret access key (the secret is stored encrypted).

New recordings are then uploaded to `isift-video/<account>/<id>.mp4` (one folder per account inside the top folder `isift-video`; the account folder is the email name plus a short permanent id) in the bucket (compressed to MP4 when ffmpeg is installed on the server, otherwise kept as WebM). Download and Delete on the Recordings page work as before; Delete also removes the object. If the bucket cannot be reached, the host is told and nothing is lost silently.

Without R2 set up, recordings up to 150 MB are stored in the database itself (so they survive updates and work with Neon), and larger ones in the data folder. Recordings made earlier stay where they are and keep working. Moving old recordings into R2 is not automatic.

### Local copy by default, cloud copy by choice (and the Basic plan limit)

Every recording is saved to the host's **own computer** first (the browser downloads the file when recording stops). The server keeps only the speech audio, for the transcript.

Next to the Record button there is a box, **Also store in cloud**, unticked by default. Tick it before stopping and the recording is also uploaded to R2 (or the database if R2 is not set up). On the **Basic** plan a cloud copy is removed automatically after **2 days** (the Recordings page shows when); Individual and Business copies are kept until deleted. The clean-up runs hourly in the background and whenever the Recordings list is opened.

## Changing plan mid-term: credit, difference and refunds (manual approval)

On **Plan and billing**, choosing another paid plan (or switching monthly/yearly) shows a quote first:

- The **unused days** of the term already paid are credited (amount paid x days left / days in the term).
- If the new plan costs **more** than the credit, only the **difference** is charged to the card on file, at once, and the new term starts today. If the card is declined nothing changes.
- If the credit is **bigger** than the new price (a downgrade), the plan switches at once, nothing is charged, and the leftover becomes a **refund request**.
- **Move to Basic** still keeps the plan until the paid period ends. Ticking "End my plan today and ask for a refund" ends it now and files a refund request for the unused time.

**No refund is ever sent automatically.** Requests wait under **Admin settings > Payments > Refund requests**. An administrator can **Approve and refund** (optionally a smaller amount, with a note) or **Decline**. Approving sends the money back through Square to the card that paid, capped at what was actually paid; the customer is notified either way and sees the status under Plan and billing. If Square rejects a refund, the request stays open and the reason is shown.
