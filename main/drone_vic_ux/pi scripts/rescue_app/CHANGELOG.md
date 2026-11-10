# Rescue app — iteration log

Newest first. The version is also saved inside every medical report and shown on the summary page,
so any report can be traced to the exact code that produced it.

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
