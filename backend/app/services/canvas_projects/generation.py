"""Shared limits for paid Seedance video-generation work on the canvas."""

MIN_SEEDANCE_VIDEO_SECONDS = 4.0
MAX_SEEDANCE_VIDEO_SECONDS = 15.0
# Shorter segments keep product identity, hand interaction, and camera movement
# controllable during per-shot replacement. The API allows up to 15 seconds,
# but the canvas intentionally plans no more than eight by default.
PREFERRED_CANVAS_SEGMENT_SECONDS = 8.0
