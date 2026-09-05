class GoogleMeetError(Exception):
    """Base exception for Google Meet integration."""


class GoogleMeetAuthenticationError(GoogleMeetError):
    """Raised when Google Meet authentication fails."""


class GoogleMeetAPIError(GoogleMeetError):
    """Raised when the Google Meet API returns an error."""


class GoogleMeetNotFoundError(GoogleMeetAPIError):
    """Raised when a requested Google Meet resource is not found."""


class GoogleMeetValidationError(GoogleMeetError):
    """Raised when Google Meet request data is invalid."""