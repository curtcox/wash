#!/bin/sh
. "$(dirname "$0")/_common.sh"
_wash_read_stdin
n=$(_wash_split_records | grep -c $'\001' || true)
printf '%s\n' "$n"
