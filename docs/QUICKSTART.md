# Quick start

Install from the public repository with Hermes already working:

```sh
hermes plugins install Qhantom-Labs/hermes64 --enable
```

Review dependency preparation prompts, restart Hermes, then **start a NEW chat**. Ask:

> Make me a game about a wizard tower with a ghost and three crystal keys.

If the one-liner is unavailable, use the release ZIP checksum, backup and extraction recipe in [Install for your agent](INSTALL-FOR-YOUR-AGENT.md). Keep any older copy outside `plugins/`; run `tools/check_install.py` on the extracted package before enabling it. The offline route requires numpy and Pillow already available to Hermes's Python.

The canonical [root quick start](../QUICKSTART.md) covers setup/download consent, old-host games-folder settings, Windows limits, expected replies and troubleshooting. A full game takes minutes and may need iteration; the agent must report missing details and failed checks. Use its actual `Play:` command and the [default controls](../PLAY.md).
