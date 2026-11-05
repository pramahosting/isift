# Podcast Studio

## What it is
HD podcast recording in iSift, under Meetings > Podcast Studio. It is a separate capability from meeting recording.

## What it records
Audio is 48 kHz stereo, Opus at 256 kbps or lossless 24-bit WAV. Voice processing (echo cancel, noise suppression, auto gain) is off so the sound is untouched; an optional clean voice toggle turns it on. Video is the best the camera gives, up to 3840x2160 at 30 fps (VP9, falling back to VP8), or 1080p, 720p or audio only. A mixed master is recorded plus one separate track per selected microphone, so each voice can be edited on its own.

## Where files are saved
On Basic, files are always saved on the person's own computer. Nothing is sent to iSift and the server refuses cloud uploads. On Standard and Business the person chooses, for each recording, to save on their computer or in the cloud. Cloud files keep their original quality (no re-encoding) and count toward the storage allowance. The administrator can switch Podcast Studio or cloud podcasts on or off for any one person in the Admin Console, and can edit plan defaults in the plan matrix.

## Studio sessions: interviews with guests
Press Start a studio session in Podcast Studio. It opens a meeting room; guests join from the link (no account needed) and everyone is told the session is being recorded. The host chooses Studio recording in the room menu. The recording is a 1920x1080 HD picture of everyone (or of whatever is shared, with the faces beside it), a mixed master at Opus 256 kbps and 48 kHz, and a separate Opus 256 kbps track for each person. A guest who joins late gets a track labelled with when they arrived. When the host stops, the same Local or Cloud choice as above is offered (Basic: always on the host's computer).

What can be shown while recording: a screen, window or browser tab (with its sound), a PDF (export slides or a document to PDF and use Share a file), a photo, a video file (MP4 or WebM), and the Whiteboard. Everything that is shared is in the recording.

## Studio background
The host can use their own studio picture. In the solo recorder, Studio background in the setup form can blur the room, use a built-in picture or upload your own: the person is cut out and placed in front of it (recording is then limited to 1080p). In a studio session use Background in the room menu; the chosen picture also fills the backdrop of the recording.

## Finding it, and remembered setup

Podcast Studio is a tab under Meetings, next to Booking and Webinars. Recordings, Transcripts, Minutes, Action items and Briefings sit in a second row under Meetings. Podcast Studio has five tabs: **Record on this computer** (title, preview and the Record button), **Interview guests online** (starts a studio session with a link), **Edit videos** (cut, join, insert, smooth, voice-over, background), **Podcast settings** and **My cloud podcasts** (recordings kept in the cloud, each with Edit and Post to YouTube buttons). Podcast settings has two tabs of its own: **Podcast equipment** (microphones, camera, studio background, video quality and audio format) and **YouTube** (the Google app details and sign-in used to post). Your settings are remembered on this browser and reused next time until you change them; a Reset link clears them. A recording keeps running if you switch tabs, and a red dot shows on the Record tab.

## Posting to YouTube with one click

Set it up once in **Podcast settings > YouTube**. YouTube never accepts a password, so the person gives iSift the **Client ID** and **Client secret** of their own Google Cloud app (an administrator can instead set `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET` once for everybody), presses **Connect YouTube** and approves access in the Google window. iSift keeps only an encrypted refresh token. The page shows the exact redirect address to add to the Google app (`<your address>/api/v1/podcasts/youtube/callback`) and the steps to create the app.

After that, **Post to YouTube** is one button: after saving a recording to the cloud, on every podcast in My cloud podcasts, and on a finished edit. A small box is pre-filled with the title; the person adds a description and tags, chooses Private, Unlisted or Public (the default is chosen in settings) and presses Post now. Large files go up in pieces and resume after a dropped connection. A sound-only podcast gets a moving sound-wave picture, because YouTube needs a picture. Disconnecting also asks Google to forget the permission.

Posting works from podcasts kept in the cloud, because the server uploads the file. Google keeps videos uploaded through an app that has not passed Google's verification private, so a new app can post at once but public posting needs Google to verify the app (a one-off review the app owner requests).

## Editing videos

The **Edit videos** tab works on cloud podcasts. The original is never changed: an edit is rendered on the server with ffmpeg and saved as a new MP4 podcast next to it (and can then be posted to YouTube). Everything is a change to a timeline of pieces, where each piece is a stretch of one video:

- **Cut and trim**: set a piece's From and To, or use Start here / End here at the playhead.
- **Cut out a section**: enter the seconds to remove; the rest closes up. Split at playhead and Delete piece do the same by hand.
- **Join videos**: Add to end puts another podcast or a clip from this computer after the timeline. Pieces can be moved, duplicated and deleted.
- **Insert a clip inside a video**: move the playhead, then Insert at playhead on a clip. The video is split there and the clip goes between the halves. A 10 second video with a 2 second clip inserted at the 4th second becomes 4 + 2 + 6 = 12 seconds.
- **Smooth**: a short blend (picture and sound) at every join, plus a fade in and out. Polish reduces hiss and evens out the loudness.
- **Voice-over**: record the microphone while the video plays (wear headphones), or add a sound file. It is placed at that moment of the finished video; set its time and volume, and lower or mute the original sound.
- **Background**: a plain backdrop (green screen works best) is removed and replaced by a colour or a picture, on the server. For any room without a green screen, **Any room, no green screen** cuts the person out in the browser (the same tool as the live studio background) while the clip plays through once, so it takes as long as the clip and the page must stay open.
- **Save as a new video** can limit the picture size (1080p, 720p, 480p). Clips added from the computer and voice-overs are working files that are deleted after a day.

The video editor and YouTube posting are **paid-plan features** (Standard and Business). They are two switches, `podcast_edit` and `youtube_post`, off on Basic and on for paid plans. An administrator can change them for any plan (Admin Console > Plans) or for one person (Admin > Users > Limits), and they show in the landing page comparison, the price list and the Compare plans table. Both also need cloud podcast storage, because the server does the work. A Basic person can be given both by an administrator.

## Editing the files outside iSift

Browsers write WebM files without a length in the header, so some editors cannot seek in them. If yours cannot, copy the file once without re-encoding: `ffmpeg -i master.webm -c copy master-fixed.webm`. Nothing is lost. The WAV tracks have no such issue.

## Limits
A guest's picture and sound are as good as their connection and equipment allow, and their separate track is recorded on the host's computer from what reaches it. The solo recorder (not a session) records only the devices on the host's own computer. Up to 8 tracks and 2 GB per file. Quality depends on the microphone, camera and browser.

## Code
Backend: `backend/app/api/routes_podcast.py`, model `PodcastRecording`, migration `0016_podcast_recordings.py`, limits `podcast`, `cloud_podcast`, `podcast_edit` and `youtube_post` in `services/entitlements.py`, module `podcast` in `routes_modules.py`. Editing: `routes_podcast_edit.py`, `services/videoedit.py` (the ffmpeg timeline renderer), `services/podwork.py` (working files, signed preview addresses, job records). YouTube: `routes_youtube.py`, `services/youtube.py`. YouTube connections and job progress are kept in `integration_settings` (no new table or migration). Frontend: `frontend/src/podcast.ts`, `PodcastStudio.tsx`, `PodcastEditor.tsx`, `PodcastYouTube.tsx`, `PodcastSave.tsx`, plus Landing, Pricing and Admin. Tests: `backend/tests/test_podcast.py`, `backend/tests/test_podcast_edit.py` (real ffmpeg; Google is replaced by a fake). Video editing needs `ffmpeg` and `ffprobe` on the server.
