from pathlib import Path
from shutil import copytree, ignore_patterns


ROOT = Path(__file__).resolve().parent.parent
copytree(
    ROOT / "restaurant" / "static",
    ROOT / "public" / "static",
    dirs_exist_ok=True,
    ignore=ignore_patterns("*.local.woff2"),
)
