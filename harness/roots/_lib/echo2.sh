#!/bin/sh
a=${1:-}
b=${2:-}
if [ -e "$a" ]; then e0=1; else e0=0; fi
if [ -e "$b" ]; then e1=1; else e1=0; fi
printf 'argv=[%s|%s] exists0=%s exists1=%s\n' "$a" "$b" "$e0" "$e1"
