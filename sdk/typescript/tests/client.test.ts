import { describe, expect, it, vi } from "vitest";

import {
  MeetlyClient,
  MeetlyError,
} from "../src/client.js";


describe("MeetlyClient", () => {
  it("creates a client successfully", () => {
    const client = new MeetlyClient({
      baseUrl: "http://localhost:8000",
    });

    expect(client).toBeInstanceOf(MeetlyClient);
  });


  it("creates a client with an API key", () => {
    const client = new MeetlyClient({
      baseUrl: "http://localhost:8000",
      apiKey: "test-api-key",
    });

    expect(client).toBeInstanceOf(MeetlyClient);
  });


  it("creates a meeting", async () => {
    const mockResponse = {
      meeting_id: "meeting-123",
      state: "idle",
    };

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify(mockResponse),
          {
            status: 200,
            headers: {
              "Content-Type": "application/json",
            },
          },
        ),
      ),
    );

    const client = new MeetlyClient({
      baseUrl: "http://localhost:8000",
    });

    const result = await client.createMeeting();

    expect(result).toEqual(mockResponse);

    expect(fetch).toHaveBeenCalledWith(
      "http://localhost:8000/meetings",
      expect.objectContaining({
        method: "POST",
      }),
    );
  });


  it("gets a meeting", async () => {
    const mockResponse = {
      meeting_id: "meeting-123",
      state: "idle",
      running: false,
    };

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify(mockResponse),
          {
            status: 200,
            headers: {
              "Content-Type": "application/json",
            },
          },
        ),
      ),
    );

    const client = new MeetlyClient({
      baseUrl: "http://localhost:8000/",
    });

    const result = await client.getMeeting(
      "meeting-123",
    );

    expect(result).toEqual(mockResponse);

    expect(fetch).toHaveBeenCalledWith(
      "http://localhost:8000/meetings/meeting-123",
      expect.objectContaining({
        method: "GET",
      }),
    );
  });


  it("rejects an empty meeting ID", async () => {
    const client = new MeetlyClient({
      baseUrl: "http://localhost:8000",
    });

    await expect(
      client.getMeeting(""),
    ).rejects.toThrow(
      "meetingId cannot be empty.",
    );
  });


  it("encodes special characters in meeting IDs", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            meeting_id: "abc/123",
            state: "idle",
            running: false,
          }),
          {
            status: 200,
            headers: {
              "Content-Type": "application/json",
            },
          },
        ),
      ),
    );

    const client = new MeetlyClient({
      baseUrl: "http://localhost:8000",
    });

    await client.getMeeting("abc/123");

    expect(fetch).toHaveBeenCalledWith(
      "http://localhost:8000/meetings/abc%2F123",
      expect.objectContaining({
        method: "GET",
      }),
    );
  });


  it("throws MeetlyError for HTTP errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: "Meeting not found.",
          }),
          {
            status: 404,
            headers: {
              "Content-Type": "application/json",
            },
          },
        ),
      ),
    );

    const client = new MeetlyClient({
      baseUrl: "http://localhost:8000",
    });

    await expect(
      client.getMeeting("missing"),
    ).rejects.toMatchObject({
      name: "MeetlyError",
      message: "Meeting not found.",
      status: 404,
    });
  });


  it("sends the API key as an authorization header", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            meeting_id: "meeting-123",
            state: "idle",
            running: false,
          }),
          {
            status: 200,
            headers: {
              "Content-Type": "application/json",
            },
          },
        ),
      ),
    );

    const client = new MeetlyClient({
      baseUrl: "http://localhost:8000",
      apiKey: "test-api-key",
    });

    await client.getMeeting("meeting-123");

    expect(fetch).toHaveBeenCalledWith(
      "http://localhost:8000/meetings/meeting-123",
      expect.objectContaining({
        method: "GET",
        headers: expect.any(Headers),
      }),
    );

    const call = vi.mocked(fetch).mock.calls[0];
    const options = call[1];

    const headers = options?.headers;

    expect(
      headers instanceof Headers
        ? headers.get("Authorization")
        : null,
    ).toBe("Bearer test-api-key");
  });


  it("exports MeetlyError correctly", () => {
    const error = new MeetlyError(
      "Test error",
      500,
    );

    expect(error).toBeInstanceOf(Error);
    expect(error).toBeInstanceOf(MeetlyError);
    expect(error.message).toBe("Test error");
    expect(error.status).toBe(500);
  });
});