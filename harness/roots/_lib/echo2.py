import os
import sys


def main() -> None:
    a = sys.argv[1] if len(sys.argv) > 1 else ""
    b = sys.argv[2] if len(sys.argv) > 2 else ""
    e0 = "1" if os.path.exists(a) else "0"
    e1 = "1" if os.path.exists(b) else "0"
    sys.stdout.write(
        "argv=[" + a + "|" + b + "] exists0=" + e0 + " exists1=" + e1 + "\n"
    )


if __name__ == "__main__":
    main()
