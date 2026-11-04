# Podcast Studio

## What it is
HD podcast recording in iSift, under Meetings > Podcast Studio. It is a separate capability from meeting recording.

## What it records
Audio is 48 kHz stereo, Opus at 256 kbps or lossless 24-bit WAV. Voice processing (echo cancel, noise suppression, auto gain) is off so the sound is untouched; an optional clean voice toggle turns it on. Video is the best the camera gives, up to 3840x2160 at 30 fps (VP9, falling back to VP8), or 1080p, 720p or audio only. A mixed master is recorded plus one separate track per selected microphone, so each voice can be edited on its own.

## Where files are saved
On Basic, files are always saved on the person's own computer. Nothing is sent to iSift and the server refuses cloud uploads. On Standard and Business the person chooses, for each recording, to save on their computer or in the cloud. Cloud files keep their original quality (no re-encoding) and count toward the storage allowance. The administrator can switch Podcast Studio or cloud podcasts on or off for any one person in the Admin Console, and can edit plan defaults in the plan matrix.

## Limits
Podcast Studio records the microphones and camera on the host's own computer. Remote guests in a meeting are not recorded as separate tracks. Up to 8 tracks and 2 GB per file. Quality depends on the microphone, camera and browser.

## Code
Backend: `backend/app/api/routes_podcast.py`, model `PodcastRecording`, migration `0016_podcast_recordings.py`, limits `podcast` and `cloud_podcast` in `services/entitlements.py`, module `podcast` in `routes_modules.py`. Frontend: `frontend/src/podcast.ts`, `PodcastStudio.tsx`, plus Landing, Pricing and Admin. Tests: `backend/tests/test_podcast.py`.
