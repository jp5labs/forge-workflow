# forge-workflow

Portable bot fleet and delivery workflow toolkit. Provides structured delivery discipline, code review automation, spec-driven planning, and multi-bot coordination for any GitHub repository.

## Quickstart

```bash
pip install "forge-workflow @ git+https://github.com/jp5labs/forge-workflow.git"
cd your-repo
forge init
forge bot add mybot
forge bot launch mybot
```

## What's included

- **forge CLI** — `forge init`, `forge deliver`, `forge review`, `forge bot`, `forge self-update`
- **Safety hooks** — secret detection, file protection, compound command interception, circuit breakers
- **Skill templates** — structured delivery, planning, assessment, review workflows (Claude Code compatible)
- **Docker infrastructure** — bot containerization with tmux, Discord integration, settings sync
- **Config layer** — `.forge/config.yaml` for repo-specific values, no hardcoded references

## Config

After `forge init`, edit `.forge/config.yaml`:

```yaml
forge:
  version: 1

repo:
  org: your-org
  name: your-repo

bots:
  - name: mybot
    role: Engineer
    github_account: mybot-dev
    email: mybot@example.com

hooks:
  mode: supervised  # or autonomous
```

## Updating

```bash
forge self-update              # latest release
forge self-update --version v0.2.0  # specific version
forge doctor                   # check version status
forge update-skills            # sync skill templates
```

## License

MIT
