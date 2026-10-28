import sys
import xml.etree.ElementTree as ET


def main() -> None:
    report = sys.stdin.buffer.read()
    start = report.find(b"<BugCollection")
    if start < 0:
        return

    root = ET.fromstring(report[start:])
    for bug in root.findall("BugInstance"):
        bug_type = bug.get("type", "SpotBugs")
        message = next(
            (item.text for item in bug.findall("Message") if item.text),
            bug_type,
        )
        for source in bug.findall("SourceLine"):
            path = source.get("sourcepath")
            line = source.get("start")
            if path and line:
                print(f"{path}:{line}: {bug_type}: {message}")


if __name__ == "__main__":
    main()
