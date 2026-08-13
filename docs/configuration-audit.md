# Configuration audit

Run `python config_audit.py` to print every public `config.json` leaf as `USED`, `DEPRECATED`, `UNUSED`, or `INVALID`.

The Telegram token is invalid in public JSON and is loaded only from `NEXUS_TELEGRAM_BOT_TOKEN`. Channel ID remains ordinary non-secret configuration.

Deprecated compatibility keys remain readable for migration clarity but are not presented as active behavior: legacy direct-execution flags, duplicate trading account mode, dry-run placeholder, history-days setting, GUI screenshot settings, and publisher reply toggle. Removal is deferred to a later versioned configuration migration.
