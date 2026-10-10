---
name: agterm-ask
description: >
  Inside agterm, ask the user a decision as a rich HTML page in an overlay instead of
  AskUserQuestion: every option explained in depth (how it works, pros/cons, cost, risk),
  with diagrams, charts, tables and code where they help; the user picks and can comment.
when_to_use: >
  Use INSTEAD of AskUserQuestion whenever AGTERM_ENABLED=1 and the choice is a real decision
  (architecture, approach, trade-off, anything where options need explaining); bos's
  PreToolUse hook denies AskUserQuestion inside agterm. A plain yes/no is just asked in chat
  text. Trigger also on: agterm-ask, /agterm-ask,
  "спроси меня в overlay", "дай развернутый выбор", "explain the options in a page".
allowed-tools: [Bash, Write]
---

# agterm-ask

Only inside agterm (`AGTERM_ENABLED=1`). Outside it, use AskUserQuestion. Inside it, bos's
`hooks/hooks.json` denies AskUserQuestion and points here (`BOS_ASK_HOOK=0` turns that off).

1. Research first, so every option is concrete. Use whatever tools a good explanation needs:
   read the code, measure, run a benchmark, look up docs.
2. Write an HTML **fragment** (no `<html>`/`<head>`) to the scratchpad. It is wrapped in a
   themed page with a form, a comment box and an Answer button.
3. Run it **with `run_in_background: true`**. It blocks until the user answers, and the user
   may take longer than a foreground Bash timeout allows:

   ```bash
   agterm-ask /path/body.html --title "How do we cache the API?"
   ```

   Add `--follow` only when the user is waiting on this question right now; otherwise the page
   opens quietly on your session, with a desktop notification, and they see it when they come back.
4. End your turn. In a flows step (your turn began with a `▶ flow:` line), first run
   `flow wait --human --note "<the question>"`: a turn that ends without it counts as silent, and
   flowd stops the run after the third. When the task notification arrives, read its stdout:
   - exit 0: `{"choice": ["b"], "note": "…"}` (Answer pressed, or closed after picking). `choice` lists the picked values; `note` is the
     free text (it can override or refine the choice, so read it). Act on it.
   - exit 3: `{"dismissed": true}`. They closed the page with nothing picked, so ask in chat
     what's wrong.
   - exit 4: another overlay is open on your session. If it is a page you opened yourself, close
     it (`agtermctl session overlay close --target "$AGTERM_SESSION_ID"`), ask again, and open your
     page again after the answer. Otherwise ask in plain chat.
   - exit 2: the overlay didn't open. Ask in plain chat (bos denies AskUserQuestion inside agterm).

## The fragment

One `.opt` section per option, with a radio `name="choice"` (checkboxes for multi-select).
Clicking anywhere in a `<label class="opt">` selects it.

```html
<p>Context: what's being decided and why it matters now. Two or three sentences.</p>

<label class="opt">
  <h2><input type="radio" name="choice" value="lru"> A. In-process LRU <span class="rec">recommended</span></h2>
  <p>How it works, what it changes in the code, what it costs.</p>
  <ul><li class="pro">+ zero infra</li><li class="con">− per-process, cold after deploy</li></ul>
  <pre><code>@lru_cache(maxsize=1000)
def fetch(id): ...</code></pre>
</label>

<label class="opt">
  <h2><input type="radio" name="choice" value="redis"> B. Redis</h2>
  <pre class="mermaid">flowchart LR; app --> redis --> api</pre>
</label>
```

Available out of the box:
- **Theme**: page colors follow the terminal theme. Use `var(--fg)`, `var(--accent)`,
  `var(--ok)`, `var(--bad)`, `var(--warn)`, and `color-mix` on them; never hardcode a palette.
- **Classes**: `.rec` (recommended badge), `.pro` / `.con`, `.card` (boxed aside), and
  tables, `<pre><code>`, `<code>`, all styled.
- **Mermaid**: `<pre class="mermaid">…</pre>`, loaded from CDN only when present.
- **Charts**: inline SVG is preferred, since it needs nothing. For a real chart library add
  `<script src="https://cdn.jsdelivr.net/npm/…@exact-version">` in the fragment; JS is on.
- **Extra fields**: any other named input (`<input name="budget">`) comes back as its own key.

Write it like a design review: what each option is, how it would actually look in this
codebase, its cost, risk and reversibility, and a comparison table when there are 3 or more.
Mark one `.rec` and say why. Write in the user's language.
