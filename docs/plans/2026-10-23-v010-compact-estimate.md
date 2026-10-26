# v0.1.0 Compact Estimate Implementation Plan

**Goal:** Keep the query form full width after estimation and show only status, partition, and estimated cost next to the re-evaluate button.

**Architecture:** Move the receipt from the form's side column into the action buttons, reduce it to three visible facts, and keep errors in the existing result panel. Adjust the event/date grid from 40/60 to approximately 76/24 on desktop, stacking it on narrow screens.

**Tech Stack:** Existing single-file HTML/CSS/JavaScript frontend, FastAPI version metadata, Playwright and pytest regression tests.

---

1. Add browser assertions for unchanged form width between input/cost stages and compact receipt placement/content.
2. Move the receipt markup into the action rail and remove obsolete receipt-only JavaScript bindings and assignments.
3. Make the query form single-column in every stage, adjust responsive action rail and event/date proportions, and visually inspect desktop/mobile screenshots.
4. Bump version references to v0.1.0, update README/history, then run browser regressions, full pytest, and diff checks. Do not upload to GitHub.
