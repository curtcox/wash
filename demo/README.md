# wash UI demo root

Small SDT notebook with a sample command and `c` names (including a dangling
target) for manual UI verification.

Install the bundle, then serve this root:

```bash
./bin/wash-ui-install "$(pwd)/demo"
PYTHONPATH=impls/reference python3 -m wash.server --root demo --port 8080
```

Open `http://127.0.0.1:8080/ui/` for the framed UI, or `./demo/start` from the
repo root to install (if needed) and launch with a browser.
