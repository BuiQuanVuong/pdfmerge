# file: pdfmerge.py
import argparse, json, sys, os
from pypdf import PdfReader, PdfWriter
from pypdf.errors import FileNotDecryptedError

def parse_range(spec):
    # "1,3,8-12,-5,7-"
    parts = []
    for token in spec.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            a, b = token.split("-", 1)
            start = int(a) if a else None
            end = int(b) if b else None
            parts.append((start, end))
        else:
            n = int(token)
            parts.append((n, n))
    return parts

def page_indices(ranges, total):
    # Convert 1-based ranges to 0-based indices inclusive
    if not ranges:
        return list(range(total))
    idx = []
    for (s, e) in ranges:
        s0 = 1 if s is None else s
        e0 = total if e is None else e
        s0 = max(1, s0); e0 = min(total, e0)
        if s0 <= e0:
            idx.extend(range(s0-1, e0))
    # Deduplicate but keep order
    seen = set(); out = []
    for i in idx:
        if i not in seen:
            seen.add(i); out.append(i)
    return out

def main():
    ap = argparse.ArgumentParser(description="Merge PDF files.")
    ap.add_argument("inputs", nargs="+", help="Input PDF files")
    ap.add_argument("-o","--output", required=True, help="Output PDF file")
    ap.add_argument("-r","--range", action="append", help="Page range for the preceding input (repeatable)")
    ap.add_argument("-b","--bookmarks", action="store_true", help="Create bookmarks per source")
    ap.add_argument("-m","--metadata", help="JSON string with Title/Author/Subject/Keywords")
    ap.add_argument("-e","--exclude-encrypted", action="store_true", help="Skip encrypted PDFs instead of failing")
    ap.add_argument("-q","--quiet", action="store_true")
    ap.add_argument("-v","--verbose", action="store_true")
    args = ap.parse_args()

    if args.range and len(args.range) not in (1, len(args.inputs)):
        print("If using --range, supply one per input or a single range applied to all.", file=sys.stderr)
        sys.exit(2)

    # Normalize range list to match inputs
    ranges = []
    if args.range:
        if len(args.range) == 1:
            ranges = [args.range[0]] * len(args.inputs)
        else:
            ranges = args.range
    else:
        ranges = [None] * len(args.inputs)

    writer = PdfWriter()

    for in_path, r in zip(args.inputs, ranges):
        if not os.path.exists(in_path):
            print(f"Missing file: {in_path}", file=sys.stderr); sys.exit(1)
        try:
            reader = PdfReader(in_path)
            if reader.is_encrypted:
                try:
                    reader.decrypt("")  # try empty password
                except Exception:
                    if args.exclude_encrypted:
                        if not args.quiet:
                            print(f"Skipping encrypted: {in_path}")
                        continue
                    else:
                        print(f"Encrypted file requires password: {in_path}", file=sys.stderr)
                        sys.exit(1)
        except FileNotDecryptedError:
            if args.exclude_encrypted:
                print(f"Skipping encrypted: {in_path}")
                continue
            else:
                print(f"Encrypted file requires password: {in_path}", file=sys.stderr)
                sys.exit(1)

        total = len(reader.pages)
        rng = parse_range(r) if r else []
        indices = page_indices(rng, total)
        if args.verbose:
            rs = r or "ALL"
            print(f"{in_path}: {len(indices) if rng else total} pages (range={rs})")

        # Add pages
        if rng:
            for i in indices:
                writer.add_page(reader.pages[i])
        else:
            for page in reader.pages:
                writer.add_page(page)

        # Optional: bookmark top-level for this source
        if args.bookmarks:
            label = os.path.basename(in_path)
            start = len(writer.pages) - (len(indices) if rng else total)
            writer.add_outline_item(label, start)

    # Metadata
    if args.metadata:
        meta = json.loads(args.metadata)
        info = {}
        for k in ("Title","Author","Subject","Keywords"):
            if k in meta:
                info[f"/{k}"] = meta[k]
        if info:
            writer.add_metadata(info)

    # Write out (streaming)
    with open(args.output, "wb") as f:
        writer.write(f)

    if not args.quiet:
        print(f"Wrote {args.output}")

if __name__ == "__main__":
    main()
