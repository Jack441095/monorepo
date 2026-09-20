Type: Advanced mastering delivery
Tags: apple digital masters, 24 bit pcm, native sample rate, aac, codec audition, afclip, auroundtripaac, inter-sample clipping
Status: Approved
Source title: Apple Digital Masters Technology Brief 2.4.1
Source creator: Apple
Source URL: https://www.apple.com/hk/apple-music/apple-digital-masters/docs/apple-digital-masters.pdf
Source version: 2.4.1
Reviewed: 2026-07-01

# Apple Digital Masters Source Delivery and Codec Audition


Short answer:
Apple requires a genuine 24-bit PCM source at the highest native sample rate without artificial upsampling or bit padding. Audition an AAC encode to check for clipping; keep the original 24-bit PCM as the deliverable.

Try this:
1. Export the true high-resolution 24-bit PCM master.
2. Leave enough headroom in reconstruction and encoding to avoid driving peaks to full scale.
3. Use Apple's supported codec audition tools to create an AAC encode.
4. Listen at matched loudness levels and inspect for on-sample and inter-sample clipping.
5. Keep the audition encode separate from the original PCM delivery master.

Why it matters:
Lossy encoding can introduce artefacts not present in the PCM sample values. Audition tests ensure that the encoded file is free of these issues before final delivery.

Common mistakes:
- Delivering the AAC audition file instead of the original 24-bit PCM.
- Upsampling or bit-padding a lower-resolution source and treating it as high-quality detail.

When this does not apply:
Apple Digital Masters studio approval and delivery requirements are programme-specific. Confirm current provider requirements before final submission.

Related questions:
- What should I deliver for Apple Digital Masters?
- Should I upsample a 44.1 kHz master for delivery?
- Why should I audition AAC before delivering a master?
- Can an AAC encode clip when the PCM source does not?
