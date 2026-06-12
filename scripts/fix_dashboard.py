"""One-off script: update user dashboard table to show submitted + reviewed timestamps."""
import re

path = "src/admin/approval_server.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# Find the line with submitted_at[:10] and surrounding block, replace it
old_line = "              <td style=\"font-size:12px;color:#718096;\">{_esc(r.submitted_at[:10] if r.submitted_at else '\u2014')}</td>"
new_lines = (
    "              <td style=\"font-size:12px;color:#718096;\">"
    "{(r.submitted_at or '')[:16].replace('T', ' ') or '\u2014'}</td>\n"
    "              <td style=\"font-size:12px;color:#718096;\">"
    "{(getattr(r, 'reviewed_at', None) or '')[:16].replace('T', ' ') or '\u2014'}</td>"
)

if old_line not in content:
    print("ERROR: old line not found")
    exit(1)

content = content.replace(old_line, new_lines, 1)

# Fix the table header too
old_header = "            <th>ID</th><th>Car</th><th>Start</th><th>End</th><th>Type</th><th>Status</th><th>Date</th>"
new_header = "            <th>ID</th><th>Car</th><th>Start</th><th>End</th><th>Type</th><th>Status</th><th>Submitted</th><th>Reviewed</th>"

if old_header not in content:
    print("ERROR: old header not found")
    exit(1)

content = content.replace(old_header, new_header, 1)

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print("Done.")
