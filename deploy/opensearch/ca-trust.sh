#!/bin/sh
set -eu

update-ca-trust extract
keytool=/usr/share/opensearch/jdk/bin/keytool
aliases=$(mktemp)
certificates=$(mktemp)
trap 'rm -f "$aliases" "$certificates"' EXIT

"$keytool" -J-Duser.language=en -list -v -cacerts -storepass changeit > "$certificates"
awk '
        /^Alias name: / { alias = substr($0, 13) }
        /SHA256: / {
            fingerprint = $0
            sub(/^.*SHA256: /, "", fingerprint)
            gsub(/:/, "", fingerprint)
            if (fingerprint == "7DD78D5F4F13459A83DFF9ABBBA62EDBAF6F2D102BF257FD712F4D9F2746ED8D" ||
                fingerprint == "F2EDAAFF3D9B701FB4D14C9F285F8C0BAD90FC3BCC1FA07D47F4718EDABA34A5" ||
                fingerprint == "D7A7A0FB5D7E2731D771E9484EBCDEF71D5F0C3E0A2948782BC83EE0EA699EF4" ||
                fingerprint == "86A1ECBA089C4A8D3BBE2734C612BA341D813E043CF9E8A862CD5C57A36BBE6B")
                print alias
        }
    ' "$certificates" > "$aliases"

while IFS= read -r alias; do
    "$keytool" -delete -cacerts -storepass changeit -alias "$alias"
done < "$aliases"
