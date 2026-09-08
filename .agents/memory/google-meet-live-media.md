---
name: Google Meet live media
description: Durable constraints for connecting Meetly to real-time Google Meet media.
---

The Meet Media API's live-audio path requires the Cloud project, OAuth principal, and meeting participants to be enrolled in Google's Developer Preview. The REST API by itself does not provide live audio; a WebRTC media client must negotiate receive-only audio streams through `connectActiveConference`.

**Why:** Google's official reference clients use WebRTC for real-time media, while the REST API only provides the signaling endpoint and recorded-resource APIs.

**How to apply:** Preserve the reference client's SDP and transceiver behavior when changing the transport, and treat an unenrolled project or principal as a configuration/startup failure rather than silently falling back to browser automation or undocumented signaling.