# 3-minute pitch: script, best points, Q&A

Deck: `docs/slides/prebuilt-pitch.html` (6 slides, rebuild with `python docs/slides/make_pitch.py`). Present mode: double-click a slide, arrows to move, Esc to exit. The demo is slide 3 and never leaves the deck: in Present mode it plays by itself when the slide comes up (about 10 s). **P** replays it, **L** switches the lying site on or off. The caption line under the chart narrates each round, so you can read it as you go. The full 10-slide deck (`prebuilt-deck.html`) is backup for questions.

## Script (~380 words spoken, ~3:00)

**1 · Problem (0:00–0:25).** "Every 3D printer misses in its own way: holes come out small, pins come out fat. Every shop learns that from scratch, one test print at a time, and they can't pool the data, because measurements give away process know-how and customer parts. So we asked: can printers learn from each other without sharing a single measurement?"

**2 · What we built (0:25–0:50).** "Two real printers, a resin printer and a PLA printer, each with its own team of agents. They print this test plate, scan it on an ordinary flatbed, and fit a physics model of their own machine. The only thing that crosses between sites is this: the mean and uncertainty of three parameters that every printer shares. Nothing else gets through. It's schema-checked and written on a hash chain."

**3 · Demo (0:50–1:40).** It starts by itself. "Each round, both sites print and measure. Only the summaries cross. Blue is a site learning alone, green is pooling all the raw data, the upper bound. Orange is our network: it drops below learning alone and lands on the oracle, without the data ever moving." Press **L**. "Now the PLA site lies: confident, wrong beliefs. Resin gets hurt for one round, its trust in PLA collapses to one percent, and by round three it's back on its own feet. A liar costs one round."

**4 · Results (1:40–2:15).** "Across a hundred simulated worlds with hidden truth: twelve percent lower error than learning alone, in three out of four worlds, and as good as pooling the data. With four sites that each know little, it's twenty-five percent. That's where this pays: many machines, each with only a little data."

**5 · Science (2:15–2:40).** "We didn't just tune until it looked good. We froze the configuration, pre-registered the claims and the failure rules, and committed a prediction for the real printers before the first real round. Every plate, bid and message is on a receipt anyone can replay."

**6 · Close (2:40–3:00).** "Any shop that can print a flat plate can join, learn faster, and keep its data. The test plate, the scanner tool and the simulator are open today. Print anywhere, trust the part."

## The five points to land

1. **The constraint is real and the design honours it:** no raw data crosses, enforced by a schema and proven by a replayable receipt chain.
2. **Matches the upper bound:** networked ≈ pooling all raw data (12.3% vs 12.2% at round 3, 100 worlds).
3. **Robust:** a lying site is cut to 1% trust after one round.
4. **It scales where it matters:** many sites with little data, 25%.
5. **Scientific discipline:** frozen config, pre-registration with fallback tiers, prediction committed before real data.

## Likely questions, honest answers

- **"Is a couple of microns worth it?"** At two sites with a 16-piece seed plate the gain is 1.6 µm (12%), small next to ~30 µm scanner noise. It grows with the number of data-poor sites (6.1 µm, 25%, at four). Two printers is the smallest possible network; the point is the method and its guarantees. Source: `hpc/sweeps/relevance/README.md`.
- **"Did it work on the real printers?"** Show the real point against the committed range (slide 5). If it's flat: a single run shows a gain only ~65–70% of the time even in simulation, because the benefit varies from one printer pair to the next. That's why we committed a range, not "networked must win" (`docs/build/07-status.md`, held-out section).
- **"What do the agents add?"** Honestly, little: with messages cut, learned credibility does no better than equal votes, and a saboteur agent barely hurts. The gain comes from the shared beliefs. The agents allocate plate slots and are where hypotheses would enter.
- **"Couldn't you just share the data anonymized?"** Measurements of a customer's part geometry are the IP. Summaries of three process-agnostic parameters are not, and the receipts prove nothing else left.
- **"Why trust the simulator?"** It's calibrated to the real seed plates before any real round (Phase D), and a seed-plate check flags any printer outside what the model can represent.
- **"Why not start trust lower?"** Starting at 0.3 only trims the first-round damage (39 → 31 µm) and costs a little when everyone is honest. A consistency check on incoming summaries would likely catch a liar in round 1; it's future work.

## If something breaks on stage

The deck is one self-contained file and works offline. If the demo animation misbehaves, the static end state is already drawn at rest, so narrate it. The full deck and `demo/tier-d/run-seed0.html` are backups.
