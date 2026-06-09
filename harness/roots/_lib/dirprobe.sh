#!/bin/sh
. "$(dirname "$0")/_common.sh"
_wash_read_stdin
if [ ! -s "$_wash_tmp" ]; then
    _wash_emit_tagged "$(basename "$0")" "$(_wash_argv_str "$@")" "" "dirprobe:"
else
    argv_str=$(_wash_argv_str "$@")
    _wash_split_records | while IFS= read -r line; do
        case "$line" in
            *$'\001'*)
                record=${line%$'\001'}
                _wash_emit_tagged "$(basename "$0")" "$argv_str" "$record" "dirprobe:"
                ;;
        esac
    done
fi
