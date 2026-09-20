import logging
import unittest

from audio.RT_player.playback_stream import AudioOutputStream


class FakePortAudioStream:
    def __init__(self):
        self.started = False
        self.stopped = False
        self.closed = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def close(self):
        self.closed = True


class FakeSoundDevice:
    def __init__(self, devices, fail_default=True):
        self.devices = devices
        self.fail_default = fail_default
        self.query_count = 0
        self.open_calls = []

    def query_devices(self):
        self.query_count += 1
        return self.devices

    def OutputStream(self, **kwargs):
        self.open_calls.append(dict(kwargs))
        if self.fail_default and kwargs.get("device") is None:
            raise RuntimeError("default output unavailable")
        return FakePortAudioStream()


class AudioOutputStreamTests(unittest.TestCase):
    def test_start_queries_devices_once_and_falls_back_to_first_output(self):
        sd = FakeSoundDevice(
            [
                {"name": "input only", "max_output_channels": 0},
                {"name": "stereo out", "max_output_channels": 2},
            ]
        )
        stream = AudioOutputStream(sd, sample_rate=48000, blocksize=256, callback=lambda *args: None, logger=logging.getLogger("test"))

        stream.start()

        self.assertEqual(sd.query_count, 1)
        self.assertFalse(stream.failed)
        self.assertIsNotNone(stream.stream)
        self.assertTrue(stream.stream.started)
        self.assertEqual(sd.open_calls[-1]["device"], 1)
        self.assertEqual(sd.open_calls[-1]["samplerate"], 48000)
        self.assertEqual(sd.open_calls[-1]["blocksize"], 256)

    def test_start_disables_stream_when_no_devices_exist(self):
        sd = FakeSoundDevice([], fail_default=False)
        stream = AudioOutputStream(sd, sample_rate=48000, blocksize=256, callback=lambda *args: None, logger=logging.getLogger("test"))

        stream.start()

        self.assertTrue(stream.failed)
        self.assertIsNone(stream.stream)
        self.assertEqual(sd.open_calls, [])


if __name__ == "__main__":
    unittest.main()
