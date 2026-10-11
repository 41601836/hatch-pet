#!/usr/bin/env python3
"""Pluggable image-generation backends for the hatch-pet pipeline.

A backend takes a text prompt plus optional grounding reference images and
produces exactly one image file. Backends are deliberately simple so any
image API (or a fully manual workflow) can be slotted in without touching
the deterministic raster pipeline.
"""

from __future__ import annotations

import json
import shutil
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Protocol


class ImagegenBackend(Protocol):
    """One image in, one image out.

    input_images items are (path, role) pairs; role describes how the image
    should be used, e.g. "canonical identity reference" or "layout guide".
    Backends that cannot accept references must say so in supports_references.
    """

    name: str
    supports_references: bool

    def generate(
        self,
        prompt: str,
        input_images: list[tuple[Path, str]],
        output_path: Path,
        *,
        width: int,
        height: int,
    ) -> None:
        ...


# The Trae text-to-image endpoint exposed to this environment. It is
# prompt-only (no reference images) and offers fixed aspect ratios, so it is
# best suited to the base pet image; row strips should use a backend with
# reference support when available.
TRAE_TEXT_TO_IMAGE_URL = "https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image"

# Map requested dimensions to the closest supported image_size preset.
_SIZE_PRESETS = {
    "square_hd": (1, 1),
    "square": (1, 1),
    "portrait_4_3": (3, 4),
    "portrait_16_9": (9, 16),
    "landscape_4_3": (4, 3),
    "landscape_16_9": (16, 9),
}


def _closest_size_preset(width: int, height: int) -> str:
    ratio = width / height
    return min(
        _SIZE_PRESETS,
        key=lambda name: abs(_SIZE_PRESETS[name][0] / _SIZE_PRESETS[name][1] - ratio),
    )


