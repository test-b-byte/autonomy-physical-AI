# Rescue app — iteration log

Newest first. The version is also saved inside every medical report and shown on the summary page,
so any report can be traced to the exact code that produced it.

## v0.7
- **Mode rules confirmed:** ESCORT needs both "can walk" and "safe to move" OK/FINE. RESPONDER = can't move but no
  immediate threat to life: the drone returns to the TOC fast to update the rescue team. BEACON = immediate threat to life.
- **Emergency beacon reworked:** the drone hovers at an offset (200 m toward the rescue team) and sends the casualty's
  location relative to the beacon by IR / optical Morse, e.g. "SOS SW 200" = casualty is 200 m south-west of the light.
  The screen shows the transmission live and explains that IR can't be seen.
- **Removed screen FLASH:** a visible blinking screen could give away the casualty's position to hostiles, which is what
  the offset is meant to avoid.
- **New: WAIT FOR FRIENDLY SIGNAL.** Shows the rescuers' recognition signal (3 short flashes or 3 whistles), how to answer,
  and time waited. HEARD IT logs the time in the report's events.

## v0.6
- **Point-of-contact modes**, decided on the device from the medical answers (modes.py):
  - **BEACON** (emergency): SEVERE bleeding or breathing, or SEVERE on two or more of bleeding/breathing/head/cold.
  - **RESPONDER** (help coming): can't walk, not safe to move, or SEVERE head wound. Skipped = worse case.
  - **ESCORT**: can walk and safe to move.
- After REPORT COLLECTED: a colored mode briefing (what's happening, what to do, why), then:
  - ESCORT: route map to the team with walking ETA; PAUSE/GO, DONE, and HURT (switches to RESPONDER).
  - RESPONDER: situation map while the drone flies home, then STAY HERE with team ETA and rotating survival tips; screen off after 45 s.
  - BEACON: live Morse display of the drone's signal (SOS, plus grid if map_state.json supplies `you.grid`); FLASH makes this screen blink the same signal.
- Report JSON now records `mode`, `mode_reason`, and an `events` list of mode decisions and changes.

## v0.5
- New SITUATION MAP page after REPORT COLLECTED (which now auto-advances after 5 s).
  Pixel-style tactical map centered on YOU: drone, rescue team / deployment point, hazards,
  hostiles, range rings with distances, dashed line showing where the drone will fly,
  and a SITREP panel listing each item's distance and compass direction.
- Symbols: friendly = blue rectangle, hostile = red diamond, hazard = orange triangle, drone = cyan X.
  They blink at different rates; YOU's uncertainty ring pulses.
- 20 s countdown ("DRONE RETURNING IN ..s"), then the report is marked collected and the app closes.
- Map data: built-in estimates by default ("EST POS"); real positions, optional real map image,
  and a measured heading are read from map_state.json when present (map_data.py).
- Compass: north-up "EST" by default; with heading_deg the map turns to the device's heading ("MAG").
- RescueApp timers are now generic per page (auto_seconds / auto_action / animated).

## v0.4
- Last page now reads REPORT COLLECTED, counts down 5 seconds, marks the report collected
  (collected_at in the JSON), blanks the screen, and closes the app.
- Hold button 1 (leftmost) still goes back one page at any point, including during the countdown
  (going back cancels it; it restarts when you return to the last page).
- Removed "hold button 4 = new report" (the app closes instead).

## v0.3
- SAFE TO MOVE? icon redesigned to show danger: warning sign above fire, predator (paw print),
  and hostile person (dark silhouette, red eyes).

## v0.2
- Questions reordered, most life-threatening first: blood loss, breathing, head wound, cold,
  walking, arms, safe to move (7 questions).
- New icons: breathing (lungs), cold (thermometer + snowflake), safe to move (lying person + warning).
- Food / water question removed (icon kept in icons.py).
- Summary page spaces items to fit all 7.
- Iteration numbers added: version.py, CHANGELOG.md, version in report JSON and on summary page.

## v0.1
- First OOD build: hardware, layout, icons, content, pages, report, main.
- 5 questions (walk, blood loss, arms, food / water, head), 320x240 landscape, buttons 17/22/23/27.
- Tap = answer, hold button 1 = back, hold 2/3 = skip, hold 4 on summary = new report.
- Saves values list + needs_attention to reports/ (session file + latest.json).
