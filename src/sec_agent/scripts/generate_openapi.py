from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sec_agent.api.app import create_app


DEFAULT_OUTPUT = Path("docs/swagger/openapi.json")


def generate_openapi(output_path: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    app = create_app(build_runtime_container=False)
    schema = app.openapi()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return schema


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成 FastAPI OpenAPI/Swagger JSON 文档")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"输出文件路径，默认 {DEFAULT_OUTPUT}",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    schema = generate_openapi(args.output)
    print(f"OpenAPI 文档已生成: {args.output}，接口数量: {len(schema.get('paths', {}))}")


if __name__ == "__main__":
    main()
