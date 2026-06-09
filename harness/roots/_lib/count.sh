#!/bin/sh
. "$(dirname "$0")/_common.sh"
_wash_read_stdin
n=$(_wash_split_records | grep -c "$_WASH_SEP" || true)
_wash_emit_tagged "$(basename "$0")" "" "$n"
