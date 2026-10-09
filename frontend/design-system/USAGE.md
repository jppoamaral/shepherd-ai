# Shepherd design system (for building the Angular app)

Source of truth for look and feel. Read `README.md` here first (voice, color rules, layout), then `tokens.json`.

- `tokens.css`: CSS custom properties and type classes. Import it once in the Angular global styles. Never hard-code a hex value, size or radius; use the variables.
- `components/bundle.css`: the `sh-*` class styles for every component. Port each into an Angular component, keeping the class names and markup shown in `components/<Name>/preview.html`.
- `components/<Name>/README.md`: usage rules for each component. `preview.html` needs `tokens.css` and `bundle.css` loaded to render.
- Fonts: EB Garamond (headings) and DM Sans (everything else), from Google Fonts: `https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=EB+Garamond:wght@500;600&display=swap`.
- Rules that apply in code: status is never color alone (icon + word); tap targets are at least `--tap-min` (44px); text is never lighter than `--ink-muted`; gold is a fill only (use `--gold-deep` for gold text); nothing is sent or recorded until a leader approves.
- Design phone first at 390px, then desktop (240px sidebar, two columns where two paths sit side by side).
- `tokens.json` is also what the design tool reads. If you change a value here, tell the user so the design file can be updated to match.

## Screen designs

The approved mockups for Home, Rosters, Conflict huddle and Memory (mobile and desktop, plus empty, loading, error and editing states) are in `screens/`. Read `screens/README.md` first. Use them for layout, copy and behavior; build with `tokens.css` and the `sh-*` components, not the hex values inside the mockups.
