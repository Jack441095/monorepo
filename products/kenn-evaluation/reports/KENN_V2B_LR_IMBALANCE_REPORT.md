# L/R Imbalance

V2-A recall was 0%. Mix-wide imbalance must not be inferred from a deliberately
panned source; source scope is unavailable in a stereo render. The V2-B gate
therefore accepts `intentional_panning` as a context confounder and abstains.
On the holdout, the candidate score detected 6/11 cases (54.5%) without healthy
recommendations. This remains below a production-ready level and needs real
channel-RMS/temporal/spectral feature work in V2-C.
