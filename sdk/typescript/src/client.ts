import type {
  AskResponse,
  CreateMeetingResponse,
  MeetingResponse,
  SummaryResponse,
  TranscriptResponse,
} from "./types.js";


export interface MeetlyClientOptions {
  baseUrl: string;
  apiKey?: string;
}


export class MeetlyError extends Error {
  readonly status: number;

  constructor(
    message: string,
    status: number,
  ) {
    super(message);
    this.name = "MeetlyError";
    this.status = status;

    Object.setPrototypeOf(
      this,
      MeetlyError.prototype,
    );
  }
}


export class MeetlyClient {
  private readonly baseUrl: string;
  private readonly apiKey?: string;

  constructor(options: MeetlyClientOptions) {
    if (!options.baseUrl.trim()) {
      throw new Error(
        "baseUrl cannot be empty.",
      );
    }

    this.baseUrl = options.baseUrl.replace(
      /\/+$/,
      "",
    );

    this.apiKey = options.apiKey;
  }


  private async request<T>(
    path: string,
    options: RequestInit = {},
  ): Promise<T> {
    const headers = new Headers(
      options.headers,
    );

    headers.set(
      "Accept",
      "application/json",
    );

    if (options.body !== undefined) {
      headers.set(
        "Content-Type",
        "application/json",
      );
    }

    if (this.apiKey) {
      headers.set(
        "Authorization",
        `Bearer ${this.apiKey}`,
      );
    }

    let response: Response;

    try {
      response = await fetch(
        `${this.baseUrl}${path}`,
        {
          ...options,
          headers,
        },
      );
    } catch (error) {
      throw new MeetlyError(
        error instanceof Error
          ? error.message
          : "Network request failed.",
        0,
      );
    }

    if (!response.ok) {
      let message =
        `Request failed with status ${response.status}.`;

      try {
        const data = await response.json();

        if (
          data &&
          typeof data.detail === "string"
        ) {
          message = data.detail;
        }
      } catch {
        // Keep the default error message.
      }

      throw new MeetlyError(
        message,
        response.status,
      );
    }

    return response.json() as Promise<T>;
  }


  async createMeeting(): Promise<CreateMeetingResponse> {
    return this.request<CreateMeetingResponse>(
      "/meetings",
      {
        method: "POST",
      },
    );
  }


  async getMeeting(
    meetingId: string,
  ): Promise<MeetingResponse> {
    this.validateMeetingId(meetingId);

    return this.request<MeetingResponse>(
      `/meetings/${encodeURIComponent(meetingId)}`,
      {
        method: "GET",
      },
    );
  }


  async startMeeting(
    meetingId: string,
  ): Promise<MeetingResponse> {
    this.validateMeetingId(meetingId);

    return this.request<MeetingResponse>(
      `/meetings/${encodeURIComponent(meetingId)}/start`,
      {
        method: "POST",
      },
    );
  }


  async stopMeeting(
    meetingId: string,
  ): Promise<MeetingResponse> {
    this.validateMeetingId(meetingId);

    return this.request<MeetingResponse>(
      `/meetings/${encodeURIComponent(meetingId)}/stop`,
      {
        method: "POST",
      },
    );
  }


  async getTranscript(
    meetingId: string,
  ): Promise<TranscriptResponse> {
    this.validateMeetingId(meetingId);

    return this.request<TranscriptResponse>(
      `/meetings/${encodeURIComponent(meetingId)}/transcript`,
      {
        method: "GET",
      },
    );
  }


  async getSummary(
    meetingId: string,
  ): Promise<SummaryResponse> {
    this.validateMeetingId(meetingId);

    return this.request<SummaryResponse>(
      `/meetings/${encodeURIComponent(meetingId)}/summary`,
      {
        method: "GET",
      },
    );
  }


  async ask(
    meetingId: string,
    question: string,
  ): Promise<AskResponse> {
    this.validateMeetingId(meetingId);

    if (!question.trim()) {
      throw new Error(
        "question cannot be empty.",
      );
    }

    return this.request<AskResponse>(
      `/meetings/${encodeURIComponent(meetingId)}/ask`,
      {
        method: "POST",
        body: JSON.stringify({
          question,
        }),
      },
    );
  }


  private validateMeetingId(
    meetingId: string,
  ): void {
    if (!meetingId.trim()) {
      throw new Error(
        "meetingId cannot be empty.",
      );
    }
  }
}