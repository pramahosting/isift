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

## Limits
A guest's picture and sound are as good as their connection and equipment allow, and their separate track is recorded on the host's computer from what reaches it. The solo recorder (not a session) records only the devices on the host's own computer. Up to 8 tracks and 2 GB per file. Quality depends on the microphone, camera and browser.

## Code
Backend: `backend/app/api/routes_podcast.py`, model `PodcastRecording`, migration `0016_podcast_recordings.py`, limits `podcast` and `cloud_podcast` in `services/entitlements.py`, module `podcast` in `routes_modules.py`. Frontend: `frontend/src/podcast.ts`, `PodcastStudio.tsx`, plus Landing, Pricing and Admin. Tests: `backend/tests/test_podcast.py`.
