export type MeetingState =
  | "idle"
  | "running"
  | "stopping"
  | "stopped"
  | "error";

export type MeetingProvider = "local" | "google_meet";

export interface CreateMeetingOptions {
  provider: MeetingProvider;
  meetingUrl?: string;
}


export interface CreateMeetingResponse {
  meeting_id: string;
  state: MeetingState;
  provider?: MeetingProvider;
}


export interface MeetingResponse {
  meeting_id: string;
  state: MeetingState;
  running: boolean;
  provider?: MeetingProvider;
}


export interface TranscriptResponse {
  meeting_id: string;
  transcript: string;
}


export interface SummaryResponse {
  meeting_id: string;
  summary: string;
}


export interface AskRequest {
  question: string;
}


export interface AskResponse {
  meeting_id: string;
  question: string;
  answer: string;
}
