# Cursor (editor-resident agent)

Cursor is a closed-source AI code editor with a built-in agent. It has no public repository, so
this description stands in for a README.

- **Beacon.** Project rules live in `.cursor/rules/*.mdc`; the agent reads them as standing
  instructions, the role CLAUDE.md or AGENTS.md play for the terminal CLIs.
- **Palette.** The agent runs through the editor, so its moves are editor-shaped: propose and
  apply a diff to a file, run a command in the integrated terminal, search the workspace.
- **Sandbox.** Whatever your editor and operating system already grant. There is no separate
  kernel policy, so the agent acts with your user's reach unless you constrain it yourself.
- **Shape.** The same model-in-a-loop-with-tools as the others, defaulted toward interactive,
  in-editor work with a human watching rather than unattended runs.
