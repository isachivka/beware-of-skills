---
name: lowkey
description: >
  Drive the lowkey browser (bobuk.io) from an agent through its lowkeyctl helper: show, hide or
  rewind a saved site's window, list a page's controls, fill a labelled field, pick an option,
  click a button or link, attach a file, wait for a control, and read the page by exporting it
  to PDF. Works inside the site's own signed-in profile, so the agent acts as the person.
when_to_use: >
  Trigger on: lowkey, lowkeyctl, lowkey://, "in lowkey", "open <alias> in lowkey", "click X on
  <alias>", "fill the form on <alias>", "save <alias> as PDF", "what's on <alias> right now",
  a saved lowkey site named by its alias, or a task on a site the person is signed in to in
  lowkey but not in agent-browser.
allowed-tools: [Bash, Read]
---

# lowkey

lowkey is a minimal macOS WebKit browser: no tabs, saved sites open by **alias**, each with its
own persistent profile (cookies, sign-in). `lowkeyctl` is its local helper; it talks to the
running app over IPC.

## Setup check

```bash
command -v lowkeyctl || ls /Applications/lowkey.app/Contents/Helpers/lowkeyctl
jq -r '.sites[] | "\(.alias)\t\(.startURL)"' ~/.config/lowkey/config.json
```

- Not on PATH: `ln -s /Applications/lowkey.app/Contents/Helpers/lowkeyctl ~/.local/bin/`
  (a symlink is fine; a *copy* fails with "run the helper inside lowkey.app/Contents/Helpers").
- The aliases live in `~/.config/lowkey/config.json`. Aliases are case-insensitive. Adding,
  renaming or removing a site is the person's job in lowkey Settings (⌘,): removing one
  deletes its profile and sign-ins. Do not edit `config.json` by hand.

## What it can and cannot do

| Can | Cannot |
|---|---|
| show / hide / rewind a saved site's window | open an arbitrary URL in a site's window |
| list controls (`inspect`) | read the page text directly — use `save-pdf` + `pdftotext` |
| `fill` a text input or textarea | fill password fields |
| `select` in a native single `<select>` | radio buttons, checkboxes, multi-select, custom dropdowns (they are not in `inspect`; `click` on their label text gives `label not found`) |
| `click` a button or link by its label — clicking a submit button submits the form normally | anything in iframes, run JavaScript, take screenshots |
| `upload` one file (≤ 8 MiB) | submit by `fill`/`select`/`upload` alone — they only fire `input`/`change` |
| `save-pdf` shows typed values in inputs and textareas | navigate to another page of the site except by clicking a link on it |

If the task needs any of the right column, say so and use agent-browser instead (it does not
share lowkey's sign-ins).

## Commands

Run `lowkeyctl --help` for the command list and syntax. Exit 0 = done, 1 = refused (reason on
stderr as `lowkeyctl: <reason>`), 64 = bad usage. Reload, back and forward have no command; use
the deep links `open 'lowkey://<alias>/reload'` (`/back`, `/forward`, `/start`, `/close`).

## Labels are exact

Labels match rendered text or `aria-label`, **case-sensitive, whitespace-normalised, punctuation
included**: a field labelled `Customer name:` is not found as `Customer name`. Always take the
label from `inspect` output, never guess it:

```bash
lowkeyctl ha inspect            # "text\tCustomer name:" … "button\tSubmit order"
lowkeyctl ha fill 'Customer name:' 'Igor'
```

## Recipe: act on a page

```bash
a=ha
before=$(lowkeyctl $a status --json)       # remember open/visible to restore at the end
lowkeyctl $a open                          # only if it was not open
ready() {                                  # $1 = a label you expect; ~30 s
  for _ in $(seq 60); do lowkeyctl $a wait "$1" --timeout 2 2>/dev/null && return 0; sleep 0.5; done
  return 1
}
ready 'Submit order' || { lowkeyctl $a status --json; exit 1; }
lowkeyctl $a inspect                       # copy exact labels from here
lowkeyctl $a fill 'Customer name:' 'Igor'
lowkeyctl $a save-pdf "$(mktemp -d)/check.pdf"   # verify the values took (see below)
lowkeyctl $a click 'Submit order'          # once; never retried
```

Right after `open`/`rewind`, and after a click that navigates, the page may still be on
`about:blank` or the old page: `wait` then fails fast with `wrong site origin` or `page loading`
instead of waiting. Hence the bounded loop over short `wait`s above, not one long `wait`.
After a navigating click, run `ready` with a label from the next page, or poll `status --json`
until `loading` is false, always with a bound.

`inspect` shows no current values. To check what a field holds before submitting, export the
page with `save-pdf` and read it: typed input and textarea values appear in the PDF.

## Recipe: read what is on the page

```bash
out=$(mktemp -d)/page.pdf
lowkeyctl ha save-pdf "$out" && pdftotext -layout "$out" - | head -200
```

Use a fresh path every time (it never overwrites). It prints the current document only: lazy
content that has not loaded and virtualised lists are missing. Read the PDF with the Read tool
when the layout matters.

## Rules

- **The person is signed in there.** Every click, fill and upload happens as them, on real
  accounts. Anything that sends, buys, deletes, posts or changes settings needs the person's
  go-ahead. An explicit request for exactly that action ("submit the order") is the go-ahead;
  if what you see before the click differs from what they asked for (another total, a payment
  step, a different recipient), stop and ask.
- **Never retry `click` or `upload` automatically.** Exit 0 means the event was dispatched, not
  that the site did anything; a nonzero exit after a timeout may still have acted. Check with
  `status`, `inspect` or `save-pdf`, then decide.
- **Leave the window as you found it**, per the `status` you took first: it was not open →
  `open 'lowkey://<alias>/close'` (releases the page, keeps the profile); it was open but hidden
  → `lowkeyctl <alias> hide`; it was visible → leave it. Don't `rewind` a page the person is in
  the middle of using.
- Page commands work only when the page is on the site's start origin (scheme, host, port) and
  only in the main document, including open shadow roots, never iframes. A redirect elsewhere
  (sign-in, another host) gives `wrong site origin`: the person needs to sign in in lowkey.

## Errors

| stderr | Meaning / next step |
|---|---|
| `unknown site: X` | No such alias. List them from `config.json`. |
| `window not open` | `open` it first (page commands never open it). |
| `wrong site origin` | Still loading, or navigated off the start origin / to a sign-in page. |
| `label not found` / `ambiguous label` | Re-run `inspect`, copy the exact label. Radios/checkboxes are not controls here. |
| `control disabled` / `control read only` | The page is not ready for it; `wait <label>`. |
| `page loading` | Poll `status` until `loading` is false. |
| `wait timed out` | The control never became visible and enabled. |
| `PDF export failed: … already exists` | Pick a new path. |
| `no reply from lowkey` / `another copy of lowkey is running` | App hung or a second copy runs; tell the person. |
