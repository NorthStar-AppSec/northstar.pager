import unittest

from alert import MAX_WAIT, wait_before_next_poll


class BackoffTest(unittest.TestCase):
    def test_normal_interval_without_failures(self):
        self.assertEqual(wait_before_next_poll(60, 0), 60)

    def test_doubles_per_failure_up_to_the_cap(self):
        self.assertEqual([wait_before_next_poll(60, n) for n in (1, 2, 3)], [120, 240, 480])
        self.assertEqual(wait_before_next_poll(60, 20), MAX_WAIT)


if __name__ == "__main__":
    unittest.main()
