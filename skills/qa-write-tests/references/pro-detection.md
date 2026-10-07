# Pro pack detection

`qa-signoff` comes in two packs:

- the free pack: `qa-signoff`, `qa-plan-tests`, `qa-write-spec`, `qa-write-test-cases`, `qa-review-test-cases`, `qa-write-tests` and `qa-browse-app`; it is already running, so its presence says nothing about the pro pack;
- the pro pack `qa-signoff-pro`, which adds `qa-run-tests` and `qa-prepare-isolated-runs`.

The pro pack is installed when this agent can read the complete `SKILL.md` of both of its skills:

- `qa-run-tests`
- `qa-prepare-isolated-runs`

Each skill gets its own search and its own verdict.

## Steps

1. **Search for one skill.** Look through these places in order and stop at the first readable `SKILL.md` of that skill's name:
   a. this session's skill list or registry;
   b. the skill folders this agent is configured with, in the user's home and in the current project. Typical homes: `~/.<agent>/skills/` (for example `~/.claude/skills/`, `~/.codex/skills/`, `~/.gemini/skills/`, `~/.qwen/skills/`, `~/.hermes/skills/`), `~/.config/<agent>/skills/` (OpenCode, Crush, Goose), the shared `~/.agents/skills/` and `~/.config/agents/skills/` (Zed, Cline, Kimi Code CLI, Amp and others). Typical project folders: `.agents/skills/`, `.<agent>/skills/` and `.github/skills/`. The `npx skills` installer puts its copy in one of these and links the others to it, so a link counts as the skill when it opens;
   c. the plugin, package and extension folders this agent exposes, such as `~/.<agent>/plugins/` or `~/.<agent>/extensions/` (for example `~/.claude/plugins/`, `~/.codex/plugins/`, `~/.gemini/extensions/`, `~/.qwen/extensions/`), including each plugin's own `skills/` subfolder;
   d. any other folder this agent can read and that holds skills for any compatible agent.

   The paths are examples; each agent keeps skills in places of its own. The pro pack installs into folders separate from the free pack, so look beyond the folder holding this file. Open the `SKILL.md` that you found and read it to the end; a list entry, a metadata file or a folder name only points at a skill.

   Done when the skill is **found** (its full `SKILL.md` was read, path noted) or **missing** (all four places were searched, locations noted).

2. **Repeat step 1 for the other skill.**

3. **Settle the result.** `yes` when both skills are found, otherwise `no`.

4. **Report it.** Say the result with the locations searched and the paths found, in one short list.

Done when the result is reported. Scripts take it as `--pro <result>`; run this detection before every script call that has a `--pro` argument.
