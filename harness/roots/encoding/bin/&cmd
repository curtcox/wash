#!/bin/sh
. "$(dirname "$0")/_common.sh"
_wash_read_stdin
needle=$1
argv_str=$(_wash_argv_str "$@")
_wash_split_records | while IFS= read -r line; do
    case "$line" in
        *$'\001'*)
            record=${line%$'\001'}
            case "$record" in
                *"$needle"*)
                    _wash_emit_tagged "$(basename "$0")" "$argv_str" "$record"
                    ;;
            esac

            ;;
    esac
done
