import unittest

from dashboard_server.alerting import AlertManager, render_telegram_message, resolve_secret


class AlertingTests(unittest.TestCase):
    def test_disabled_alert_manager_skips_events(self):
        manager = AlertManager({"enabled": False, "provider": "telegram"})
        self.assertFalse(manager._should_send({"status": "scanning", "src_ip": "10.0.0.1"}))

    def test_scanning_alert_is_rate_limited_by_source(self):
        manager = AlertManager({"enabled": True, "provider": "telegram", "cooldown_seconds": 300})
        event = {"status": "scanning", "src_ip": "10.0.0.1"}
        self.assertTrue(manager._should_send(event))
        self.assertFalse(manager._should_send(event))

    def test_non_scanning_alert_is_skipped(self):
        manager = AlertManager({"enabled": True, "provider": "telegram", "cooldown_seconds": 300})
        self.assertFalse(manager._should_send({"status": "normal", "src_ip": "10.0.0.1"}))

    def test_render_message_includes_target_ips(self):
        text = render_telegram_message(
            {
                "status": "scanning",
                "score": 0.93,
                "src_ip": "10.10.90.10",
                "target_network": "10.10.20.0/24",
                "top_dst_ips": ["10.10.20.20", "10.10.20.21"],
                "top_dst_ports": [23, 80],
            }
        )
        self.assertIn("10.10.90.10", text)
        self.assertIn("10.10.20.20", text)
        self.assertIn("23, 80", text)

    def test_resolve_secret_supports_environment(self):
        self.assertEqual(resolve_secret("plain-value"), "plain-value")


if __name__ == "__main__":
    unittest.main()
