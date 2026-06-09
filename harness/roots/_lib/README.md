# Fixture Command Library

This directory contains shared command fixtures copied into canonical roots by `harness/scripts/rebuild_corpus.py` and used during root materialization.

`exit*.sh` and `exit*.py` files are generated on demand by `harness/conformance/rootcorpus.py` and intentionally ignored by git. Regenerate them through the harness instead of editing them manually.
