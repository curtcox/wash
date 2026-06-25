names — fixture for SDT name resolution (runtime.md §6.6).

An ordinal SDT tree (0/, 0/0/, 1/) plus c naming files exercising:
  - basic name -> node resolution (greeting, node1)
  - literal child shadowing a same-named name (report.txt the file vs the name)
  - nearest-scope-wins shadowing (greeting redefined in 0/c)
  - jump + scope rebuild (zerodir -> /0, then continue into its children/scope)
  - chaining (chain -> target_b -> node1 -> /1/a)
  - loop detection (loopa <-> loopb)
  - dangling target (gone -> /nope/missing)
  - escape rejection (escape -> ../wash-outside-secret.txt, synthesized outside root)

The outside-root target for the escape case is synthesized at materialization
time (see harness/conformance/rootcorpus.py), never checked in, mirroring the
symlinks root.
