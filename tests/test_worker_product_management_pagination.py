import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILE = ROOT / "src" / "worker" / "product_management.py"


class ProductManagementPaginationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SOURCE_FILE.is_file():
            raise FileNotFoundError(
                f"Product management source not found: {SOURCE_FILE}"
            )

        cls.source = SOURCE_FILE.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)
        cls.functions = {
            node.name: node
            for node in ast.walk(cls.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

    def function_source(self, name):
        node = self.functions.get(name)
        self.assertIsNotNone(
            node,
            f"Expected function {name!r} was not found.",
        )
        return ast.get_source_segment(self.source, node)

    def test_page_size_is_defined(self):
        self.assertRegex(
            self.source,
            r"(?m)^\s*PAGE_SIZE\s*=\s*8\s*$",
        )

    def test_product_count_is_scoped_to_seller(self):
        source = self.function_source("_render_product_list")
        normalized = " ".join(source.lower().split())

        self.assertIn("select count(*) as total", normalized)
        self.assertIn("where seller_id = ?", normalized)

    def test_product_query_uses_d1_pagination(self):
        source = self.function_source("_render_product_list")
        normalized = " ".join(source.lower().split())

        self.assertIn(
            "order by created_at desc, id desc",
            normalized,
        )
        self.assertIn("limit ? offset ?", normalized)
        self.assertIn(
            "seller_id,",
            normalized,
        )
        self.assertIn(
            "start,",
            normalized,
        )

    def test_page_number_is_clamped_to_valid_range(self):
        source = self.function_source("_render_product_list")
        normalized = " ".join(source.lower().split())

        self.assertIn(
            "total_products + page_size - 1",
            normalized,
        )
        self.assertIn(
            "min(int(page), total_pages - 1)",
            normalized,
        )
        self.assertIn(
            "start = page * page_size",
            normalized,
        )

    def test_previous_and_next_page_callbacks(self):
        source = self.function_source("_render_product_list")
        normalized = " ".join(source.split())

        self.assertIn(
            'if page > 0: navigation.append(',
            normalized,
        )
        self.assertIn(
            'f"prodlist:{seller_id}:{page}"',
            normalized,
        )
        self.assertIn(
            'if start + PAGE_SIZE < total_products:',
            normalized,
        )
        self.assertIn(
            'f"prodlist:{seller_id}:{page + 2}"',
            normalized,
        )

    def test_empty_product_list_has_a_message(self):
        source = self.function_source("_render_product_list")

        self.assertIn("if total_products == 0:", source)
        self.assertIn("هنوز محصولی اینجا نیست", source)

    def test_product_list_checks_seller_ownership(self):
        source = self.function_source("handle_product_list")

        self.assertIn("_owned_seller(", source)
        self.assertIn("if seller is None:", source)
        self.assertIn(
            "شما به این فروشگاه دسترسی ندارید.",
            source,
        )


if __name__ == "__main__":
    unittest.main()