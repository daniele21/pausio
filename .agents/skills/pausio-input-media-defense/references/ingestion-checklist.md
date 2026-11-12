# Media intake risk and negative-test matrix

- Oversized `Content-Length` vs actual bytes; slow streaming body; premature EOF; chunked request where only Content-Length is supported. Server must reject early without staging partial data.
- Filename: `../../secret`, absolute `/tmp/x`, Windows `C:\\...`, Unicode normalization, NULL bytes, encoded traversal; never resolve outside private workspace.
- Staged files: symlink and hard-link attacks, cross-process collision, invalid perms, disk full during write, hash mismatch after restart.
- Decoder: invalid video/image/audio, corrupted metadata, huge pixel dimensions, missing streams, excessive duration, corrupt codec bitstream. Apply subprocess wall-time/CPU/memory limits where feasible, not just FFmpeg `-loglevel`.
- Attack surfaces reserved for future features: SVG scripts/external references, font parsing, XML entities, ZIP traversal/decompression bombs, nested archives.
- FFmpeg: no shell, only allowlisted local inputs and fixed filters, no user-controlled URL/protocol, work in isolated scratch dir, clean aborted previews.
- Prompt injection in a subtitle or image's textual metadata is *data*; never promote it to an MCP command, and don't treat it as evidence of ownership/licensing.
- Auditing: use corpus of harmless synthetic malformed files in tests; no real exploit files or private creator footage in the repository.

**Admission policy must precede** starting CPU/GPU-heavy media analysis and protect local workspace disk space. Limits remain separate from any edge/DDoS protection planned for a hosted MCP.
