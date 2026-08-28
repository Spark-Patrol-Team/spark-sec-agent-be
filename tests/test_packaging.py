# -*- coding: utf-8 -*-
"""打包/安装层面回归检查。

验证点（对应知识包 package-data 的打包回归）：
  1. 知识包 `webshell-knowledge.md` 已迁入 Python 包内（`sec_agent.deep_agent`
     包的 `knowledge/` 子目录），而非依赖源码树外的 `docs/` 相对路径；
  2. `pyproject.toml` 声明了 `[tool.setuptools.package-data]`，把该 md 随 wheel/sdist
     一起分发（`pip install` 后仍可读取）；
  3. `knowledge.py` 通过 `importlib.resources` 从包内读取知识全文，等价于安装后
     读取路径，避免源码树 `parents[4]` 相对路径在安装后失效。

说明：本测试无需真实构建 wheel；构建层面的校验已通过
`python -m build --wheel --no-isolation` 手工验证 wheel 内包含
`sec_agent/deep_agent/knowledge/webshell-knowledge.md`。
"""
from __future__ import annotations

import tomllib
import unittest
from importlib import resources
from pathlib import Path

from sec_agent.deep_agent.tools.knowledge import _default_knowledge_text


# 项目根（本文件位于 tests/ 下，上一级即项目根）
_PROJECT_ROOT = Path(__file__).resolve().parents[1]


class TestKnowledgePackageData(unittest.TestCase):
    def test_knowledge_md_lives_inside_package(self):
        """知识包文件必须位于包内，才可能作为 package-data 随包分发。"""
        pkg_file = _PROJECT_ROOT / "src" / "sec_agent" / "deep_agent" / "knowledge" / "webshell-knowledge.md"
        self.assertTrue(pkg_file.is_file(), f"知识包应位于包内：{pkg_file}")

    def test_package_data_declared_in_pyproject(self):
        """pyproject.toml 需声明 package-data，把 knowledge/*.md 打进 wheel/sdist。"""
        pyproject = _PROJECT_ROOT / "pyproject.toml"
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        package_data = data["tool"]["setuptools"]["package-data"]
        self.assertIn("sec_agent.deep_agent", package_data)
        self.assertIn("knowledge/*.md", package_data["sec_agent.deep_agent"])

    def test_knowledge_loadable_via_importlib_resources(self):
        """安装后读取路径：importlib.resources 应能从包内读到知识全文。"""
        text = _default_knowledge_text()
        self.assertIn("WebShell", text)
        self.assertIn("攻击原理", text)

    def test_knowledge_resource_resolvable_from_package(self):
        """包内资源可直接定位，且是真实文件（非空）。"""
        resource = resources.files("sec_agent.deep_agent") / "knowledge" / "webshell-knowledge.md"
        self.assertTrue(resource.is_file())
        self.assertTrue(resource.read_text(encoding="utf-8").strip())


if __name__ == "__main__":
    unittest.main(verbosity=2)
