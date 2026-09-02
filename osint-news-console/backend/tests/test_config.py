import os
import unittest
from unittest.mock import patch

from app import config


YAML_CONFIG = {
    "server": {"debug": False, "port": 8123},
    "database": {"path": "data/from-yaml.db"},
    "ai": {
        "mode": "mock",
        "ollama": {"fallback_model": "yaml-model", "timeout": 90},
        "deepseek": {"api_key": "yaml-key"},
    },
    "collector": {"request_timeout": 25},
    "cleanup": {"retention_days": 5},
    "rule_engine": {"source_weight": 0.55},
}


class ConfigLoadingTests(unittest.TestCase):
    def tearDown(self):
        config.reset_config()

    def test_yaml_values_populate_nested_settings(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(
            config, "_load_yaml", return_value=YAML_CONFIG
        ):
            loaded = config.get_config()

        self.assertFalse(loaded.server.debug)
        self.assertEqual(loaded.server.port, 8123)
        self.assertEqual(loaded.ai.ollama.fallback_model, "yaml-model")
        self.assertEqual(loaded.ai.ollama.timeout, 90)
        self.assertEqual(loaded.collector.request_timeout, 25)
        self.assertEqual(loaded.rule_engine.source_weight, 0.55)

    def test_environment_variables_override_yaml_without_mutating_environment(self):
        env = {
            "SERVER_PORT": "9000",
            "AI_MODE": "ollama",
            "OLLAMA_TIMEOUT": "15",
            "DEEPSEEK_API_KEY": "env-key",
            "DATABASE_PATH": "data/from-env.db",
        }
        with patch.dict(os.environ, env, clear=True), patch.object(
            config, "_load_yaml", return_value=YAML_CONFIG
        ):
            loaded = config.get_config()
            self.assertEqual(dict(os.environ), env)

        self.assertEqual(loaded.server.port, 9000)
        self.assertEqual(loaded.ai.mode, "ollama")
        self.assertEqual(loaded.ai.ollama.timeout, 15)
        self.assertEqual(loaded.ai.deepseek.api_key, "env-key")
        self.assertEqual(loaded.database["path"], "data/from-env.db")


if __name__ == "__main__":
    unittest.main()
