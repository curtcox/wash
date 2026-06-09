#!/bin/sh
joined=""
for arg in "$@"; do
    if [ -z "$joined" ]; then
        joined="$arg"
    else
        joined="$joined|$arg"
    fi
done
printf 'argv=[%s]\n' "$joined"
