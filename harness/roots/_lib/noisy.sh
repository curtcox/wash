#!/bin/sh
. "$(dirname "$0")/_common.sh"
_wash_read_stdin
_wash_split_records | while IFS= read -r line; do
    case "$line" in
        *"$_WASH_SEP"*)
            record=${line%"$_WASH_SEP"}
            printf 'out:%s\n' "$record"
            printf 'err:%s\n' "$record" 1>&2
            ;;
    esac
done
