import sys


def main() -> None:
    args = sys.argv[1:]
    joined = "|".join(args)
    sys.stdout.write("argv=[" + joined + "]\n")


if __name__ == "__main__":
    main()
