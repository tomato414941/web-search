import csv
import io
import logging
import zipfile
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

TRANCO_URL = "https://tranco-list.eu/top-1m.csv.zip"


def download_tranco(count: int = 1000) -> list[str]:
    """Download Tranco list and return top N domains as URLs."""
    logger.info(f"Downloading Tranco list (top {count})...")
    req = Request(TRANCO_URL, headers={"User-Agent": "PaleblueBot/1.0"})
    with urlopen(req, timeout=30) as resp:
        zip_data = resp.read()

    with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
        csv_name = zf.namelist()[0]
        with zf.open(csv_name) as f:
            reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8"))
            domains = []
            for row in reader:
                if len(row) >= 2:
                    domains.append(row[1].strip())
                if len(domains) >= count:
                    break

    logger.info(f"Got {len(domains)} domains from Tranco list")
    return [f"https://{d}/" for d in domains]
