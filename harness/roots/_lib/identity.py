import sys

import sys


def _read_stdin() -> bytes:
    return sys.stdin.buffer.read()


def _split_records(data: bytes) -> list[bytes]:
    if not data:
        return []
    if data.endswith(b"\n"):
        data = data[:-1]
    if not data:
        return [b""]
    return data.split(b"\n")


def _argv_str(argv: list[str]) -> str:
    return ",".join(argv)


def _emit_line(parts: list[str]) -> None:
    line = "".join(parts) + "\n"
    sys.stdout.buffer.write(line.encode("utf-8", errors="surrogateescape"))


def _emit_tagged(tag: str, argv: list[str], record: bytes, *, prefix: str = "") -> None:
    rec = record.decode("utf-8", errors="surrogateescape")
    _emit_line([prefix, tag, "(", _argv_str(argv), "):", rec])


def _emit_tagged_records(tag: str, argv: list[str], records: list[bytes], *, prefix: str = "") -> None:
    for record in records:
        _emit_tagged(tag, argv, record, prefix=prefix)


def _contains_substring(record: bytes, needle: str) -> bool:
    return needle in record.decode("utf-8", errors="surrogateescape")


def main() -> None:
    argv = sys.argv[1:]
    data = _read_stdin()
    records = _split_records(data)
    _emit_tagged_records("identity", argv, records)

    return None


if __name__ == "__main__":
    main()
