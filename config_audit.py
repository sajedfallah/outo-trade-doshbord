"""Classify the public v0.9.20 configuration contract."""
from __future__ import annotations

from config_loader import load_config

USED = {
    "telegram.channel_id", "mt5.terminal_path", "mt5.account_mode",
    "trading.entry_tolerance_points", "trading.market_entry_tolerance_price",
    "trading.deviation_points", "trading.magic_number", "risk_management.mode",
    "risk_management.default_risk_percent", "risk_management.max_risk_percent_per_trade",
    "risk_management.max_open_positions", "risk_management.min_reward_risk",
    "risk_management.max_lot", "risk_management.max_total_open_risk_percent",
    "execution.execute_by_default", "execution.telegram_only_default", "symbol_map", "symbols", "timeframes",
    "monitor.enabled", "monitor.poll_seconds", "monitor.partial_close_min_volume",
    "monitor.auto_publish_partial", "monitor.auto_publish_final", "monitor.result_chart",
    "dashboard", "reporting", "analytics", "journal", "prop_firm",
    "risk_intelligence", "workflow", "strategy_builder", "trailing",
}
DEPRECATED = {
    "execution.enable_direct_mt5", "trading.account_mode", "trading.dry_run",
    "monitor.history_days", "monitor.screenshot", "publisher.reply_result_to_signal",
}
INVALID = {"telegram.bot_token"}
UNUSED = {
    "risk_management.mode", "risk_management.risk_basis",
    "monitor.result_chart.style_version", "dashboard.performance_source",
    "dashboard.refresh_seconds", "dashboard.available_languages",
    "reporting.catchup_hours", "analytics.mae_mfe_timeframe",
    "risk_intelligence.telegram_continues_when_blocked",
    "risk_intelligence.kill_switch.block_new_mt5_orders",
    "risk_intelligence.trade_review.engine", "workflow.enabled",
    "workflow.audit_retention_events", "workflow.auto_backfill_on_demand",
    "strategy_builder.enabled", "trailing.engine_poll_source",
    "trailing.client_policy_mode", "trailing.max_targets",
    "trailing.publish_management_updates",
}


def _leaves(value, prefix=""):
    if isinstance(value, dict):
        for key, child in value.items():
            name = f"{prefix}.{key}" if prefix else key
            yield from _leaves(child, name)
    else:
        yield prefix


def classify(path: str) -> str:
    if path in INVALID:
        return "INVALID"
    if any(path == x or path.startswith(x + ".") for x in DEPRECATED):
        return "DEPRECATED"
    if any(path == x or path.startswith(x + ".") for x in UNUSED):
        return "UNUSED"
    if any(path == x or path.startswith(x + ".") or x.startswith(path + ".") for x in USED):
        return "USED"
    return "UNUSED"


def audit_config(cfg=None):
    cfg = cfg or load_config()
    return [{"key": path, "status": classify(path)} for path in sorted(_leaves(cfg))]


if __name__ == "__main__":
    for row in audit_config():
        print(f"{row['status']:10} {row['key']}")
