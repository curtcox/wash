# wash UI Recovery

The UI is ordinary root content. If it is edited into a broken state, re-drop the
bundle over the paths listed in `ui/.ui-manifest`:

```bash
./bin/wash-ui-install /path/to/root
```

The installer merges `env/path` and `exec` additively and aborts with a conflict
report if any other bundle file already differs. Fix conflicts manually or restore
from a backup, then re-run the installer.

Reserved helper command names owned by the bundle: `ui`, `explain`, `commands`,
`names`, `name-new`, `name-set`, `name-rm`, `append`, `search`, `help`, `term`,
`rootinfo`, and `wash-ui-install`.

The runtime remains usable without the UI:

```bash
curl http://127.0.0.1:8080/some/path
curl -X PUT --data-binary @file.txt http://127.0.0.1:8080/some/path
curl -X DELETE http://127.0.0.1:8080/some/path
```
