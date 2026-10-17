import unittest

from midi.velocity_mapper import VELOCITY_MAPPER


class VelocityMapperTests(unittest.TestCase):
    def test_melody_is_audible_at_medium_velocity(self):
        amp = float(VELOCITY_MAPPER.get_parameters("melody", 64)["amplitude"])
        self.assertGreaterEqual(amp, 0.70)

    def test_drone_is_stable_and_nonzero(self):
        a0 = float(VELOCITY_MAPPER.get_parameters("drone", 10)["amplitude"])
        a1 = float(VELOCITY_MAPPER.get_parameters("drone", 120)["amplitude"])
        self.assertGreater(a0, 0.0)
        self.assertAlmostEqual(a0, a1, places=5)


if __name__ == "__main__":
    unittest.main()

