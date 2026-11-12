# Local MCP spike — Pausio Studio tools (experimental)

This is the **first proof of tool control**, not a shipped autonomous editor. It does not use or require an OpenAI/Anthropic inference API key. ChatGPT/Claude Chat perform any semantic/editorial analysis **outside** Pausio. The tool server only forwards a small allowlist of commands to your already-running Pausio Studio, which owns validation, revisions and rendering.

## Run with Claude Desktop (local stdio connector)

1. Start your current Pausio Studio on your Mac (same environment):

   ~~~bash
   source .venv/bin/activate
   pausio studio --port 8765
   ~~~

   Observe the **actual** port printed by Studio. When 8765 is occupied, Studio might choose 8766 or 8767.

2. Configure Claude Desktop's local MCP server entry (where supported). Replace `/ABSOLUTE/PATH` and `8765` with your actual venv and port:

   ~~~json
   {
     "mcpServers": {
       "pausio": {
         "command": "/ABSOLUTE/PATH/pausio/.venv/bin/pausio",
         "args": ["mcp", "--studio-port", "8765"]
       }
     }
   }
   ~~~

3. Restart the client if necessary, grant tool permissions, and ask it to call `pausio_get_project`, then `pausio_get_transcript`. A running Studio with an imported video is required for a useful transcript. Do not mistake a successful tool handshake for full video-understanding capability.

## Tool inventory (MVP)

- `pausio_get_project`: read active project snapshot (without transcript).
- `pausio_get_transcript`: request transcript only when needed.
- `pausio_get_job_status`: read current async job and preview status.
- `pausio_start_pause_analysis`: start the existing conservative FFmpeg pause proposal, not semantic video understanding.
- `pausio_apply_command`: only `segment.update`, `caption.correct`, `caption.configure`; must include the current `project_revision` and exact payload.
- `pausio_render_preview`: start FFmpeg preview, then poll the status tool.

No tool approves the final timeline, overwrites a source, posts to the internet, imports arbitrary files, executes a command, or renders the **final** export. Existing editor still requires human approval and final export. Tool writes are tracked by the same project command tape as UI edits.

## Limitations and next gate

- This is **stdio + loopback only**. It can be connected to supported desktop MCP clients but not directly to ChatGPT browser chat. Browser chat needs a separately authenticated HTTPS bridge and a real account-level capability test; never expose `/api/state`, `/api/command` or the Studio loopback port directly.
- Local MCP cannot itself view the chat video or generate overlay artwork; agent-driven storyboard, overlay editor, asset transfer, library, LUFS and self-hosted ASR are separate planned work packages in `AGENTIC_EDITING_PLAN.md`.
- It reads only the active Studio process on the selected port. One Studio local workspace/process is still the source of truth.
- The assistant may see the full transcript when you explicitly invoke the transcript tool. This is user-controlled data sharing with the chat product, not an invisible Pausio upload. Follow the product's own data controls.
- Run tests with `python -m unittest tests.test_local_mcp -v` or full CI. Test on the actual Claude Desktop version and account before claiming interactive compatibility.

Future agentic integration will use shared application services, atomic instruction batches, authenticated scoped HTTP/MCP transport and observation tools rather than building a second renderer.
