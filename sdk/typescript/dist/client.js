export class MeetingResource {
    client;
    id;
    provider;
    state;
    constructor(client, response) {
        this.client = client;
        this.id = response.meeting_id;
        this.provider = response.provider;
        this.state = response.state;
    }
    async start() {
        return this.client.startMeeting(this.id);
    }
    async stop() {
        return this.client.stopMeeting(this.id);
    }
    async getTranscript() {
        const response = await this.client.getTranscript(this.id);
        return response.transcript;
    }
    async getTranscriptResponse() {
        return this.client.getTranscript(this.id);
    }
    async getStatus() {
        return this.client.getMeeting(this.id);
    }
}
export class MeetingsResource {
    client;
    constructor(client) {
        this.client = client;
    }
    async create(options) {
        const response = await this.client.createMeeting(options);
        return new MeetingResource(this.client, response);
    }
}
export class MeetlyError extends Error {
    status;
    constructor(message, status) {
        super(message);
        this.name = "MeetlyError";
        this.status = status;
        Object.setPrototypeOf(this, MeetlyError.prototype);
    }
}
export class MeetlyClient {
    baseUrl;
    apiKey;
    meetings;
    constructor(options) {
        if (!options.baseUrl.trim()) {
            throw new Error("baseUrl cannot be empty.");
        }
        this.baseUrl = options.baseUrl.replace(/\/+$/, "");
        this.apiKey = options.apiKey;
        this.meetings = new MeetingsResource(this);
    }
    async request(path, options = {}) {
        const headers = new Headers(options.headers);
        headers.set("Accept", "application/json");
        if (options.body !== undefined) {
            headers.set("Content-Type", "application/json");
        }
        if (this.apiKey) {
            headers.set("Authorization", `Bearer ${this.apiKey}`);
        }
        let response;
        try {
            response = await fetch(`${this.baseUrl}${path}`, {
                ...options,
                headers,
            });
        }
        catch (error) {
            throw new MeetlyError(error instanceof Error
                ? error.message
                : "Network request failed.", 0);
        }
        if (!response.ok) {
            let message = `Request failed with status ${response.status}.`;
            try {
                const data = await response.json();
                if (data &&
                    typeof data.detail === "string") {
                    message = data.detail;
                }
            }
            catch {
                // Keep the default error message.
            }
            throw new MeetlyError(message, response.status);
        }
        return response.json();
    }
    async createMeeting(options) {
        const body = options
            ? JSON.stringify({
                provider: options.provider,
                meeting_url: options.meetingUrl,
            })
            : undefined;
        return this.request("/meetings", {
            method: "POST",
            ...(body ? { body } : {}),
        });
    }
    async getMeeting(meetingId) {
        this.validateMeetingId(meetingId);
        return this.request(`/meetings/${encodeURIComponent(meetingId)}`, {
            method: "GET",
        });
    }
    async startMeeting(meetingId) {
        this.validateMeetingId(meetingId);
        return this.request(`/meetings/${encodeURIComponent(meetingId)}/start`, {
            method: "POST",
        });
    }
    async stopMeeting(meetingId) {
        this.validateMeetingId(meetingId);
        return this.request(`/meetings/${encodeURIComponent(meetingId)}/stop`, {
            method: "POST",
        });
    }
    async getTranscript(meetingId) {
        this.validateMeetingId(meetingId);
        return this.request(`/meetings/${encodeURIComponent(meetingId)}/transcript`, {
            method: "GET",
        });
    }
    async getSummary(meetingId) {
        this.validateMeetingId(meetingId);
        return this.request(`/meetings/${encodeURIComponent(meetingId)}/summary`, {
            method: "GET",
        });
    }
    async ask(meetingId, question) {
        this.validateMeetingId(meetingId);
        if (!question.trim()) {
            throw new Error("question cannot be empty.");
        }
        return this.request(`/meetings/${encodeURIComponent(meetingId)}/ask`, {
            method: "POST",
            body: JSON.stringify({
                question,
            }),
        });
    }
    validateMeetingId(meetingId) {
        if (!meetingId.trim()) {
            throw new Error("meetingId cannot be empty.");
        }
    }
}
