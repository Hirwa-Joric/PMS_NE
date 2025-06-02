#!/bin/bash
# Loop through all .txt files in the current directory
for file in *.txt; do
    if [[ -f "$file" ]]; then
        # Create a temp file
        tmp_file=$(mktemp)
        # Replace the first number in each line with 0
        sed -E 's/^[0-9]+/0/' "$file" > "$tmp_file"
        # Overwrite the original file
        mv "$tmp_file" "$file"
    fi
done
