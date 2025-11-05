"""Constants for log messages used throughout the TTV pipeline."""

# Directory creation messages
LOG_TTV_DIR_CREATED = "Created TTV directory: "

# Video segment creation and processing
LOG_VIDEO_SEGMENT_CREATE = "Creating video segment: output_path"
LOG_FFPROBE_COMMAND = "Running ffprobe command: ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1"
LOG_FINAL_VIDEO_CREATED = "Final video with closing credits created: output_path"
LOG_CLOSING_CREDITS_DURATION = "Generated closing credits duration"

# Background music processing
LOG_BACKGROUND_MUSIC_SUCCESS = "Successfully added background music"
LOG_BACKGROUND_MUSIC_FAILURE = "Failed to add background music"

# Final video output
LOG_FINAL_VIDEO_PATH = "Final video created at: output_path={}"
