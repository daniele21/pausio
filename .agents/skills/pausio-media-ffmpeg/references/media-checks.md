# FFmpeg checks and diagnostic protocol

Start with (quote input paths):

`ffprobe -v error -show_format -show_streams -of json "input.mp4"`

For timing problems compare source video stream `time_base` and `start_time`, audio `sample_rate` and `start_time`, metadata rotation, `r_frame_rate` vs `avg_frame_rate`; inspect original frames near each cut. For the current pipeline use:

`python -m pausio inspect "input.mp4"`
`python -m pausio plan "input.mp4" -o "plan.json"`
`python -m pausio render "plan.json" -o "render.mp4" --dry-run`

Synthetic cases: no audio, one keep segment, disjoint intervals, zero-length invalid interval, trailing silence, initial silence, portrait with rotation metadata, VFR with monotonic timestamps, stereo/mono, input with negative timestamps, extremely short clip, unusual paths, corrupt source, stalled FFmpeg, existing output.

Important: `silencedetect` measures low-energy signal, **not human speech**. Do not promise precise word-level editing or sync without evaluating it.

Upstream references:
- https://ffmpeg.org/ffmpeg-filters.html
- https://ffmpeg.org/ffprobe.html
- https://github.com/WyattBlue/auto-editor (workflow inspiration only)
