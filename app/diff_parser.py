from dataclasses import dataclass, field

@dataclass
class FileDiff:
    """Represents the diff for a single file, including line mapping."""
    path: str
    content: str
    # Maps line number in the new file to its 1-based position in the diff
    line_mapping: dict[int, int] = field(default_factory=dict)

def parse_diff(diff_text: str) -> list[FileDiff]:
    """
    Parses a unified diff into FileDiff objects, calculating the position
    of each added or modified line within the diff for commenting.
    """
    file_diffs_raw = diff_text.split('diff --git ')[1:]
    parsed_diffs = []

    for file_diff_raw in file_diffs_raw:
        try:
            lines = file_diff_raw.split('\n')
            first_line = lines[0]
            # Extract the 'b' path, which is the new file path
            path = first_line.split(' b/')[1].strip()
            
            content = 'diff --git ' + file_diff_raw
            file_diff_obj = FileDiff(path=path, content=content)

            position_in_diff = 0
            current_new_line_num = 0

            for line in lines:
                position_in_diff += 1
                if line.startswith('@@'):
                    # e.g., @@ -1,13 +1,15 @@
                    hunk_info = line.split(' ')[2]
                    current_new_line_num = int(hunk_info.split(',')[0][1:])
                elif line.startswith('+') and not line.startswith('+++'):
                    file_diff_obj.line_mapping[current_new_line_num] = position_in_diff
                    current_new_line_num += 1
                elif line.startswith(' ') and not line.startswith('---'):
                    current_new_line_num += 1
            
            parsed_diffs.append(file_diff_obj)
        except (IndexError, ValueError) as e:
            print(f"Warning: Could not parse a file diff segment. Error: {e}")
            continue
            
    return parsed_diffs
