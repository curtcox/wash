# wash UI Recovery

The UI is ordinary root content. If it is edited into a broken state, re-copy
the bundle files over `ui/`, `bin/`, `env/meta`, `env/path`, and `exec`.

The runtime remains usable without the UI:

```bash
curl http://127.0.0.1:8080/some/path
curl -X PUT --data-binary @file.txt http://127.0.0.1:8080/some/path
curl -X DELETE http://127.0.0.1:8080/some/path
```
