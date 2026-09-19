import unittest
from unittest.mock import Mock

from customer_flow import CustomerFlow, State


class CustomerFlowTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.ports = Mock()
        self.flow = CustomerFlow(self.ports, clock=lambda: self.now)

    def approach(self):
        self.flow.customer_seen("customer", "white")
        self.flow.distance("customer", 1.0, self.now)
        return self.flow.session_id

    def test_yes_waits_for_matching_order_then_leaves_and_restarts_music(self):
        session = self.approach()
        self.flow.answer(session, "yes")
        self.ports.show_order_qr.assert_called_once_with(session)
        self.assertFalse(self.flow.order_completed("old-session"))
        self.ports.leave.assert_not_called()
        self.assertTrue(self.flow.order_completed(session))
        self.assertEqual(self.flow.state, State.LEAVING)
        names = [call[0] for call in self.ports.mock_calls]
        self.assertLess(names.index("stop_jingle"), names.index("speak"))
        self.assertEqual(names[-2:], ["leave", "start_jingle"])
        self.assertFalse(self.flow.order_completed(session))
        self.assertFalse(self.flow.customer_seen("another"))
        self.assertFalse(self.flow.departure_completed("old-session"))
        self.assertTrue(self.flow.departure_completed(session))

    def test_no_says_goodbye_without_qr_and_cools_down(self):
        session = self.approach()
        self.flow.answer(session, "no")
        self.ports.show_order_qr.assert_not_called()
        self.ports.speak.assert_called_with("No problem! Have a nice day.")
        self.flow.departure_completed(session)
        self.assertFalse(self.flow.customer_seen("customer"))
        self.now += 121
        self.assertTrue(self.flow.customer_seen("customer"))

    def test_distance_requires_fresh_selected_customer_and_valid_range(self):
        self.flow.customer_seen("customer")
        for who, distance, timestamp in [
            ("another", 1, 100), ("customer", 1, 90), ("customer", 1, 101),
            ("customer", 0, 100), ("customer", -1, 100),
            ("customer", float("nan"), 100), ("customer", 3, 100),
        ]:
            self.assertFalse(self.flow.distance(who, distance, timestamp))
        self.ports.listen.assert_not_called()
        self.assertTrue(self.flow.distance("customer", 1.5, 100))

    def test_all_wait_states_time_out_without_thanking_for_order(self):
        for state, elapsed in [(State.APPROACH, 21), (State.ANSWER, 13), (State.ORDER, 181)]:
            with self.subTest(state=state):
                self.setUp()
                self.flow.customer_seen("customer")
                if state != State.APPROACH:
                    self.flow.distance("customer", 1, self.now)
                if state == State.ORDER:
                    self.flow.answer(self.flow.session_id, "yes")
                self.now += elapsed
                self.flow.tick()
                self.assertEqual(self.flow.state, State.LEAVING)
                self.ports.start_jingle.assert_called_once()
                self.assertFalse(any("Thank you for your order" in str(c) for c in self.ports.mock_calls))

    def test_late_answer_and_old_session_are_ignored(self):
        session = self.approach()
        self.assertFalse(self.flow.answer("other", "yes"))
        self.assertFalse(self.flow.answer(session, "unknown"))
        self.now += 13
        self.assertFalse(self.flow.answer(session, "yes"))
        self.ports.show_order_qr.assert_not_called()

    def test_shutdown_attempts_all_cleanup_after_failure(self):
        self.ports.stop_motion.side_effect = RuntimeError("device failure")
        with self.assertRaises(RuntimeError):
            self.flow.shutdown()
        self.ports.stop_listening.assert_called_once()
        self.ports.hide_order_qr.assert_called_once()
        self.ports.stop_jingle.assert_called_once()


if __name__ == "__main__":
    unittest.main()
