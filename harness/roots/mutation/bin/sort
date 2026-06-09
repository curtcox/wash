#!/bin/sh
. "$(dirname "$0")/_common.sh"
if [ "$#" -lt 1 ]; then
    exit 0
fi
out_path=$1
_wash_read_stdin
_wash_split_records | while IFS= read -r line; do
    case "$line" in
        *$'\001'*)
            printf '%s\n' "${line%$'\001'}"
            ;;
    esac
done | LC_ALL=C sort -o "$out_path"
