# Meetly

Meetly is a FastAPI meeting-intelligence service. It accepts audio from a
provider, sends it through live transcription and speaker diarization, and
exposes the assembled transcript plus optional summaries and Q&A.

## What is included

- Provider-based meeting lifecycle: `local` and `google_meet`
- Live transcription with `faster-whisper`
- Speaker diarization and transcript assembly
- Optional OpenRouter summaries and transcript Q&A
- FastAPI REST API with OpenAPI docs
- TypeScript SDK with a resource API for meetings

The processing path is:

```text
provider audio
  -> AudioSource
  -> RecorderBackend
  -> Meeting
  -> Transcriber / Diarizer
  -> TranscriptAssembler
```

## Requirements

- Python 3.10+
- Node.js 18+ and npm for the TypeScript SDK
- PortAudio for microphone capture when using a local microphone source

## Run the API

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

uvicorn api.main:app --host 0.0.0.0 --port 8000
```

The API is available at `http://localhost:8000`.

- Health: `GET /health/`
- OpenAPI UI: `http://localhost:8000/docs`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

Copy `.env.example` to `.env` and set only the values required by the
providers and AI operations you use. Never commit `.env` or credentials.

## Google Meet

Meetly uses the Google Meet Media API audio path:

```text
Google Meet
  -> enrolled Google Meet Media transport
  -> GoogleMeetAudioSource
  -> RecorderBackend
  -> Meeting
  -> transcription and diarization
```

Create a Google Meet-backed meeting with:

```bash
curl -X POST http://localhost:8000/meetings \
  -H 'Content-Type: application/json' \
  -d '{
    "provider": "google_meet",
    "meeting_url": "https://meet.google.com/abc-defg-hij"
  }'
```

Then start it with:

```bash
curl -X POST http://localhost:8000/meetings/<meeting_id>/start
```

Required environment variables:

```text
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REFRESH_TOKEN=
```

The refresh token must be authorized for the required Google Meet scopes,
including the restricted live-media audio scope. Google Meet live media is a
Developer Preview capability and requires the Google Cloud project and OAuth
principal to be enrolled.

The REST API alone does not provide live audio. Meetly therefore keeps the
official Google Media API reference-client transport as an explicit
`MediaTransport` boundary. The transport must be supplied by the enrolled
Google Media integration; Meetly does not use browser automation, fake frames,
or undocumented signaling.

## REST API

### Create a meeting

`POST /meetings`

Local provider:

```json
{}
```

Google Meet provider:

```json
{
  "provider": "google_meet",
  "meeting_url": "https://meet.google.com/abc-defg-hij"
}
```

The response contains `meeting_id`, `state`, and `provider`.

### Meeting lifecycle

```text
GET  /meetings/{meeting_id}
POST /meetings/{meeting_id}/start
POST /meetings/{meeting_id}/stop
```

### Transcript and AI operations

```text
GET  /meetings/{meeting_id}/transcript
GET  /meetings/{meeting_id}/summary
POST /meetings/{meeting_id}/ask
```

Ask request:

```json
{
  "question": "What decisions were made?"
}
```

Meeting states are `idle`, `running`, `stopping`, `stopped`, and `error`.

## TypeScript SDK

Build the SDK:

```bash
cd sdk/typescript
npm install
npm run build
```

Use the provider-based resource API:

```ts
import { MeetlyClient } from "@meetly/sdk";

const meetly = new MeetlyClient({
  baseUrl: "http://localhost:8000",
});

const meeting = await meetly.meetings.create({
  provider: "google_meet",
  meetingUrl: "https://meet.google.com/abc-defg-hij",
});

await meeting.start();
const transcript = await meeting.getTranscript();
console.log(transcript);
```

The resource also provides:

```ts
await meeting.getStatus();
await meeting.stop();
await meeting.getTranscriptResponse();
```

An API key can be supplied to the client:

```ts
const meetly = new MeetlyClient({
  baseUrl: "https://api.example.com",
  apiKey: process.env.MEETLY_API_KEY,
});
```

The SDK sends the key as a Bearer token.

## Development checks

Python tests:

```bash
pytest
```

TypeScript checks:

```bash
cd sdk/typescript
npm run typecheck
npm test
```

## Security

- Keep OAuth credentials, API keys, and refresh tokens in environment
  variables or a secrets manager.
- Do not commit `.env` files or credential files.
- Use HTTPS and server-side secret storage in production.

## License

See `LICENSE`.