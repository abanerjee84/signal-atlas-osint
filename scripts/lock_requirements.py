"""Write exact runtime and development dependency pins from the verified virtual environment."""

from importlib.metadata import distribution, distributions
from pathlib import Path

from packaging.requirements import Requirement

root = Path(__file__).resolve().parent.parent
runtime = set()


def visit(name):
    package = distribution(name)
    canonical = package.metadata["Name"].lower().replace("_", "-")
    if canonical in runtime:
        return
    runtime.add(canonical)
    for spec in package.requires or []:
        requirement = Requirement(spec)
        if not requirement.marker or requirement.marker.evaluate({"extra": ""}):
            visit(requirement.name)


for name in (
    "fastapi",
    "uvicorn",
    "httpx",
    "pydantic-settings",
    "defusedxml",
    "vaderSentiment",
    "langdetect",
):
    visit(name)
pins = {
    package.metadata["Name"].lower().replace("_", "-"): f"{package.metadata['Name']}=={package.version}"
    for package in distributions()
}
(root / "requirements.txt").write_text(
    "# Resolved runtime pins, Python 3.12. Regenerate with scripts/lock_requirements.py.\n"
    + "\n".join(pins[name] for name in sorted(runtime))
    + "\n",
    encoding="utf-8",
)
(root / "requirements-dev.txt").write_text(
    "-r requirements.txt\n"
    + "\n".join(pin for name, pin in sorted(pins.items()) if name not in runtime and name != "pip")
    + "\n",
    encoding="utf-8",
)
print(f"Locked {len(runtime)} runtime packages")