class TraeHttpBackend:
    name = "trae"
    supports_references = False

    def __init__(self, timeout: float = 180.0):
        self.timeout = timeout

    def generate(
        self,
        prompt: str,
        input_images: list[tuple[Path, str]],
        output_path: Path,
        *,
        width: int,
        height: int,
    ) -> None:
        if input_images:
            raise SystemExit(
                "trae backend does not support reference images; "
                "use a backend with reference support for row strips, or the manual backend"
            )
        params = urllib.parse.urlencode(
            {
                "prompt": prompt,
                "image_size": _closest_size_preset(width, height),
            }
        )
        request = urllib.request.Request(
            f"{TRAE_TEXT_TO_IMAGE_URL}?{params}",
            headers={"User-Agent": "hatch-pet/1.0"},
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            body = response.read()
            content_type = response.headers.get("Content-Type", "")
        if not content_type.startswith("image/"):
            raise SystemExit(
                f"trae backend returned non-image content ({content_type}): {body[:300]!r}"
            )
        output_path.write_bytes(body)


class ManualBackend:
    """No API: the operator (or the agent's own image tooling) generates the
    image elsewhere and stages it at the expected path. This backend simply
    promotes the staged file into place, failing loudly if it is missing."""

    name = "manual"
    supports_references = True  # references are handled outside this process

    def __init__(self, staging_dir: Path):
        self.staging_dir = staging_dir

    def generate(
        self,
        prompt: str,
        input_images: list[tuple[Path, str]],
        output_path: Path,
        *,
        width: int,
        height: int,
    ) -> None:
        staged = self.staging_dir / output_path.name
        if not staged.is_file():
            raise SystemExit(
                f"manual backend: staged image not found: {staged}\n"
                "Generate the image with your preferred tool and place it there, then rerun."
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(staged, output_path)


class ArkSeedreamBackend:
    """Volcano Engine Ark images API (Seedream). Supports reference images."""

    name = "ark"
    supports_references = True
    DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"

    def __init__(
        self,
        api_key: str,
        model: str = "doubao-seedream-4-0-250828",
        base_url: str | None = None,
        timeout: float = 300.0,
    ):
        if not api_key:
            raise SystemExit("ark backend requires an API key (--api-key or ARK_API_KEY)")
        self.api_key = api_key
        self.model = model
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout

    @staticmethod
    def _data_uri(path: Path) -> str:
        import base64
        import mimetypes

        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")

    def generate(
        self,
        prompt: str,
        input_images: list[tuple[Path, str]],
        output_path: Path,
        *,
        width: int,
        height: int,
    ) -> None:
        payload: dict[str, object] = {
            "model": self.model,
            "prompt": prompt,
            "size": f"{width}x{height}",
            "response_format": "b64_json",
            "watermark": False,
        }
        if input_images:
            payload["image"] = [self._data_uri(path) for path, _role in input_images]

        request = urllib.request.Request(
            f"{self.base_url}/images/generations",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            raise SystemExit(f"ark API error {exc.code}: {detail}") from exc

        items = body.get("data") or []
        if not items or not items[0].get("b64_json"):
            raise SystemExit(f"ark API returned no image data: {json.dumps(body)[:500]}")
        import base64

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(base64.b64decode(items[0]["b64_json"]))


class WanxDashScopeBackend:
    """Alibaba DashScope Tongyi Wanx backend (async task API).

    Primary path uses wanx2.1-imageedit with reference images for identity
    locking. On quota / not-activated / rate-limit errors it falls through a
    model chain automatically (imageedit -> t2i max -> plus -> turbo).
    """

    name = "wanx"
    supports_references = True
    DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com"

    # errors that should trigger the next model in the chain
    FALLBACK_CODES = (
        "quota", "Throttling", "RateLimit", "ModelNotOpen", "AccessDenied",
        "ServiceUnavailable", "Arrearage", "Forbidden", "NotSupported",
    )

    def __init__(
        self,
        api_key: str,
        model: str | None = None,
        base_url: str | None = None,
        timeout: float = 300.0,
        poll_interval: float = 2.0,
    ):
        if not api_key:
            raise SystemExit("wanx backend requires an API key (--api-key or DASHSCOPE_API_KEY)")
        self.api_key = api_key
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.poll_interval = poll_interval
        # model chain: explicit model first, then degraded fallbacks
        self.model_chain = [model] if model else []
        self.model_chain += [
            m for m in ("wanx2.1-imageedit", "wanx2.1-t2i-max",
                        "wanx2.1-t2i-plus", "wanx2.1-t2i-turbo")
            if m not in self.model_chain
        ]
        self.last_model: str | None = None

    @staticmethod
    def _data_uri(path: Path) -> str:
        import base64
        import mimetypes

        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")

    def _post(self, url: str, payload: dict[str, object], async_header: bool = False) -> dict[str, object]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if async_header:
            headers["X-DashScope-Async"] = "enable"
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            raise _WanxHTTPError(exc.code, detail) from exc

    def _get(self, url: str) -> dict[str, object]:
        request = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            raise _WanxHTTPError(exc.code, exc.read().decode("utf-8", "replace")) from exc

    @staticmethod
    def _is_fallbackable(exc: Exception) -> bool:
        if isinstance(exc, _WanxHTTPError):
            return any(code in exc.detail for code in WanxDashScopeBackend.FALLBACK_CODES)
        text = str(exc)
        return any(code.lower() in text.lower() for code in WanxDashScopeBackend.FALLBACK_CODES)

    def _submit_imageedit(
        self, model: str, function: str, prompt: str, image_url: str,
    ) -> str:
        body = self._post(
            f"{self.base_url}/api/v1/services/aigc/image2image/image-synthesis",
            {
                "model": model,
                "input": {
                    "function": function,
                    "prompt": prompt,
                    "base_image_url": image_url,
                },
                "parameters": {"n": 1},
            },
            async_header=True,
        )
        return body["output"]["task_id"]

    def _submit_t2i(self, model: str, prompt: str, size: str) -> str:
        body = self._post(
            f"{self.base_url}/api/v1/services/aigc/text2image/image-synthesis",
            {
                "model": model,
                "input": {"prompt": prompt},
                "parameters": {"size": size, "n": 1, "prompt_extend": False},
            },
            async_header=True,
        )
        return body["output"]["task_id"]

    def _wait_result_url(self, task_id: str) -> str:
        import time

        url = f"{self.base_url}/api/v1/tasks/{task_id}"
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            body = self._get(url)
            output = body.get("output", {})
            status = output.get("task_status", body.get("task_status"))
            if status == "SUCCEEDED":
                results = output.get("results") or []
                if results and results[0].get("url"):
                    return results[0]["url"]
                raise SystemExit(f"wanx task {task_id} succeeded without url: {body}")
            if status in ("FAILED", "CANCELED", "UNKNOWN"):
                raise _WanxTaskError(
                    output.get("code") or str(status),
                    output.get("message", json.dumps(output)[:300]),
                )
            time.sleep(self.poll_interval)
        raise SystemExit(f"wanx task {task_id} timed out after {self.timeout:.0f}s")

    def _download(self, url: str, output_path: Path) -> None:
        with urllib.request.urlopen(url, timeout=self.timeout) as response:
            data = response.read()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(data)

    def generate(
        self,
        prompt: str,
        input_images: list[tuple[Path, str]],
        output_path: Path,
        *,
        width: int,
        height: int,
    ) -> None:
        size = f"{width}*{height}"
        image_uris: list[str] = []
        for raw, _role in input_images:
            if isinstance(raw, str) and raw.startswith(("http://", "https://")):
                image_uris.append(raw)
            else:
                image_uris.append(self._data_uri(Path(raw)))
        errors: list[str] = []

        for model in self.model_chain:
            try:
                if model == "wanx2.1-imageedit":
                    if not image_uris:
                        errors.append(f"{model}: needs reference image, skipped")
                        continue
                    first_path, first_role = input_images[0]
                    # photo/raw pet -> instruction edit into cartoon base;
                    # already-cartoon base -> cartoon-character reference generation
                    role = first_role.lower()
                    if "cartoon" in role or "canonical" in role or "base" in role:
                        function = "control_cartoon_feature"
                    else:
                        function = "description_edit"
                    task_id = self._submit_imageedit(model, function, prompt, image_uris[0])
                else:
                    task_id = self._submit_t2i(model, prompt, size)
                result_url = self._wait_result_url(task_id)
                self._download(result_url, output_path)
                self.last_model = model
                return
            except (_WanxHTTPError, _WanxTaskError) as exc:
                errors.append(f"{model}: {exc}")
                if not self._is_fallbackable(exc):
                    raise SystemExit(f"wanx generation failed (non-retryable): {errors[-1]}")
                continue
        raise SystemExit("wanx generation failed across all models:\n  - " + "\n  - ".join(errors))


class _WanxHTTPError(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(f"HTTP {status}: {detail[:300]}")


class _WanxTaskError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def get_backend(
    name: str,
    *,
    staging_dir: Path | None = None,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
) -> ImagegenBackend:
    if name == "trae":
        return TraeHttpBackend()
    if name == "manual":
        root = staging_dir or Path.cwd() / "staged"
        return ManualBackend(root)
    if name == "ark":
        import os

        return ArkSeedreamBackend(
            api_key=api_key or os.environ.get("ARK_API_KEY", ""),
            model=model or "doubao-seedream-4-0-250828",
            base_url=base_url,
        )
    if name == "wanx":
        import os

        return WanxDashScopeBackend(
            api_key=api_key or os.environ.get("DASHSCOPE_API_KEY", ""),
            model=model,
            base_url=base_url,
        )
    raise SystemExit(f"unknown imagegen: {name}")


def backend_info() -> str:
    return json.dumps(
        {
            "backends": [
                {
                    "name": "trae",
                    "supports_references": False,
                    "notes": "HTTP text-to-image endpoint; fixed aspect presets; prompt-only",
                },
                {
                    "name": "manual",
                    "supports_references": True,
                    "notes": "promotes a file you generated externally from the staging dir",
                },
                {
                    "name": "ark",
                    "supports_references": True,
                    "notes": "Volcano Engine Ark Seedream; set ARK_API_KEY or pass --api-key",
                },
                {
                    "name": "wanx",
                    "supports_references": True,
                    "notes": "Tongyi Wanx / DashScope; auto fallback imageedit->t2i max/plus/turbo; set DASHSCOPE_API_KEY",
                },
            ]
        },
        indent=2,
    )
