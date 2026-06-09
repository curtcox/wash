import sys


def main() -> None:
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    sys.stdout.write("argv=[" + arg + "]\n")


if __name__ == "__main__":
    main()
