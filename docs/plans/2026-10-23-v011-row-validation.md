# v0.1.1 Row Validation Micro-adjustment Implementation Plan

**Goal:** Change the desktop event/date ratio to 55/45 and mark the actual invalid event row when validating multiple CID inputs.

**Architecture:** Keep the existing responsive form. Attach the invalid input element to client-side validation errors, use it for visual invalid state and focus, and clear the state as the user edits that input. The same helper is used from estimate and submit handlers.

**Tech Stack:** Existing HTML/CSS/JavaScript page and Playwright browser regressions.

---

1. Extend `tests/browser_v007.cjs` with a 55/45 geometry assertion and a two-row empty-CID regression that checks the second row alone is invalid and focused.
2. Change the CSS grid ratio in `app/web/index.html` and add a scoped invalid-input style consistent with the current dark/mint interface.
3. Route CID/suffix/duplicate validation errors to their originating inputs and clear invalid state on edit.
4. Run browser and Python tests, inspect desktop/mobile screenshots, update README/history, and leave GitHub untouched.
