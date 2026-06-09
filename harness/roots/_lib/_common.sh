# Shared helpers for wash fixture commands (sourced, not executed).
_wash_tmp=
_wash_tmp_cleanup() {
    if [ -n "$_wash_tmp" ] && [ -f "$_wash_tmp" ]; then
        rm -f "$_wash_tmp"
    fi
}

_wash_read_stdin() {
    _wash_tmp=$(mktemp)
    trap '_wash_tmp_cleanup' EXIT INT HUP TERM
    cat > "$_wash_tmp"
}

_wash_argv_str() {
    if [ "$#" -eq 0 ]; then
        printf ''
        return
    fi
    printf '%s' "$1"
    shift
    while [ "$#" -gt 0 ]; do
        printf ',%s' "$1"
        shift
    done
}

_wash_emit_tagged() {
    tag=$1
    argv_str=$2
    record=$3
    prefix=${4:-}
    printf '%s%s(%s):%s\n' "$prefix" "$tag" "$argv_str" "$record"
}

_wash_split_records() {
    awk '
    function split_records(content,    i, parts, n) {
        if (length(content) == 0)
            return 0
        if (substr(content, length(content), 1) == "\n")
            content = substr(content, 1, length(content) - 1)
        if (length(content) == 0) {
            records[1] = ""
            return 1
        }
        n = split(content, parts, "\n")
        for (i = 1; i <= n; i++)
            records[i] = parts[i]
        return n
    }
    BEGIN { RS = "^$" }
    {
        n = split_records($0)
        for (i = 1; i <= n; i++)
            print records[i] "\001"
    }' "$_wash_tmp"
}
