import sys


def main() -> None:
    suffix = sys.argv[1] if len(sys.argv) > 1 else ""
    sys.stdout.write(suffix)


if __name__ == "__main__":
    main()
