from dataclasses import dataclass

@dataclass
class FileDiff:
    """Represents the diff for a single file."""
    path: str
    content: str

def parse_diff(diff_text: str) -> list[FileDiff]:
    """
    Parses a unified diff text into a list of FileDiff objects, one for each file.
    """
    # The file delimiter in a GitHub diff is 'diff --git ...'
    # We split the text by this delimiter. The first item is usually empty.
    file_diffs_raw = diff_text.split('diff --git ')[1:]
    
    parsed_diffs = []
    for file_diff_raw in file_diffs_raw:
        try:
            # The first line of each raw chunk contains the file path.
            # e.g., 'a/path/to/file.py b/path/to/file.py\n'
            first_line = file_diff_raw.split('\n')[0]
            # Extract the 'a' path, which is the original file path.
            path = first_line.split(' ')[0][2:]  # Removes the 'a/' prefix
            
            # Re-add the 'diff --git ' prefix to the content for completeness.
            content = 'diff --git ' + file_diff_raw
            
            parsed_diffs.append(FileDiff(path=path, content=content))
        except IndexError:
            # This can happen if a diff chunk is malformed.
            print(f"Warning: Could not parse a file diff segment.\nSegment (first 100 chars): {file_diff_raw[:100]}...")
            continue
            
    return parsed_diffs
