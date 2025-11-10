#!/usr/bin/env python3
"""CLI interface for ganglia-studio."""

import argparse

from ganglia_studio.video.ttv import text_to_video


def main():
    parser = argparse.ArgumentParser(description="GANGLIA Studio - Multimedia Generation")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Video generation
    video_parser = subparsers.add_parser("video", help="Generate video from text")
    video_parser.add_argument("--config", required=True, help="Path to TTV config JSON")
    video_parser.add_argument("--output", help="Output directory")

    args = parser.parse_args()

    if args.command == "video":
        text_to_video(args.config, args.output)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
