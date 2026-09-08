import type { AskResponse, CreateMeetingOptions, CreateMeetingResponse, MeetingResponse, SummaryResponse, TranscriptResponse } from "./types.js";
export declare class MeetingResource {
    private readonly client;
    readonly id: string;
    readonly provider?: CreateMeetingResponse["provider"];
    readonly state: CreateMeetingResponse["state"];
    constructor(client: MeetlyClient, response: CreateMeetingResponse);
    start(): Promise<MeetingResponse>;
    stop(): Promise<MeetingResponse>;
    getTranscript(): Promise<string>;
    getTranscriptResponse(): Promise<TranscriptResponse>;
    getStatus(): Promise<MeetingResponse>;
}
export declare class MeetingsResource {
    private readonly client;
    constructor(client: MeetlyClient);
    create(options: CreateMeetingOptions): Promise<MeetingResource>;
}
export interface MeetlyClientOptions {
    baseUrl: string;
    apiKey?: string;
}
export declare class MeetlyError extends Error {
    readonly status: number;
    constructor(message: string, status: number);
}
export declare class MeetlyClient {
    private readonly baseUrl;
    private readonly apiKey?;
    readonly meetings: MeetingsResource;
    constructor(options: MeetlyClientOptions);
    request<T>(path: string, options?: RequestInit): Promise<T>;
    createMeeting(options?: CreateMeetingOptions): Promise<CreateMeetingResponse>;
    getMeeting(meetingId: string): Promise<MeetingResponse>;
    startMeeting(meetingId: string): Promise<MeetingResponse>;
    stopMeeting(meetingId: string): Promise<MeetingResponse>;
    getTranscript(meetingId: string): Promise<TranscriptResponse>;
    getSummary(meetingId: string): Promise<SummaryResponse>;
    ask(meetingId: string, question: string): Promise<AskResponse>;
    private validateMeetingId;
}
