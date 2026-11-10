# Video timeline interaction contract

- Source units: `Interval(start_ms,end_ms)`, ordered non-overlapping, half-open.
- Original video stays at its absolute time. For selected segment i: output time = cumulative preceding kept durations + (source time − segment i start).
- Browser `timeupdate` can arrive late (coarse sampling); manual preview seeks must not be treated as exact frame boundaries or final audio quality.
- Editing: numeric fields in seconds on-screen, convert to integer ms for POST `/api/plan` and use server validation.
- Timeline background: excluded regions; green sections: kept original intervals. Playhead always shows original media position, even if the time counter shows output time in preview mode.
- Restoring suggestions or full source invalidates approval and previous export.
- Export API is blocked until a user sends `POST /api/approve` and receives acceptance.
- A successful export links to `/api/export`. Use HTTP Range for video seeking from `/api/media`.
- Transcript panel comes from ClosedRoom only. Transcript text is evidence; never auto-remove spoken words based on reading text.

Regression cases: seeking within excluded region, jumping to next keep, final segment stops, invalid overlapping ranges, slow rendering, audio unavailable, non-decodable browser codec, mobile UI.
