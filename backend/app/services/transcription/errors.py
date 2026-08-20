"""Errors exposed by the media-transcription API."""


class TranscriptionError(RuntimeError):
    """Base error exposed by the transcription API."""


class MediaDownloadError(TranscriptionError):
    """The allowlisted upstream media could not be downloaded."""


class ModelUnavailableError(TranscriptionError):
    """The local speech recognition model could not be loaded."""


class PunctuationModelUnavailableError(ModelUnavailableError):
    """The local punctuation restoration model could not be loaded."""


class VocalSeparationError(TranscriptionError):
    """The local vocal/accompaniment separation step could not complete."""
