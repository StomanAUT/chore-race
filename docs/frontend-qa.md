# Frontend QA

Use this matrix before a release that changes either Lovelace card. Test in
both the light and dark Home Assistant themes.

## Responsive sizes

- 1024 × 600 landscape tablet: race lanes and the scrollable task list remain
  visible together; planner controls do not overlap or leave the card.
- 768 × 1024 portrait tablet: content wraps without horizontal scrolling.
- 460 px dashboard column: the race stage becomes one column and its completion
  dialog fits the dynamic viewport.
- 320 px dashboard column: planner summaries, labels and action buttons wrap
  without clipping; touch controls remain at least 44 pixels high.

## Keyboard and screen reader

- Tab reaches every enabled control in a logical DOM order.
- Every focused input, select, button, summary, weekday and image choice has a
  visible focus indicator.
- Opening task completion moves focus into the dialog. Tab and Shift+Tab remain
  inside it; Escape closes it and returns focus to the originating task.
- Participant selection exposes `aria-pressed`; blocked actions are disabled
  and have a task-specific accessible label.
- Refresh/loading/success messages use a polite live region. Errors use an
  assertive alert.

## Motion and contrast

- With `prefers-reduced-motion: reduce`, cars, progress meters, live indicators
  and interaction transitions stop animating.
- With `force_reduced_motion: true`, the race card behaves the same regardless
  of the operating-system preference.
- Primary text uses Home Assistant's theme text colors. Muted text is never the
  only carrier of state: blocked, ready, completed and selected states also
  have labels, disabled controls, borders or accessible state.

