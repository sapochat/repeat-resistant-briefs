import argparse, json
from pathlib import Path
from .briefs import build_source_pack

def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument("candidates"); p.add_argument("history"); p.add_argument("output"); p.add_argument("--limit",type=int,default=8); a=p.parse_args()
    text=build_source_pack(json.loads(Path(a.candidates).read_text()), json.loads(Path(a.history).read_text()), a.limit)
    Path(a.output).write_text(text); print(a.output); return 0
if __name__ == "__main__": raise SystemExit(main())
