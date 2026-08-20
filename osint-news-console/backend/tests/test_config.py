from app.config import AppConfig


def test_default_weights_sum_to_one():
    config = AppConfig()
    rule = config.rule_engine
    assert (
        round(
            rule.source_weight
            + rule.corroboration_weight
            + rule.freshness_weight
            + rule.completeness_weight,
            6,
        )
        == 1.0
    )


def test_source_specific_collector_defaults():
    config = AppConfig.model_validate({"collector": {"interval_minutes": 30}})
    assert config.collector.interval_minutes == 30
    assert config.timezone == "Asia/Shanghai"
