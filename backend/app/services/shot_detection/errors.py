"""Errors exposed by the automatic shot-detection API."""


class ShotDetectionError(RuntimeError):
    """Base error exposed by the automatic shot-detection API."""


class ShotMediaDownloadError(ShotDetectionError):
    """The allowlisted source video could not be downloaded."""


class ShotDecodeError(ShotDetectionError):
    """The downloaded video cannot be decoded into frames."""
