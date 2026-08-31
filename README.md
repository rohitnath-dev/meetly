# Meetly

Meetly is a meeting intelligence backend that captures meeting audio, transcribes speech, identifies individual speakers, assembles transcripts, and generates AI-powered summaries and insights. The project exposes a FastAPI-based HTTP API and includes a TypeScript SDK for integrating with the API from JavaScript and TypeScript applications.

## Overview

Meetly separates concerns cleanly across the codebase. The API layer handles HTTP requests and responses. The core layer manages meeting lifecycle and orchestration. The audio layer handles recording, transcription, and diarization. The LLM layer handles summarization and question answering. This separation keeps the system maintainable and allows each layer to evolve independently.

## Features

- Meeting lifecycle management, including creation, start, and stop operations
- Live transcription pipeline
- Speaker diarization
- Transcript assembly
- AI-powered meeting summarization
- Question answering over meeting content
- Zoom integration layer
- FastAPI REST API with interactive OpenAPI documentation
- TypeScript SDK with typed API responses
- API key authentication support in the SDK
- Centralized HTTP error handling in the SDK

## Project Structure

```
meetly/
├── api/                    FastAPI HTTP API
│   ├── main.py
│   ├── health.py
│   ├── meetings.py
│   ├── meeting_factory.py
│   ├── meeting_manager.py
│   └── schemas/
│       └── meeting.py
│
├── audio/                  Audio processing
│   ├── integrations/
│   │   └── zoom.py
│   ├── processing/
│   │   ├── ai/
│   │   ├── diarization/
│   │   ├── live_transcription/
│   │   └── transcript/
│   └── recorder/
│
├── core/
│   └── meeting.py          Meeting orchestration
│
├── llm/
│   ├── client.py
│   └── prompts.py
│
├── sdk/
│   └── typescript/         TypeScript SDK
│       ├── src/
│       ├── tests/
│       ├── package.json
│       └── tsconfig.json
│
├── tests/
│   └── api/
│
├── config.py
├── pyproject.toml
├── requirements.txt
├── LICENSE
└── README.md
```

## Requirements

- Python 3.10 or later
- Node.js 18 or later, for the TypeScript SDK
- npm

## Getting Started

Clone the repository:

```bash
git clone <YOUR_REPOSITORY_URL>
cd meetly
```

### Python Environment

Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate      # On Windows: .venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

### Environment Variables

Create a `.env` file and configure the required settings before starting the API. Do not commit secrets, API keys, or credentials to version control.

### Running the API

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`. Interactive documentation is available at `http://localhost:8000/docs`, and the OpenAPI specification is available at `http://localhost:8000/openapi.json`.

### TypeScript SDK

```bash
cd sdk/typescript
npm install
npm run build
npm run typecheck
```

## SDK Usage

```ts
import { MeetlyClient } from "@meetly/sdk";

const client = new MeetlyClient({
  baseUrl: "http://localhost:8000",
});

const meeting = await client.createMeeting();
console.log(meeting.meeting_id);

const status = await client.getMeeting(meeting.meeting_id);
console.log(status);
```

An API key can be supplied when creating the client:

```ts
const client = new MeetlyClient({
  baseUrl: "https://your-api.example.com",
  apiKey: "your-api-key",
});
```

The SDK sends the key using the Bearer authorization scheme.

## API Reference

### Health

`GET /health/` returns the health status of the API.

### Root

`GET /` returns basic project and API information.

### Create a Meeting

`POST /meetings` creates and registers a new meeting.

Example response:

```json
{
  "meeting_id": "mtg_...",
  "state": "idle"
}
```

### Get Meeting Status

`GET /meetings/{meeting_id}` returns the current state of a meeting.

Example response:

```json
{
  "meeting_id": "mtg_...",
  "state": "idle",
  "running": false
}
```

### Start a Meeting

`POST /meetings/{meeting_id}/start` starts processing for a registered meeting.

### Stop a Meeting

`POST /meetings/{meeting_id}/stop` stops processing for a meeting.

### Get Transcript

`GET /meetings/{meeting_id}/transcript` returns the finalized transcript.

Example response:

```json
{
  "meeting_id": "mtg_...",
  "transcript": "..."
}
```

### Get Summary

`GET /meetings/{meeting_id}/summary` generates and returns an AI-powered summary.

Example response:

```json
{
  "meeting_id": "mtg_...",
  "summary": "..."
}
```

### Ask a Question

`POST /meetings/{meeting_id}/ask` allows a question to be asked about the finalized meeting.

Request:

```json
{
  "question": "What were the main decisions?"
}
```

Response:

```json
{
  "meeting_id": "mtg_...",
  "question": "What were the main decisions?",
  "answer": "..."
}
```

## Meeting States

| State | Description |
|---|---|
| idle | Meeting has been created but processing has not started |
| running | Meeting processing is active |
| stopping | Meeting is in the process of stopping |
| stopped | Meeting processing has stopped |
| error | Meeting processing encountered an error |

## Testing

Python tests are located under `tests/`. Run them with:

```bash
pytest
```

TypeScript SDK tests are located under `sdk/typescript/tests/`. Run type checks with:

```bash
cd sdk/typescript
npm run typecheck
```

If test tooling is configured for the SDK, run:

```bash
npm test
```

## Deployment

Meetly can be deployed as a web service on any platform that supports Python ASGI applications. For a deployment such as Railway, start the application with:

```bash
uvicorn api.main:app --host 0.0.0.0 --port $PORT
```

Ensure all required environment variables and external AI or audio service credentials are configured in the deployment environment. After deployment, the FastAPI documentation should be available at `https://<your-domain>/docs`.

## Error Handling

The API communicates failures using standard HTTP status codes:

- `404` indicates the meeting does not exist
- `400` indicates an invalid meeting operation or request
- `500` indicates an internal server error

The TypeScript SDK exposes a `MeetlyError` class containing a `message` and a `status` field:

```ts
try {
  await client.getMeeting("missing");
} catch (error) {
  if (error instanceof MeetlyError) {
    console.error(error.status);
    console.error(error.message);
  }
}
```

## Security

- Do not commit API keys or other secrets to the repository
- Store deployment credentials in environment variables
- Use HTTPS in production
- Do not expose development credentials in client-side applications

## License

This project is licensed under the terms included in this repository. See the `LICENSE` file for details.
