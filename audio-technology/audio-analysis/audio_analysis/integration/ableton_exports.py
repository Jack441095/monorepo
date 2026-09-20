from __future__ import annotations

import gzip
import math


def generate_correction_rack(
    review_id: str, *, review_lookup: callable, report_reader: callable
) -> bytes | None:
    review = review_lookup(review_id)
    if not review:
        return None
    report = report_reader(review.get("report_name", ""))
    metrics = report.get("metrics") or {}
    mix_bands = metrics.get("bands") or {}

    ref_bands = {}
    ref_payload = report.get("reference")
    if isinstance(ref_payload, dict):
        ref_bands = ref_payload.get("metrics", {}).get("bands") or {}

    gains = {}
    bands_keys = ["sub", "bass", "low_mids", "mids", "presence", "sibilance", "air"]
    for key in bands_keys:
        mix_val = float(mix_bands.get(key, 0.15))
        ref_val = float(ref_bands.get(key, 0.15))
        if mix_val <= 0:
            mix_val = 0.01
        if ref_val <= 0:
            ref_val = 0.01
        gain_db = 10 * math.log10(ref_val / mix_val)
        gains[key] = max(-12.0, min(12.0, gain_db))

    sub = gains.get("sub", 0.0)
    bass = gains.get("bass", 0.0)
    low_mids = gains.get("low_mids", 0.0)
    mids = gains.get("mids", 0.0)
    presence = gains.get("presence", 0.0)
    sibilance = gains.get("sibilance", 0.0)
    air = gains.get("air", 0.0)

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Ableton MajorVersion="5" MinorVersion="11.0_11300" SchemaVersion="3" Creator="Ableton Live 11">
	<Eq8>
		<On Value="true" />
		<IsExpanded Value="true" />
		<IsVertical Value="false" />
		<ActiveBand Value="0" />
		<Bands>
			<Band id="0">
				<On Value="true" />
				<Mode Value="2" />
				<Frequency Value="30.0" />
				<Gain Value="{sub:.2f}" />
				<Q Value="0.71" />
			</Band>
			<Band id="1">
				<On Value="true" />
				<Mode Value="2" />
				<Frequency Value="100.0" />
				<Gain Value="{bass:.2f}" />
				<Q Value="0.71" />
			</Band>
			<Band id="2">
				<On Value="true" />
				<Mode Value="2" />
				<Frequency Value="280.0" />
				<Gain Value="{low_mids:.2f}" />
				<Q Value="0.71" />
			</Band>
			<Band id="3">
				<On Value="true" />
				<Mode Value="2" />
				<Frequency Value="1000.0" />
				<Gain Value="{mids:.2f}" />
				<Q Value="0.71" />
			</Band>
			<Band id="4">
				<On Value="true" />
				<Mode Value="2" />
				<Frequency Value="4000.0" />
				<Gain Value="{presence:.2f}" />
				<Q Value="0.71" />
			</Band>
			<Band id="5">
				<On Value="true" />
				<Mode Value="2" />
				<Frequency Value="7000.0" />
				<Gain Value="{sibilance:.2f}" />
				<Q Value="0.71" />
			</Band>
			<Band id="6">
				<On Value="true" />
				<Mode Value="3" />
				<Frequency Value="12000.0" />
				<Gain Value="{air:.2f}" />
				<Q Value="0.71" />
			</Band>
			<Band id="7">
				<On Value="false" />
				<Mode Value="4" />
				<Frequency Value="20000.0" />
				<Gain Value="0.0" />
				<Q Value="0.71" />
			</Band>
		</Bands>
	</Eq8>
</Ableton>
"""
    return gzip.compress(xml.encode("utf-8"))
