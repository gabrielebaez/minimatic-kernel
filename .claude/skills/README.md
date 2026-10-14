# Project skills

Vendored from [mattpocock/skills](https://github.com/mattpocock/skills) (MIT).

- **Installed:** 2026-10-14
- **Upstream commit:** `49dd158d1076134a641b33efb035946536778336`
- **Upstream version:** `mattpocock-skills` 1.3.1
- **Set:** the 27 promoted skills listed in upstream `.claude-plugin/plugin.json`
  (`skills/engineering/*` and `skills/productivity/*`). `misc/`, `in-progress/`
  and `deprecated/` are not installed.

These are editable copies, not a managed plugin, so they do not update
themselves. The two upstream install routes (`claude plugin install` and
`npx skills`) need the `claude` CLI or Node, neither of which was available
when these were installed; they were copied in by hand instead.

## Local changes

- `code-review` is installed as **`mp-code-review`** so it does not shadow
  Claude Code's built-in `/code-review`. The folder name, the `name:` field,
  and the references in `implement`, `implement-spec`, `tdd` and `ask-matt`
  were all renamed to match. Upstream treats renaming your own copy as the
  supported fix for this clash.
- The per-skill `agents/openai.yaml` manifests were left out: they describe the
  skills to Codex and Copilot, and Claude Code ignores them.

Nothing else was modified. Keep this list current if you edit a skill, so a
future update can tell local changes from upstream ones.

## Updating

Re-clone upstream, re-copy the 27 promoted skill folders, then re-apply the
two local changes above. Alternatively, switch to the managed plugin
(`claude plugin install mattpocock-skills@claude-plugins-official`) and delete
these folders — upstream warns that running both routes gives you every skill
twice.

## Start here

Run `/setup-matt-pocock-skills` once in this repo. It asks which issue tracker
to use, which labels `/triage` should apply, and where generated docs should
live, then writes that configuration down. Several engineering skills expect it
to have run.

`/ask-matt` routes you to the right skill if you are unsure which one fits.
