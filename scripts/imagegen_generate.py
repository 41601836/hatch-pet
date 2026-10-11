#!/usr/bin/env python3
"""Generate one hatch-pet image job through a pluggable backend.

Replaces the original skill's $imagegen delegation: the parent agent reads a
job from imagegen-jobs.json, then invokes this CLI with the job's prompt file
and grounding images. Exactly one image is produced per invocation.

Examples:
  python scripts/imagegen_generate.py \
      --prompt-file run/prompts/base-pet.md \
      --output run/generated/base.png \
      --backend trae --width 1024 --height 1024

  python scripts/imagegen_generate.py \
      --prompt-file run/prompts/idle.md \
      --input-image run/references/canonical-base.png --input-role "identity reference" \
      --input-image run/references/layout-guides/idle.png --input-role "layout guide only" \
      --output run/generated/idle.png \
      --backend manual --staging-dir ~/pet-staging
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from imagegen_backends import backend_info, get_backend


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt-file", help="Markdown/text prompt file.")
    parser.add_argument("--output", help="Output image path (PNG/WebP).")
    parser.add_argument(
        "--input-image",
        action="append",
        default=[],
        help="Grounding reference image; repeatable. Pair with --input-role.",
    )
    parser.add_argument(
        "--input-role",
        action="append",
        default=[],
        help="Role label for the matching --input-image; repeatable.",
    )
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--height", type=int, default=1024)
    parser.add_argument("--backend", default="trae", help="Backend name (see --list-backends).")
    parser.add_argument("--staging-dir", help="Staging directory for the manual backend.")
    parser.add_argument("--api-key", help="API key for the ark backend (or set ARK_API_KEY).")
    parser.add_argument("--model", help="Model ID for the ark backend.")
    parser.add_argument("--base-url", help="API base URL override for the ark backend.")
    parser.add_argument("--list-backends", action="store_true")
    args = parser.parse_args()

    if args.list_backends:
        print(backend_info())
        return

    if not args.prompt_file or not args.output:
        raise SystemExit("--prompt-file and --output are required")

    if len(args.input_role) not in {0, len(args.input_image)}:
        raise SystemExit("--input-role count must match --input-image count (or be omitted)")

    prompt_path = Path(args.prompt_file).expanduser().resolve()
    if not prompt_path.is_file():
        raise SystemExit(f"prompt file not found: {prompt_path}")
    prompt = prompt_path.read_text(encoding="utf-8").strip()
    if not prompt:
        raise SystemExit(f"prompt file is empty: {prompt_path}")

    roles = args.input_role or ["reference"] * len(args.input_image)
    input_images: list[tuple[Path, str]] = []
    for raw_path, role in zip(args.input_image, roles):
        if raw_path.startswith(("http://", "https://")):
            input_images.append((raw_path, role))  # remote URL passed through verbatim
            continue
        path = Path(raw_path).expanduser().resolve()
        if not path.is_file():
            raise SystemExit(f"input image not found: {path}")
        input_images.append((path, role))

    output_path = Path(args.output).expanduser().resolve()
    backend = get_backend(
        args.backend,
        staging_dir=Path(args.staging_dir).resolve() if args.staging_dir else None,
        api_key=args.api_key,
        model=args.model,
        base_url=args.base_url,
    )
    if input_images and not backend.supports_references:
        raise SystemExit(
            f"backend '{args.backend}' cannot use the {len(input_images)} listed input image(s); "
            "choose a backend with reference support"
        )

    backend.generate(prompt, input_images, output_path, width=args.width, height=args.height)
    print(
        json.dumps(
            {
                "ok": True,
                "backend": args.backend,
                "output": str(output_path),
                "prompt_file": str(prompt_path),
                "input_images": [str(path) for path, _role in input_images],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
