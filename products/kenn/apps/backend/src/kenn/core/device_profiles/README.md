# Qualified device profiles

`*.json` files here teach KENN to set a Live device parameter in real units ("set the Operator filter frequency to
2 kHz"). They are written by `tooling/scripts/qualify_device_candidates.py` after a parameter has been measured from Live's
display strings and then set, read back and restored on real Live at three or more points. `core/device_units.py` loads an
entry only if it carries a passed `qualification` block; a candidate that hasn't been qualified is ignored. The profiles
in `device_units.py` itself were verified by hand and win if the two ever disagree.
