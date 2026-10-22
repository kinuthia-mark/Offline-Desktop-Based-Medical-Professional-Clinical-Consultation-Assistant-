# ADR-018: Readable colours, visible keyboard focus and text that wraps

- Status: accepted
- Date: 2026-10-22
- Requirement IDs: FR-03, FR-06, FR-16 (the screens); AMD-42 (the theme)
- Evidence: `src/clinassist/ui/theme.py`, the accessibility tests in `tests/test_ui.py`

## Context
An accessibility review of the screens against WCAG 2.1 level AA measured every text colour
against the backgrounds it sits on, using the WCAG contrast formula. Body text passed easily
(13 to 15:1). The colours that carry meaning did not, because each was one fixed colour used on
both the light and the dark version:

| Colour | Light | Dark | Needed |
|---|---|---|---|
| amber "AI-generated" labels | 2.95 | 5.10 | 4.5 |
| error red | 4.04 | 3.73 | 4.5 |
| green "Offline: verified" | 3.45 | 4.37 | 4.5 |
| grey model label | 3.95 | 3.81 | 4.5 |
| white text on teal buttons | 6.04 | 3.32 | 4.5 |
| outline of text boxes and buttons | 1.42 | 1.41 | 3.0 |

The amber label that marks AI-generated text was the hardest text on the light screen to read,
although it is one of the most important. The review also found no visible keyboard focus on
buttons (the stylesheet replaced Qt's own), and the status line of the first panel was cut off,
not wrapped, when the panel was narrow.

## Decision
- **Meaning colours belong to the theme.** Five tones (`ai`, `error`, `ok`, `warn`, `quiet`)
  have their own shade in the light and the dark version, each at least 4.5:1 on every
  background it is used on. Labels name the tone with `theme.tone(label, "ai")` instead of
  setting a colour; no screen sets a colour itself any more.
- **Buttons in the dark version** use a deeper teal behind white text (5.5:1); titles and tabs
  keep the brand teal, which passes as text.
- **Outlines** of text boxes and buttons are at least 3:1 (WCAG 1.4.11), so a box can be seen
  without colour.
- **Keyboard focus is visible:** a 2-pixel border on the focused button, text box, list and
  table, and an outline on check boxes and tabs (WCAG 2.4.7).
- **The status line wraps** (WCAG 1.4.10). The network label's words say what the check found;
  the colour only repeats it (WCAG 1.4.1).
- Disabled buttons keep their lower contrast: WCAG does not require contrast for inactive
  controls, and lower contrast is how they read as unavailable.

## Evidence
- `test_every_text_colour_meets_wcag_aa_contrast` computes the WCAG ratio for every text tone
  and the outlines, in both versions, from the colour tables. Putting the old amber back makes
  it fail.
- `test_meaning_colours_come_from_the_theme`, `test_unknown_tone_is_refused`,
  `test_keyboard_focus_is_visible`, `test_the_next_step_wraps_instead_of_being_cut_off`.
- Both versions rendered and checked by eye on the reference PC.

## Limits
- Not tested with a screen reader (Windows Narrator or NVDA). Qt gives standard controls their
  names and roles, but the program was not walked through with one.
- Text size follows Windows' scaling setting; the layout was checked at the default size only.
