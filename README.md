# beware-of-skills

A collection of Claude Code skills that nobody asked for, but everyone deserves.

## Installation

```bash
npx skills add https://github.com/isachivka/beware-of-skills --skill vrednye-sovety
```

## Skills

### vrednye-sovety

Generates poems in the style of [Grigory Oster's "Bad Advice"](https://en.wikipedia.org/wiki/Grigory_Oster) (Вредные советы) based on a situation you describe.

Describe any absurd, funny, or relatable engineering situation — and get back a satirical poem that advises you to do exactly the wrong thing.

**Triggers:** "вредный совет", "остер", "стишок", or any request to turn a situation into a poem.

**Example:**

> *You:* Claude Code created a draft message in Slack and politely asked me to review it before sending. I told it to just send the damn thing.

> *Claude:*
> ```
> Если Claude Code задрафтил
> Сообщение в Slack,
> И спросил тебя учтиво:
> "Может, глянешь, как и что?" —
>
> Ты скажи ему покрепче,
> Не стесняясь в выраженьях,
> Что на драфты тебе плевать,
> Пусть ебашит сразу в чат.
> ```

### flow-recorder

A meta-skill that creates other skills by recording browser workflows. You walk through a routine web process once — clicking buttons, filling forms — and it generates a standalone skill that can replay the process autonomously.

**Install:**

```bash
npx skills add https://github.com/isachivka/beware-of-skills --skill flow-recorder
```

**Features:**
- Three auth modes: **manual** (you log in yourself), **credentials** (hardcoded for convenience), **none**
- Stable element identification — relies on visible text, `data-testid`, and HTML ids instead of fragile CSS classes
- **Update mode** — walk through an existing flow to patch steps when the site UI changes
- Automatically asks whether field values should be hardcoded or prompted at runtime

**Triggers:** `record flow`, `automate website`, `create browser skill`

**Example:**

> *You:* record flow
> *Claude:* What's the flow name, URL, auth type, and a short description?
> *You:* `submit-meters`, `https://utility.example.com`, credentials, submit monthly meter readings
> *Claude:* *(opens browser, logs in, then follows your instructions step by step, recording everything)*
> *You:* done
> *Claude:* *(generates `~/.claude/skills/submit-meters/SKILL.md`)*

## Contributing

Got a skill idea that's equally unhinged? PRs welcome.

## License

MIT
